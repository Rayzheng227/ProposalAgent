import asyncio
from backend.src.routers.log import log_queue

async def logs_service():
    while True:
        if not log_queue.empty():
            yield {"event": "log", "data": log_queue.get_nowait()}
        await asyncio.sleep(0.1)