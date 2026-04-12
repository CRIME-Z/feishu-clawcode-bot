"""
ACP Agent - claw-code --acp 持久进程管理器
通过 JSON-RPC 2.0 与 claw-code 通信
"""
import subprocess
import threading
import time
import logging
import json
import select
import os
import signal
import fcntl
import uuid
from typing import Dict, Optional, Callable
from .watchdog import SilenceWatchdog

logger = logging.getLogger(__name__)


class ACPAgent:
    """
    ACP 持久进程管理器：
    - 启动 `agent --acp` 持久进程
    - 通过 stdin/stdout 发送 JSON-RPC 2.0 消息
    - 实时读取 stdout，触发看门狗重置
    - 自动重连机制
    """

    def __init__(
        self,
        agent_path: str = "agent",
        working_dir: str = None,
        env: Dict[str, str] = None,
        timeout: int = 300,
        watchdog_threshold: int = 300,
    ):
        """
        Args:
            agent_path: agent 命令路径
            working_dir: 工作目录
            env: 环境变量（会合并系统环境变量）
            timeout: 单次响应超时（秒）
            watchdog_threshold: 看门狗沉默阈值（秒）
        """
        self.agent_path = agent_path
        self.working_dir = working_dir or os.getcwd()
        self.timeout = timeout
        self.watchdog_threshold = watchdog_threshold

        # 合并环境变量
        self.env = dict(os.environ)
        if env:
            self.env.update(env)

        self.proc: Optional[subprocess.Popen] = None
        self.watchdog: Optional[SilenceWatchdog] = None
        self.running = False
        self.lock = threading.Lock()

        # JSON-RPC 回调
        self._pending_requests: Dict[str, threading.Event] = {}
        self._pending_results: Dict[str, any] = {}
        self._output_callback: Optional[Callable[[str], None]] = None

        # 读取线程
        self.reader_thread: Optional[threading.Thread] = None

    def set_output_callback(self, cb: Callable[[str], None]):
        """设置输出回调（实时流式输出）"""
        self._output_callback = cb

    def _build_cmd(self) -> list:
        """构建启动命令"""
        cmd = [self.agent_path, "--acp"]
        return cmd

    def start(self) -> bool:
        """启动 ACP 进程"""
        with self.lock:
            if self.running:
                logger.warning("[ACP] 进程已在运行")
                return True

            try:
                logger.info(f"[ACP] 启动: {' '.join(self._build_cmd())}")
                self.proc = subprocess.Popen(
                    self._build_cmd(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self.working_dir,
                    env=self.env,
                    preexec_fn=os.setsid,  # 新建进程组，方便 kill
                )

                # 设置 stdout 为非阻塞读取
                fd = self.proc.stdout.fileno()
                fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

                # 设置 stderr 合并到 stdout（CLI 输出到 stderr）
                # 重定向 stderr -> stdout
                import subprocess
                # 实际上我们已经在 Popen 时分离了，重新用 tee 方式读取

                self.running = True

                # 启动看门狗
                self.watchdog = SilenceWatchdog(
                    proc=self.proc,
                    on_timeout=self._on_watchdog_timeout,
                    threshold=self.watchdog_threshold,
                )
                self.watchdog.start()

                # 启动读取线程
                self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
                self.reader_thread.start()

                logger.info(f"[ACP] 进程已启动 PID={self.proc.pid}")
                return True

            except Exception as e:
                logger.error(f"[ACP] 启动失败: {e}")
                self.running = False
                return False

    def _read_loop(self):
        """实时读取 stdout 的循环"""
        while self.running and self.proc and self.proc.poll() is None:
            try:
                ready, _, _ = select.select([self.proc.stdout], [], [], 0.5)
                if ready:
                    chunk = self.proc.stdout.read(4096)
                    if chunk:
                        text = chunk.decode("utf-8", errors="replace")
                        # 重置看门狗
                        if self.watchdog:
                            self.watchdog.record_output()
                        # 触发输出回调
                        if self._output_callback:
                            try:
                                self._output_callback(text)
                            except Exception as e:
                                logger.error(f"[ACP] 输出回调失败: {e}")
            except (OSError, IOError):
                break
            except Exception as e:
                logger.error(f"[ACP] 读取异常: {e}")
                break

    def _on_watchdog_timeout(self):
        """看门狗超时回调"""
        logger.warning("[ACP] 看门狗触发，重启进程")
        self.restart()

    def restart(self):
        """重启 ACP 进程"""
        logger.info("[ACP] 重启中...")
        self.stop()
        time.sleep(2)
        self.start()

    def stop(self):
        """停止 ACP 进程"""
        with self.lock:
            if not self.running:
                return

            self.running = False

            if self.watchdog:
                self.watchdog.stop()

            if self.proc:
                try:
                    pgid = os.getpgid(self.proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass

            self.proc = None
            logger.info("[ACP] 进程已停止")

    def send_request(self, method: str, params: dict = None, session_id: str = None) -> dict:
        """
        发送 JSON-RPC 2.0 请求并等待响应

        Args:
            method: RPC 方法名
            params: 参数
            session_id: 可选，用于标识会话

        Returns:
            响应结果
        """
        if not self.running or not self.proc:
            raise RuntimeError("ACP 进程未运行")

        request_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        event = threading.Event()
        self._pending_requests[request_id] = event

        try:
            # 发送请求
            msg = json.dumps(request) + "\n"
            self.proc.stdin.write(msg.encode("utf-8"))
            self.proc.stdin.flush()

            # 等待响应（带超时）
            if not event.wait(timeout=self.timeout):
                raise TimeoutError(f"请求超时 ({self.timeout}s)")

            return self._pending_results.pop(request_id, {})

        except Exception as e:
            logger.error(f"[ACP] 请求失败: {e}")
            raise

        finally:
            self._pending_requests.pop(request_id, None)
            self._pending_results.pop(request_id, None)

    def send_message(self, text: str, session_id: str = None) -> str:
        """
        发送消息并获取响应（简化接口）

        Args:
            text: 消息内容
            session_id: 会话 ID

        Returns:
            响应文本
        """
        params = {
            "message": {"role": "user", "content": text},
        }
        if session_id:
            params["session_id"] = session_id

        try:
            response = self.send_request("anthropic.messages.create", params)
            # 解析响应
            content = response.get("content", [])
            if isinstance(content, list):
                return "\n".join(
                    block.get("text", "") for block in content if block.get("type") == "text"
                )
            return str(response)
        except Exception as e:
            logger.error(f"[ACP] 发送消息失败: {e}")
            raise

    def is_alive(self) -> bool:
        """检查进程是否存活"""
        return self.running and self.proc and self.proc.poll() is None
