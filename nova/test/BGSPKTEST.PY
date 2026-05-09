import asyncio
import websockets
import time

# Config
AUDIO_FILE = "response.wav"
CHUNK_SIZE = 1024  # Sending 1KB chunks for stability

async def stream_audio(websocket):
    print(f"▶ Processing {AUDIO_FILE}...")
    try:
        with open(AUDIO_FILE, "rb") as f:
            f.seek(44)  # Skip WAV Header
            audio_data = f.read()

        await websocket.send("audio_start")
        
        # 24000Hz * 16-bit(2 bytes) * 1 channel = 48000 bytes/sec
        # Sending 1024 bytes every 0.021s is real-time. 
        # We use 0.019s to stay slightly ahead and prevent underrun.
        for i in range(0, len(audio_data), CHUNK_SIZE):
            chunk = audio_data[i:i + CHUNK_SIZE]
            await websocket.send(chunk)
            await asyncio.sleep(0.019) 

        await websocket.send("audio_end")
        print("✅ Finished")
    except Exception as e:
        print(f"Error: {e}")

async def handler(websocket):
    async for message in websocket:
        if message == "play_test":
            await stream_audio(websocket)

async def main():
    async with websockets.serve(handler, "0.0.0.0", 8080):
        print("🚀 Server running on port 8080. Press 'p' in ESP Serial to test.")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())