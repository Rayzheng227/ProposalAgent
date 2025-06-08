import asyncio
import logging
import os

from fastapi import HTTPException, Depends
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from backend.src.routers.log import QueueLogHandler, log_queue
from config import GCF, load_config
from backend.src.agent.graph import ProposalAgent
from threadPool import get_executor
from concurrent.futures import ThreadPoolExecutor

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
async def download_md(file_name: str):
    # 获取当前文件的绝对路径
    current_file_path = Path(__file__).resolve()
    # 获取项目的根目录路径
    project_root = current_file_path.parents[3]  # 因为 start.py 在 ProposalAgent/backend/src/agent/routers 下
    # 构建输出文件夹的绝对路径
    output_dir = project_root / 'output'
    # 获取具体的 .md 文件路径
    file_path = output_dir / file_name
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=file_path, filename="downloaded_file.md", media_type='text/markdown')

@app.get("/logs")
async def stream_logs(executor : ThreadPoolExecutor = Depends(get_executor)):
    async def event_generator():
        while True:
            if not log_queue.empty():
                yield {"event": "log", "data": log_queue.get_nowait()}
            await asyncio.sleep(0.1)
    return EventSourceResponse(event_generator())

@app.get("/agent")
async def agent(research_question: str, executor : ThreadPoolExecutor = Depends(get_executor)):
    def agent_task():
        agent = ProposalAgent()
        agent.generate_proposal(research_question)
    executor.submit(agent_task)
    return


if __name__ == "__main__":
    uvicorn.run(app, host=GCF.server.ip, port=GCF.server.port)