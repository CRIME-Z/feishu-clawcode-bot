"""
Silence Watchdog - 检测进程卡住并自动重启
"""
import threading
import time
import signal
import logging
import os

logger = logging.getLogger(__name__)


class SilenceWatchdog:
    """
    沉默看门狗：
    - 实时监控子进程 stdout/stderr
    - 追踪最后输出时间戳
    - 超过阈值自动 SIGKILL 并重启
    """

    def __init__(self, proc, on_timeout, threshold=300, check_interval=10):
        """
        Args:
            proc: subprocess.Popen 对象
            on_timeout: 超时回调函数
            threshold: 沉默阈值（秒），默认 300（5分钟）
            check_interval: 检查间隔（秒）
        """
        self.proc = proc
        self.on_timeout = on_timeout
        self.threshold = threshold
        self.check_interval = check_interval
        self.last_output_ts = time.time()
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

    def record_output(self):
        """任何输出时调用，重置计时器"""
        with self.lock:
            self.last_output_ts = time.time()

    def start(self):
        """启动看门狗"""
        self.running = True
        self.last_output_ts = time.time()
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()
        logger.info(f"[Watchdog] 启动，阈值 {self.threshold} 秒")

    def stop(self):
        """停止看门狗"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _watch_loop(self):
        """看门狗主循环"""
        while self.running:
            time.sleep(self.check_interval)

            with self.lock:
                elapsed = time.time() - self.last_output_ts

            if elapsed >= self.threshold:
                logger.warning(f"[Watchdog] 沉默 {elapsed:.0f}s，超过阈值 {self.threshold}s，准备 kill")
                self._kill_process()
                self.running = False
                try:
                    self.on_timeout()
                except Exception as e:
                    logger.error(f"[Watchdog] on_timeout 回调失败: {e}")

    def _kill_process(self):
        """强制杀死进程组"""
        try:
            pgid = os.getpgid(self.proc.pid)
            os.killpg(pgid, signal.SIGKILL)
            logger.warning(f"[Watchdog] 已发送 SIGKILL 到进程组 {pgid}")
        except (ProcessLookupError, OSError) as e:
            logger.error(f"[Watchdog] kill 失败: {e}")
