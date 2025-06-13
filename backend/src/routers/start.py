import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from backend.src.services.agent_service import agent_service
from backend.src.entity.r import R
from backend.src.utils.queue_util import QueueUtil
from backend.src.entity.stream_mes import StreamMes
import asyncio

# 创建 FastAPI 实例
app = FastAPI()
# 允许所有来源的跨域设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

thread_pool = ThreadPoolExecutor(max_workers=5)


@app.post("/sendQuery")
async def send_query(data: dict):
    """
    发送问题
    data:{
        query: str # 问题
        historyId: str # 前端需要的唯一标记一个历史记录的id
        isClarification: bool # 是否是回答问题
    }
    """
    if not data.get("query"):
        return R.error_with_mes("请输入具体的问题")
    if not data.get("historyId"):
        return R.error_with_mes("历史记录异常")

    if data["isClarification"]:
        QueueUtil.set_clarification(data["historyId"], data["query"])
    else:
        def agent_task():
            agent_service(data["historyId"], data["query"])

        thread_pool.submit(agent_task)

    return R.ok()


@app.websocket("/ws/{history_id}")
async def stream_mes(websocket: WebSocket, history_id: str):
    """
    给指定的history_id的ws连接实时回传消息
    """
    await websocket.accept()
    try:
        # 持续从队列消费消息并发送给客户端
        while True:
            mes: StreamMes = QueueUtil.popleft_mes(history_id)
            if mes is None:
                await asyncio.sleep(0.1)  # 队列空时短暂等待
                continue
            # 发送正常消息
            await websocket.send_text(json.dumps(mes.to_dict()))
            if mes.is_finish: break

    except WebSocketDisconnect:
        print(f"连接断开: {history_id}")
    finally:
        # 清理资源
        QueueUtil.del_queue(history_id)
        await websocket.close()


@app.post("/checkFileExist")
async def checkFileExist(data: dict):
    """
    检查要下载文件是否存在
    data:{
        fileType: str # "pdf"或者"md"
        historyId: str # 前端需要的唯一标记一个历史记录的id
    }
    """
    if not data.get("fileType"):
        return None
    if not data.get("historyId"):
        return None
    file_type = data["fileType"]

    # file_name = f"Research_Proposal_{data['historyId']}.{'pdf' if file_type == 'pdf' else 'md'}"
    file_name = "111.md"
    if file_type == 'pdf':
        file_path = Path(__file__).parent.parent.parent.parent / "exporter/pdf_output" / file_name
    else:
        file_path = Path(__file__).parent.parent.parent.parent / "output" / file_name
    if not os.path.exists(file_path):
        return R.error_with_mes("文件不存在！请稍后再尝试下载")
    return R.ok()

@app.post("/download")
async def download(data: dict):
    """
    下载文件
    data:{
        fileType: str # "pdf"或者"md"
        historyId: str # 前端需要的唯一标记一个历史记录的id
    }
    """
    if not data.get("fileType"):
        return None
    if not data.get("historyId"):
        return None
    file_type = data["fileType"]
    file_name = f"Research_Proposal_{data['historyId']}.{file_type}"
    if file_type == 'pdf':
        file_path = Path(__file__).parent.parent.parent.parent / "exporter/pdf_output" / file_name
    else:
        file_path = Path(__file__).parent.parent.parent.parent / "output" / file_name

    if not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="File not found")
    return FileResponse(path=file_path, filename=file_name)
