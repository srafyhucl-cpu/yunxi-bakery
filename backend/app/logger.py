"""
日志工具。

使用标准库 logging，输出结构化日志到 stdout。
所有模块通过 setup_logger 获取同名 logger 实例。
"""

import logging
import sys


def setup_logger(level: str = "info") -> logging.Logger:
    """初始化并返回 yunxi_bot 日志器，避免重复添加 handler。"""
    logger = logging.getLogger("yunxi_bot")
    logger.setLevel(getattr(logging, level.upper()))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s  %(levelname)s  %(name)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    if not logger.handlers:
        logger.addHandler(handler)
    return logger
