import uvicorn
from src.routers.start import app
from src.routers.config import ServerConfig

if __name__ == "__main__":
    serverConfig = ServerConfig(load_config=True)
    uvicorn.run(app, host=serverConfig.ip, port=serverConfig.port)
