import asyncio
import builtins
import datetime

import uvicorn
import websockets
from fastapi import FastAPI

from config.config import PORT_API, PORT_WS
from app.communication.websocket import handle_client
from app.orchestration.orchestrator import Orchestrator

_original_print = builtins.print
def _ts_print(*args, **kwargs):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    _original_print(f"{ts}", *args, **kwargs)
builtins.print = _ts_print

app = FastAPI()
orchestrator = Orchestrator()


@app.get("/api/check")
async def check():
    return {"message": "Nova is alive!"}


@app.get("/api/test")
async def test():
    return {"message": "Nova is alive!"}


async def main():
    print("Nova server starting...")

    await orchestrator.start()

    ws_server = websockets.serve(handle_client, "0.0.0.0", PORT_WS)
    api_server = uvicorn.Server(uvicorn.Config(app, host="192.168.1.92", port=PORT_API))

    print(f"WebSocket running on port {PORT_WS}")
    print(f"API running on port {PORT_API}")
    print("Camera + Face Monitoring active")
    print("Nova is ready.")

    try:
        async with ws_server:
            await api_server.serve()
    finally:
        await orchestrator.stop()


asyncio.run(main())
