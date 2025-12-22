import logging
import logging.handlers
import os
import sys
from PySide6.QtCore import QObject, Signal

class LogSignal(QObject):
    """用于在 QtLogHandler 中发射信号的辅助类"""
    log_received = Signal(str, int)  # message, levelno

class QtLogHandler(logging.Handler):
    """自定义 Logging Handler，将日志记录发射为 Qt 信号"""
    def __init__(self, signal_emitter):
        super().__init__()
        self.signal_emitter = signal_emitter

    def emit(self, record):
        try:
            msg = self.format(record)
            # 发射信号，参数为格式化后的消息和日志级别
            self.signal_emitter.log_received.emit(msg, record.levelno)
        except Exception:
            self.handleError(record)

def setup_logging(log_dir="logs", max_bytes=5*1024*1024, backup_count=5):
    """
    配置全局日志系统
    :param log_dir: 日志文件存储目录
    :param max_bytes: 单个日志文件最大字节数
    :param backup_count: 保留的旧日志文件数量
    :return: LogSignal 实例，用于连接 UI槽函数
    """
    # 确保日志目录存在
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 创建信号发射器
    log_signal = LogSignal()

    # 获取 root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG) # 捕获所有级别的日志

    # 清除已有的 handlers (防止重复添加)
    if logger.handlers:
        logger.handlers.clear()

    # 通用格式化器
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')

    # 1. 控制台处理器 (StreamHandler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 2. 文件处理器 (RotatingFileHandler)
    log_file = os.path.join(log_dir, "app.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 3. Qt 处理器 (用于 UI 显示)
    qt_handler = QtLogHandler(log_signal)
    qt_handler.setLevel(logging.INFO) # UI 通常显示 INFO 及以上
    # UI 显示格式：时间 - 级别 - 消息
    qt_formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s', datefmt='%H:%M:%S')
    qt_handler.setFormatter(qt_formatter)
    logger.addHandler(qt_handler)

    logging.info("日志系统初始化完成")
    return log_signal

