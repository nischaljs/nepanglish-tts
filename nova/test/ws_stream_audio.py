import asyncio

import websockets

CHUNK_SIZE = 1024 # Larger chunks are more efficient for Wi-Fi
AUDIO_FILE = "response.wav"

async def stream_audio(websocket):
    print("▶ Streaming audio...")

    # Tell ESP to start playback
    await websocket.send("audio_start")

    with open(AUDIO_FILE, "rb") as f:
        # 🔥 Skip WAV header (44 bytes)
        f.seek(44)

        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break

            await websocket.send(chunk)
            await asyncio.sleep(0.01)  # pacing (20ms)

    # Tell ESP playback finished
    await websocket.send("audio_end")
    print("✅ Audio finished")


async def handler(websocket):
    print("Client connected")

    try:
        async for message in websocket:
            print("Received:", message)

            if message == "play_test":
                await stream_audio(websocket)

    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")


async def main():
    server = await websockets.serve(handler, "0.0.0.0", 8080)
    print("🚀 WebSocket server running on ws://0.0.0.0:8080")
    await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())