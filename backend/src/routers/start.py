import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

import uvicorn
from fastapi import FastAPI
from fastapi import Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from backend.src.routers.log import QueueLogHandler, log_queue
from config import GCF, load_config
from threadPool import get_executor
from backend.src.services.agent_service import agent_service
from backend.src.services.logs_service import logs_service
from backend.src.services.md_services import md_services

# 加载配置
load_config()

# 创建 FastAPI 实例
app = FastAPI()
# backend/src/main.py

# 设置日志级别
logging.basicConfig(level=logging.INFO)

# 添加自定义日志处理器
queue_handler = QueueLogHandler(log_queue)
queue_handler.setLevel(logging.INFO)  # 只处理 INFO 日志
logging.getLogger().addHandler(queue_handler)  # 或者添加到 root logger

# 允许所有来源的跨域设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI!"}

#下载md文件
@app.get("/download_md")
async def download_md(research_field: str, uuid: str):
    path = md_services(research_field, uuid)
    return FileResponse(path=path, filename="downloaded_file.md", media_type='text/markdown')

@app.get("/logs")
async def stream_logs():
    logs_service()
    return EventSourceResponse(logs_service())

@app.get("/agent")
async def agent(research_field: str, executor : ThreadPoolExecutor = Depends(get_executor)):
    uuid__hex = uuid.uuid4().hex
    def agent_task():
        agent_service(research_field, uuid__hex)
    executor.submit(agent_task)
    return {"Proposal_id" : uuid__hex}


if __name__ == "__main__":
    uvicorn.run(app, host=GCF.server.ip, port=GCF.server.port)