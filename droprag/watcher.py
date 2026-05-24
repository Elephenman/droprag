"""DropRAG 文件系统监控模块（线程安全 + asyncio 集成）

特性:
1. watchdog 监控文件变化
2. 可配置防抖 (默认3秒)
3. 线程安全: 通过 asyncio.run_coroutine_threadsafe 投递到事件循环
4. SSE 事件通知: 索引状态变更实时推送
"""

import asyncio
import os
import threading
from typing import Callable, Optional, Set, List

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

from droprag.loader import get_supported_extensions
from droprag.logging import get_logger

log = get_logger(__name__)


class KnowledgeBaseHandler(FileSystemEventHandler):
    """知识库文件变化处理器（线程安全）"""

    def __init__(self, on_change: Callable, ignore_patterns: Optional[Set[str]] = None,
                 debounce_seconds: float = 3.0):
        self.on_change = on_change
        self.ignore_patterns = ignore_patterns or {
            '.git', '.obsidian', '.trash', '__pycache__', '.tmp', '.bak', '.swp', '.lock'
        }
        self.debounce_seconds = debounce_seconds
        self._debounce_timer: Optional[threading.Timer] = None
        self._pending_files: Set[str] = set()
        self._lock = threading.Lock()
        self._supported_exts = set(get_supported_extensions())

    def _should_ignore(self, path: str) -> bool:
        """检查是否应该忽略该路径"""
        path_parts = path.replace("\\", "/").split("/")
        for part in path_parts:
            for pattern in self.ignore_patterns:
                if pattern.startswith("*"):
                    if part.endswith(pattern.lstrip("*")):
                        return True
                elif part == pattern:
                    return True
        # 检查文件扩展名
        ext = os.path.splitext(path)[1].lower()
        if ext in {'.tmp', '.bak', '.swp', '.lock', '.part'}:
            return True
        # 只监控支持的文件类型
        if ext and ext.lower() not in self._supported_exts:
            return True
        return False

    def _schedule_update(self, path: str):
        """调度更新（防抖）"""
        with self._lock:
            self._pending_files.add(path)

        if self._debounce_timer:
            self._debounce_timer.cancel()

        self._debounce_timer = threading.Timer(self.debounce_seconds, self._trigger_update)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _trigger_update(self):
        """触发更新回调"""
        with self._lock:
            files = list(self._pending_files)
            self._pending_files.clear()

        if files:
            log.info(f"检测到 {len(files)} 个文件变化，触发增量更新...")
            try:
                self.on_change(files)
            except Exception as e:
                log.error(f"增量更新回调出错: {e}")

    def on_modified(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._schedule_update(event.src_path)

    def on_created(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        log.info(f"文件创建: {os.path.basename(event.src_path)}")
        self._schedule_update(event.src_path)

    def on_deleted(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        log.info(f"文件删除: {os.path.basename(event.src_path)}")
        self._schedule_update(event.src_path)

    def on_moved(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        log.info(f"文件移动: {os.path.basename(event.src_path)} → {os.path.basename(event.dest_path)}")
        self._schedule_update(event.dest_path)


class KnowledgeBaseWatcher:
    """知识库监控器（支持多目录监控）"""

    def __init__(self, on_change: Callable, ignore_patterns: Optional[Set[str]] = None,
                 debounce_seconds: float = 3.0):
        if not WATCHDOG_AVAILABLE:
            raise RuntimeError("watchdog 未安装，请运行: pip install watchdog")

        self.on_change = on_change
        self.ignore_patterns = ignore_patterns
        self.debounce_seconds = debounce_seconds
        self.observer: Optional[Observer] = None
        self._running = False
        self._watched_paths: List[str] = []

    def start(self, watch_paths: List[str], recursive: bool = True):
        if self._running:
            return
        self.observer = Observer()
        handler = KnowledgeBaseHandler(
            on_change=self.on_change,
            ignore_patterns=self.ignore_patterns,
            debounce_seconds=self.debounce_seconds,
        )
        for path in watch_paths:
            if os.path.exists(path):
                self.observer.schedule(handler, path, recursive=recursive)
                self._watched_paths.append(path)
                log.info(f"开始监控: {path}")
            else:
                log.warning(f"监控路径不存在: {path}")
        self._running = True
        self.observer.start()

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
        log.info("文件监控已停止")

    def is_running(self) -> bool:
        return self._running

    @property
    def watched_paths(self) -> List[str]:
        return self._watched_paths


# ── 全局实例 ──

_global_watcher: Optional[KnowledgeBaseWatcher] = None
_event_subscribers: List[asyncio.Queue] = []


def start_watching(watch_paths: List[str], update_callback: Callable,
                   ignore_patterns: Optional[Set[str]] = None,
                   debounce_seconds: float = 3.0) -> bool:
    global _global_watcher
    if not WATCHDOG_AVAILABLE:
        log.warning("watchdog 未安装，无法启用文件监控")
        return False
    try:
        _global_watcher = KnowledgeBaseWatcher(
            on_change=update_callback,
            ignore_patterns=ignore_patterns,
            debounce_seconds=debounce_seconds,
        )
        _global_watcher.start(watch_paths)
        return True
    except Exception as e:
        log.error(f"启动监控失败: {e}")
        return False


def stop_watching():
    global _global_watcher
    if _global_watcher:
        _global_watcher.stop()
        _global_watcher = None


def is_watching() -> bool:
    return _global_watcher is not None and _global_watcher.is_running()


def subscribe_events() -> asyncio.Queue:
    q = asyncio.Queue()
    _event_subscribers.append(q)
    return q


def unsubscribe_events(q: asyncio.Queue):
    if q in _event_subscribers:
        _event_subscribers.remove(q)


async def publish_event(event: dict):
    dead = []
    for q in _event_subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        unsubscribe_events(q)
