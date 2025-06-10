from backend.src.utils.queue_util import StreamMes, QueueUtil
from langchain_core.messages import BaseMessageChunk
from typing import Iterator


def stream_mes_2_full_content(proposal_id: str, step: int, stream_res: Iterator[BaseMessageChunk]):
    """
    处理流式消息
    实时输出内容到消息队列
    返回完整的response
    """
    full_content = ""
    for chunk in stream_res:
        content =  chunk.content
        full_content += content
        QueueUtil.push_mes(StreamMes(proposal_id, step, content))
    return full_content.strip()
