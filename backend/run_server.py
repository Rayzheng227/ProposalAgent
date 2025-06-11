import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from src.routers.start import app
from src.routers.config import GCF

if __name__ == "__main__":
    uvicorn.run(app, host=GCF.server.ip, port=GCF.server.port)