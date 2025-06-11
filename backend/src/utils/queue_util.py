from collections import deque
from typing import Dict
from threading import Lock
from backend.src.entity.stream_mes import StreamMes


class QueueUtil:
    message_queues: Dict[str, deque] = {}
    _lock = Lock()  # 线程锁，确保并发安全

    @classmethod
    def new_queue(cls, proposal_id: str, max_len: int = 100) -> None:
        """
        创建指定ID的消息队列
        """
        with cls._lock:  # 加锁确保线程安全
            if proposal_id not in cls.message_queues:
                cls.message_queues[proposal_id] = deque(maxlen=max_len)

    @classmethod
    def push_mes(cls, stream_mes: StreamMes) -> None:
        """
        向指定ID的队列添加消息
        """
        proposal_id = stream_mes.proposal_id
        with cls._lock:
            if proposal_id in cls.message_queues:
                cls.message_queues[proposal_id].append(stream_mes)

    @classmethod
    def popleft_mes(cls, proposal_id: str) -> StreamMes | None:
        """
        获取指定ID的消息
        """
        this_queue = cls.message_queues[proposal_id]
        if this_queue and len(this_queue) > 0:
            return this_queue.popleft()
        return None

    @classmethod
    def del_queue(cls, proposal_id: str) -> None:
        """
        移除指定ID的队列
        """
        with cls._lock:
            cls.message_queues.pop(proposal_id, None)
