import asyncio
import json
import time

import webrtcvad
import websockets

from app.vad.vad_detection import detect_speech

CHUNK_SIZE = 512
AUDIO_FILE = "data/output_audio/response.wav"
ws = None
clients = set()
RATE = 24000
FRAME_MS = 20
FRAME_SIZE = int(RATE * FRAME_MS / 1000)

vad = webrtcvad.Vad(3)

VOLUME_THRESHOLD = 600
SPEECH_CONFIRM_FRAMES = 5
SILENCE_LIMIT = int(2000 / FRAME_MS)


async def handle_client(websocket):
    global ws
    ws = websocket
    clients.add(websocket)

    addr = websocket.remote_address
    print(f"[WS] ✓ ESP32 connected from {addr}")
    print(f"[WS] Total clients: {len(clients)}")
    total_bytes = 0
    msg_count = 0

    try:
        async for message in websocket:
            if isinstance(message, str):
                print(f"[WS] ◀ Text from ESP32: '{message}'")
                if message == "play_test":
                    print("[WS] play_test received → streaming audio")
                    await stream_audio()
                if message == "Hello from ESP":
                    print("[WS] Received greeting from ESP!")

            if isinstance(message, bytes):
                msg_count += 1
                total_bytes += len(message)
                if msg_count % 50 == 0:
                    print(f"[WS] Received {msg_count} audio frames ({total_bytes/1024:.0f} KB from {addr})")
                await detect_speech(message)

    except websockets.exceptions.ConnectionClosed:
        print(f"[WS] ✗ ESP32 disconnected ({addr}, {total_bytes/1024:.0f} KB received)")

    finally:
        clients.discard(websocket)


async def send_websocket_message(message):
    global ws
    if ws is None:
        print("[WS] ⚠ No active WebSocket — cannot send message!")
        return
    try:
        await ws.send(message)
        print(f"[WS] ▶ Sent to ESP32: '{message}'")
    except websockets.exceptions.ConnectionClosed:
        print("[WS] ✗ Client disconnected while sending!")
        ws = None


async def broadcast(data):
    for client in clients:
        try:
            payload = json.dumps(data)
            print(f"[WS] ▶ Broadcast to {client.remote_address}: {payload}")
            await client.send(payload)
        except websockets.exceptions.ConnectionClosed:
            clients.discard(client)
            print("[WS] Removed disconnected client during broadcast!")


def get_WSconnection():
    return ws


async def stream_audio(AUDIO_FILE="data/output_audio/response.wav"):
    websocket = get_WSconnection()
    if websocket is None:
        print("[WS] ⚠ Cannot stream audio: no ESP32 connected")
        return

    print(f"[WS] ▶ Streaming audio file: {AUDIO_FILE}")
    t0 = time.time()

    await websocket.send("audio_start")
    print("[WS] Sent: audio_start")

    total = 0
    chunks = 0
    with open(AUDIO_FILE, "rb") as f:
        f.seek(44)
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            if len(chunk) % 2 != 0:
                chunk += b'\x00'
            await websocket.send(chunk)
            total += len(chunk)
            chunks += 1
            await asyncio.sleep(0.01)

    await asyncio.sleep(2)
    await websocket.send("audio_end")
    elapsed = time.time() - t0
    print(f"[WS] ✅ Audio streamed: {total/1024:.1f} KB in {chunks} chunks ({elapsed:.1f}s)")
    await websocket.send("start_stream")
    print("[WS] Sent: start_stream")


async def stream_music(AUDIO_FILE="assets/music/song.wav"):
    websocket = get_WSconnection()
    if websocket is None:
        print("[WS] ⚠ Cannot stream music: no ESP32 connected")
        return

    print(f"[WS] ▶ Streaming music: {AUDIO_FILE}")
    t0 = time.time()

    await websocket.send("audio_start")

    total = 0
    chunks = 0
    with open(AUDIO_FILE, "rb") as f:
        f.seek(44)
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            if len(chunk) % 2 != 0:
                chunk += b'\x00'
            await websocket.send(chunk)
            total += len(chunk)
            chunks += 1
            await asyncio.sleep(0.01)

    await asyncio.sleep(2)
    await websocket.send("audio_end")
    elapsed = time.time() - t0
    print(f"[WS] ✅ Music streamed: {total/1024:.1f} KB in {chunks} chunks ({elapsed:.1f}s)")
