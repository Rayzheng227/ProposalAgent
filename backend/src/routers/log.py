# utils.py
import logging
import queue

# 创建一个全局队列用于存储日志
log_queue = queue.Queue()

class QueueLogHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        # 将日志记录放入队列
        self.log_queue.put(self.format(record))