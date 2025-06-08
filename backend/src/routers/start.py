from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from config import GCF, load_config

# 加载配置
load_config()

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

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI!"}



if __name__ == "__main__":
    uvicorn.run(app, host=GCF.server.ip, port=GCF.server.port)