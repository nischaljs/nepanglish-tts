import queue
import threading
from collections import deque

import pyaudio

RATE = 16000
FRAME_DURATION_MS = 20
FRAME_SIZE = int(RATE * FRAME_DURATION_MS / 1000)
FORMAT = pyaudio.paInt16
CHANNELS = 1


class MicAudioCapture:
    """Captures audio from system mic via PyAudio.

    Runs in a dedicated thread. Puts raw PCM frames (16-bit, 16kHz, mono)
    into a thread-safe queue. Can be started/stopped independently.
    Supports optional pre-buffer for wake-word context retention.

    Usage:
        cap = MicAudioCapture()
        cap.start()
        frame = cap.frames.get(timeout=1)  # blocks until frame available
        cap.stop()
    """

    def __init__(self, device_index=None, rate=RATE, frame_size=FRAME_SIZE):
        self.device_index = device_index
        self.rate = rate
        self.frame_size = frame_size
        self.frames = queue.Queue()
        self._running = False
        self._thread = None
        self._pa = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def is_running(self):
        return self._running

    def _loop(self):
        self._pa = pyaudio.PyAudio()
        stream = self._pa.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=self.rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=self.frame_size,
        )
        try:
            while self._running:
                data = stream.read(self.frame_size, exception_on_overflow=False)
                self.frames.put(data)
        finally:
            stream.stop_stream()
            stream.close()
            self._pa.terminate()
