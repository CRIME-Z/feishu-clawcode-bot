"""
ClawCode 执行器封装 - V2 版本
整合 ACP 持久进程 + Per-Session 队列 + 看门狗
"""
import os
import logging
import threading
import time
from typing import Optional

from .acp_agent import ACPAgent
from .queue_manager import QueueManager
from feishu_client import FeishuClient

logger = logging.getLogger(__name__)


class ClawCodeExecutorV2:
    """
    ClawCode 执行器 V2：
    - ACP 持久进程（常驻 + 自动重连）
    - Per-Session 并行队列
    - 实时流式输出回调
    - 看门狗（5分钟沉默自动重启）
    """

    def __init__(self, config: dict = None):
        """
        Args:
            config: 配置字典
                - agent_path: agent 命令路径（默认 "agent"）
                - working_dir: 工作目录
                - env: 环境变量
                - watchdog_threshold: 看门狗阈值（秒）
                - feishu_client: FeishuClient 实例
        """
        self.config = config or {}
        self.agent_path = self.config.get("agent_path", "agent")
        self.working_dir = self.config.get("working_dir", os.getcwd())
        self.env = self.config.get("env", {})
        self.watchdog_threshold = self.config.get("watchdog_threshold", 300)
        self.feishu_client: Optional[FeishuClient] = self.config.get("feishu_client")

        # 状态
        self.available = False
        self._started = False
        self._lock = threading.Lock()

        # 初始化 ACP Agent
        self._agent: Optional[ACPAgent] = None

        # 初始化队列管理器（worker 延迟绑定）
        self._queue_manager: Optional[QueueManager] = None

    def _check_available(self) -> bool:
        """检查 agent 是否可用"""
        import shutil
        return shutil.which(self.agent_path) is not None

    def start(self) -> bool:
        """启动执行器"""
        with self._lock:
            if self._started:
                return True

            if not self._check_available():
                logger.error(f"[ExecutorV2] agent 未找到: {self.agent_path}")
                return False

            # 合并环境变量
            env = dict(os.environ)
            env.update(self.env)

            # 创建 ACP Agent
            self._agent = ACPAgent(
                agent_path=self.agent_path,
                working_dir=self.working_dir,
                env=env,
                watchdog_threshold=self.watchdog_threshold,
            )

            # 设置流式输出回调
            self._agent.set_output_callback(self._on_stream_output)

            # 启动
            if not self._agent.start():
                logger.error("[ExecutorV2] ACP Agent 启动失败")
                return False

            # 创建队列管理器
            self._queue_manager = QueueManager(worker_fn=self._process_message)

            self._started = True
            self.available = True
            logger.info("[ExecutorV2] 启动成功")
            return True

    def stop(self):
        """停止执行器"""
        with self._lock:
            if not self._started:
                return

            if self._agent:
                self._agent.stop()
                self._agent = None

            self._started = False
            self.available = False
            logger.info("[ExecutorV2] 已停止")

    def is_available(self) -> bool:
        """检查执行器是否可用"""
        return self.available and self._agent and self._agent.is_alive()

    def _on_stream_output(self, text: str):
        """流式输出回调（可继承重写）"""
        # 目前主要是触发看门狗重置
        pass

    def _process_message(self, session_id: str, chat_id: str, text: str, msg_id: str):
        """
        处理单条消息（队列 worker 函数）
        """
        if not self.is_alive():
            logger.error(f"[ExecutorV2] Agent 未运行，拒绝处理")
            if self.feishu_client:
                try:
                    self.feishu_client.reply_message(
                        msg_id,
                        "⚠️ Agent 未运行，请联系管理员"
                    )
                except Exception:
                    pass
            return

        try:
            logger.info(f"[ExecutorV2] 处理消息 session={session_id[:8]}..., msg_id={msg_id[:8]}...")

            # 发送消息
            response = self._agent.send_message(text, session_id=session_id)

            # 回复用户
            if self.feishu_client:
                self.feishu_client.reply_message(msg_id, self._truncate(response))

            logger.info(f"[ExecutorV2] 处理完成 session={session_id[:8]}...")

        except TimeoutError as e:
            logger.error(f"[ExecutorV2] 处理超时: {e}")
            if self.feishu_client:
                self.feishu_client.reply_message(msg_id, f"⚠️ 执行超时（>{self._agent.timeout}s）")
        except Exception as e:
            logger.error(f"[ExecutorV2] 处理异常: {e}")
            if self.feishu_client:
                self.feishu_client.reply_message(msg_id, f"⚠️ 执行失败: {str(e)}")

    def enqueue(self, session_id: str, chat_id: str, text: str, msg_id: str):
        """
        将消息加入队列
        """
        if not self._started:
            logger.error("[ExecutorV2] 执行器未启动")
            return

        self._queue_manager.enqueue(session_id, chat_id, text, msg_id)

    def restart(self):
        """重启 ACP Agent"""
        if self._agent:
            self._agent.restart()

    @staticmethod
    def _truncate(text: str, max_length: int = 4000) -> str:
        """截断文本"""
        if len(text) <= max_length:
            return text
        return text[:max_length] + f"\n\n[...还有 {len(text) - max_length} 字符]"
