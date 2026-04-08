"""
OpenClaw 风格的消息去重模块
基于 OpenClaw persistent-dedupe.ts 的 Python 实现

特点：
- 两层检查：内存(快速) → 磁盘(持久化)
- 文件锁防止并发写冲突
- 原子写入：先写临时文件再 rename
- 启动时从磁盘加载缓存（warmup）
- 相同消息在飞行中也会被拦截（inflight dedupe）
"""
import os
import json
import time
import fcntl
import errno
import shutil
import threading
from typing import Optional, Dict

# 默认配置
DEFAULT_TTL_MS = 1440 * 60 * 1000  # 24小时
DEFAULT_MEMORY_MAX_SIZE = 10000
DEFAULT_FILE_MAX_ENTRIES = 50000


class DedupeCache:
    """内存中的 TTL Cache，带 LRU 驱逐"""

    def __init__(self, ttl_ms: int = DEFAULT_TTL_MS, max_size: int = DEFAULT_MEMORY_MAX_SIZE):
        self.ttl_ms = ttl_ms
        self.max_size = max_size
        self._cache: Dict[str, float] = {}  # key -> timestamp
        self._lock = threading.Lock()

    def _prune(self, now: float):
        """清理过期 + 超量条目"""
        cutoff = now - self.ttl_ms if self.ttl_ms > 0 else None

        # 删除过期
        if cutoff is not None:
            expired = [k for k, ts in self._cache.items() if ts < cutoff]
            for k in expired:
                del self._cache[k]

        # LRU 驱逐：超量时删除最老的
        if self.max_size > 0 and len(self._cache) > self.max_size:
            sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k])
            for k in sorted_keys[:len(self._cache) - self.max_size]:
                del self._cache[k]

    def check(self, key: str, now: Optional[float] = None) -> bool:
        """检查并记录。如果存在返回 True（应跳过）"""
        if not key:
            return False
        now = now or time.time() * 1000

        with self._lock:
            existing = self._cache.get(key)
            if existing is not None:
                if self.ttl_ms > 0 and now - existing >= self.ttl_ms:
                    del self._cache[key]
                else:
                    # 刷新访问时间（touch）
                    del self._cache[key]
                    self._cache[key] = now
                    return True

            # 不存在，添加
            self._cache[key] = now
            self._prune(now)
            return False

    def clear(self):
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


def _sanitize_data(value: dict) -> dict:
    """只保留有效的 number 类型 timestamp"""
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if isinstance(v, (int, float)) and v > 0}


def _prune_data(data: dict, now: float, ttl_ms: int, max_entries: int):
    """删除过期 + 超量条目"""
    # 删除过期
    if ttl_ms > 0:
        expired = [k for k, ts in data.items() if now - ts >= ttl_ms]
        for k in expired:
            del data[k]

    # 按时间排序，删除最老的直到在限制内
    keys = list(data.keys())
    if len(keys) <= max_entries:
        return
    keys.sort(key=lambda k: data[k])
    for k in keys[:len(keys) - max_entries]:
        del data[k]


def _resolve_dedup_file(dedup_dir: str, namespace: str = "global") -> str:
    """解析命名空间对应的去重文件路径"""
    return os.path.join(dedup_dir, f"dedup_{namespace}.json")


class PersistentDedupe:
    """
    OpenClaw 风格持久化去重
    两层：内存Cache + 文件锁保护的磁盘存储
    """

    def __init__(
        self,
        dedup_dir: str,
        ttl_ms: int = DEFAULT_TTL_MS,
        memory_max_size: int = DEFAULT_MEMORY_MAX_SIZE,
        file_max_entries: int = DEFAULT_FILE_MAX_ENTRIES,
        namespace: str = "global"
    ):
        self.dedup_dir = dedup_dir
        self.ttl_ms = ttl_ms
        self.memory_max_size = memory_max_size
        self.file_max_entries = file_max_entries
        self.namespace = namespace

        os.makedirs(dedup_dir, exist_ok=True)
        self._file_path = _resolve_dedup_file(dedup_dir, namespace)
        self._memory = DedupeCache(ttl_ms, memory_max_size)
        self._inflight: Dict[str, tuple] = {}  # key -> (future, result)
        self._inflight_lock = threading.Lock()

    def warmup(self) -> int:
        """启动时从磁盘加载缓存到内存，返回加载数量"""
        if not os.path.exists(self._file_path):
            return 0

        now = time.time() * 1000
        try:
            with open(self._file_path, 'r') as f:
                data = _sanitize_data(json.load(f))

            loaded = 0
            for key, ts in data.items():
                if self.ttl_ms > 0 and now - ts >= self.ttl_ms:
                    continue
                scoped_key = f"{self.namespace}:{key}"
                self._memory.check(scoped_key, ts)
                loaded += 1
            return loaded
        except (json.JSONDecodeError, IOError) as e:
            print(f"[Dedup] warmup failed: {e}")
            return 0

    def _check_and_record_inner(self, key: str, now: float) -> bool:
        """
        内部：文件锁 + 原子写入
        返回 True = 已存在（应跳过），False = 新记录（应处理）
        """
        # 内存快速检查
        scoped_key = f"{self.namespace}:{key}"
        if self._memory.check(scoped_key, now):
            return True

        # 文件锁
        lock_path = self._file_path + ".lock"
        lock_fd = None
        try:
            lock_fd = open(lock_path, 'w')
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)

            # 读取现有数据
            if os.path.exists(self._file_path):
                with open(self._file_path, 'r') as f:
                    data = _sanitize_data(json.load(f))
            else:
                data = {}

            seen_at = data.get(key)
            if seen_at is not None and (self.ttl_ms <= 0 or now - seen_at < self.ttl_ms):
                # 已存在且未过期
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                return True

            # 写入新记录
            data[key] = now
            _prune_data(data, now, self.ttl_ms, self.file_max_entries)

            # 原子写入：先写临时文件再 rename
            tmp_path = self._file_path + ".tmp"
            with open(tmp_path, 'w') as f:
                json.dump(data, f)
            os.rename(tmp_path, self._file_path)

            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            return False

        except IOError as e:
            if lock_fd:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                except:
                    pass
            if e.errno == errno.EWOULDBLOCK:
                # 锁被占用，当作已处理
                return True
            print(f"[Dedup] disk error, fallback to memory: {e}")
            return True
        finally:
            if lock_fd:
                lock_fd.close()

    def check_and_record(self, message_id: str) -> bool:
        """
        检查消息是否已处理。
        返回 True = 重复（应跳过），False = 新消息（应处理）
        """
        key = message_id.strip()
        if not key:
            return True

        # inflight 检查：同一消息同时到来，只让一个通过
        with self._inflight_lock:
            if key in self._inflight:
                return True  # 正在处理中
            # 记录当前请求
            self._inflight[key] = (threading.current_thread(), None)

        try:
            now = time.time() * 1000
            result = self._check_and_record_inner(key, now)
            return result
        finally:
            with self._inflight_lock:
                self._inflight.pop(key, None)

    def has_recorded(self, message_id: str) -> bool:
        """只检查，不记录"""
        key = message_id.strip()
        if not key:
            return False
        scoped_key = f"{self.namespace}:{key}"
        now = time.time() * 1000
        return self._memory.check(scoped_key, now)

    def memory_size(self) -> int:
        return self._memory.size()
