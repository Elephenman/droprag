"""DropRAG 统一日志模块

使用标准 logging 模块替代 print，支持:
1. 控制台 + 文件双输出
2. 日志级别控制
3. 日志文件轮转
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

_loggers = {}


def get_logger(name: str = "droprag", level: str = "INFO",
               log_file: Optional[str] = None,
               max_bytes: int = 50 * 1024 * 1024,
               backup_count: int = 3) -> logging.Logger:
    """获取配置好的 logger

    Args:
        name: logger 名称
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_file: 日志文件路径，None 则仅控制台
        max_bytes: 日志文件最大字节数
        backup_count: 保留的备份文件数
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复添加 handler
    if logger.handlers:
        _loggers[name] = logger
        return logger

    # 控制台 handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(console)

    # 文件 handler (可选)
    if log_file:
        import os
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(file_handler)

    _loggers[name] = logger
    return logger


def setup_logging(level: str = "INFO", log_file: Optional[str] = None,
                  max_size_mb: int = 50, backup_count: int = 3):
    """全局日志配置（在 engine 启动时调用一次）"""
    root = get_logger("droprag", level, log_file,
                      max_bytes=max_size_mb * 1024 * 1024,
                      backup_count=backup_count)
    # 设置第三方库日志级别
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    return root
