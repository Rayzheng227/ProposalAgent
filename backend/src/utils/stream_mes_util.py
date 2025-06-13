from src.entity.stream_mes import StreamAnswerMes, StreamClarifyMes
from src.utils.queue_util import QueueUtil
from langchain_core.messages import BaseMessageChunk
from typing import Iterator
import time


class StreamUtil:
    @staticmethod
    def transfer_stream_answer_mes(stream_res: Iterator[BaseMessageChunk], proposal_id: str, step: int, title: str):
        """
        处理流式消息
        实时输出内容到消息队列
        返回完整的response
        """
        full_content = ""
        for chunk in stream_res:
            content = chunk.content
            full_content += content
            QueueUtil.push_mes(StreamAnswerMes(proposal_id, step, title, content))
        return full_content.strip()

    @staticmethod
    def transfer_stream_clarify_mes(stream_res: Iterator[BaseMessageChunk], proposal_id: str):
        """
        处理流式消息
        实时输出内容到消息队列
        返回完整的response
        """
        start_time = time.time()
        full_content = ""
        for chunk in stream_res:
            content = chunk.content
            full_content += content
            QueueUtil.push_mes(StreamClarifyMes(proposal_id, content))
        QueueUtil.push_mes(
            StreamClarifyMes(proposal_id, "\n\n✅ 生成完毕，共耗时 %.2fs" % (time.time() - start_time), is_finish=True))
        return full_content.strip()
