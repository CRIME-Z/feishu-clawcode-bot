"""
Per-Session Queue Manager - 每个 session 独立的队列
"""
import threading
import logging
from collections import defaultdict
from typing import Dict, List, Tuple, Callable, Optional

logger = logging.getLogger(__name__)


class QueueManager:
    """
    Per-Session 并行队列：
    - 同一 session：串行处理（先来先服务）
    - 不同 session：完全并行
    - 每个 session 有独立的处理线程
    """

    def __init__(self, worker_fn: Callable[[str, str, str], None]):
        """
        Args:
            worker_fn: 处理函数签名 (session_id, chat_id, text, msg_id) -> None
        """
        self.worker_fn = worker_fn
        self.queues: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)  # session_id -> [(chat_id, text, msg_id), ...]
        self.locks: Dict[str, threading.Lock] = {}
        self.threads: Dict[str, threading.Thread] = {}
        self.global_lock = threading.Lock()

    def _get_session_lock(self, session_id: str) -> threading.Lock:
        """获取或创建 session 的锁"""
        with self.global_lock:
            if session_id not in self.locks:
                self.locks[session_id] = threading.Lock()
            return self.locks[session_id]

    def enqueue(self, session_id: str, chat_id: str, text: str, msg_id: str):
        """
        将消息加入对应 session 的队列
        """
        sess_lock = self._get_session_lock(session_id)

        with sess_lock:
            self.queues[session_id].append((chat_id, text, msg_id))
            queue_len = len(self.queues[session_id])

        # 检查是否已有线程在跑这个 session
        with self.global_lock:
            should_start = (
                session_id not in self.threads
                or not self.threads[session_id].is_alive()
            )

            if should_start:
                t = threading.Thread(
                    target=self._process_session,
                    args=(session_id,),
                    daemon=True
                )
                self.threads[session_id] = t
                t.start()

        logger.info(f"[Queue] session={session_id[:8]}..., 队列长度={queue_len}, 新线程={should_start}")

    def _process_session(self, session_id: str):
        """
        每个 session 独立的处理线程，不停地从自己的队列里取消息处理
        """
        sess_lock = self._get_session_lock(session_id)

        while True:
            # 从队列取任务
            with sess_lock:
                if not self.queues[session_id]:
                    # 队列空了，线程退出
                    break
                chat_id, text, msg_id = self.queues[session_id].pop(0)

            try:
                self.worker_fn(session_id, chat_id, text, msg_id)
            except Exception as e:
                logger.error(f"[Queue] 处理失败 session={session_id[:8]}...: {e}")

    def size(self, session_id: str) -> int:
        """查看某个 session 的队列长度"""
        with self._get_session_lock(session_id):
            return len(self.queues.get(session_id, []))

    def total_size(self) -> int:
        """查看总队列长度"""
        with self.global_lock:
            return sum(len(q) for q in self.queues.values())
