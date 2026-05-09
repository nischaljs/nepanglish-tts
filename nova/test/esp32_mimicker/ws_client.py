"""WebSocket client that speaks the same protocol as the real ESP32.

Connects to the Nova server and handles bidirectional messaging:
  - Sends binary audio frames (raw 16-bit PCM)
  - Receives text commands: start_stream, stop_stream, audio_start, audio_end
  - Receives JSON command payloads

Protocol matches Hardware/MCU.txt exactly:
  ESP32 → server: binary audio frames (320 samples, 16-bit, 16kHz)
  Server → ESP32: "start_stream" | "stop_stream" | "audio_start" | "audio_end"
  Server → ESP32: {"type":"command","payload":{...}}

Usage:
    client = WSClient("ws://localhost:8080")
    client.on_stream_start = lambda: print("Stream requested")
    client.on_stream_stop = lambda: print("Stream stopped")
    await client.connect()
    await client.send_audio(frame_bytes)
    await client.disconnect()
"""

import asyncio
import json

import websockets


class WSClient:
    """Handles the WebSocket protocol between Pi and ESP32."""

    def __init__(self, url="ws://localhost:8080"):
        self.url = url
        self._ws = None
        self._reader_task = None

        # Callbacks — set these externally to react to server commands
        self.on_stream_start = None
        self.on_stream_stop = None
        self.on_audio_start = None
        self.on_audio_end = None
        self.on_command = None
        self.on_connected = None
        self.on_disconnected = None

    @property
    def connected(self):
        return self._ws is not None and not self._ws.closed

    async def connect(self):
        self._ws = await websockets.connect(self.url)
        self._reader_task = asyncio.create_task(self._reader())
        if self.on_connected:
            self.on_connected()

    async def disconnect(self):
        if self._reader_task:
            self._reader_task.cancel()
        if self._ws:
            await self._ws.close()
        if self.on_disconnected:
            self.on_disconnected()

    async def send_audio(self, data: bytes):
        if self.connected:
            await self._ws.send(data)

    async def send_text(self, text: str):
        if self.connected:
            await self._ws.send(text)

    async def _reader(self):
        try:
            async for msg in self._ws:
                if isinstance(msg, str):
                    await self._handle_text(msg)
        except websockets.exceptions.ConnectionClosed:
            if self.on_disconnected:
                self.on_disconnected()

    async def _handle_text(self, msg: str):
        if msg == "start_stream":
            if self.on_stream_start:
                self.on_stream_start()
        elif msg == "stop_stream":
            if self.on_stream_stop:
                self.on_stream_stop()
        elif msg == "audio_start":
            if self.on_audio_start:
                self.on_audio_start()
        elif msg == "audio_end":
            if self.on_audio_end:
                self.on_audio_end()
        else:
            try:
                data = json.loads(msg)
                if self.on_command:
                    self.on_command(data)
            except json.JSONDecodeError:
                pass
