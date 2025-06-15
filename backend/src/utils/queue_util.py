from collections import deque
from typing import Dict, Optional
from threading import Lock
from src.entity.stream_mes import StreamMes


class QueueUtil:
    message_queues: Dict[str, deque] = {}
    _lock = Lock()  # 线程锁，确保并发安全
    user_clarifications: Dict[str, str] = {}

    @classmethod
    def set_clarification(cls, proposal_id: str, clarification: str) -> None:
        cls.user_clarifications[proposal_id] = clarification

    @classmethod
    def get_clarification(cls, proposal_id: str) -> str:
        clarify = cls.user_clarifications.get(proposal_id, "")
        if not clarify:
            return ""
        else:
            cls.user_clarifications[proposal_id] = ""
            return clarify

    @classmethod
    def push_mes(cls, stream_mes: StreamMes) -> bool:
        """
        向指定ID的队列添加消息
        返回是否成功添加
        """
        proposal_id = stream_mes.proposal_id
        with cls._lock:
            # 确保队列存在
            if proposal_id not in cls.message_queues:
                cls.message_queues[proposal_id] = deque(maxlen=100)

            queue = cls.message_queues[proposal_id]
            queue.append(stream_mes)
            return True

    @classmethod
    def popleft_mes(cls, proposal_id: str) -> Optional[StreamMes]:
        """
        获取指定ID的消息，若对应id不存在则先创建该id的队列
        """
        with cls._lock:  # 加锁确保线程安全
            if proposal_id not in cls.message_queues:
                cls.message_queues[proposal_id] = deque(maxlen=100)

            queue = cls.message_queues[proposal_id]
            if queue:
                return queue.popleft()
            return None

    @classmethod
    def del_queue(cls, proposal_id: str) -> None:
        """移除指定ID的队列"""
        with cls._lock:
            cls.message_queues.pop(proposal_id, None)
