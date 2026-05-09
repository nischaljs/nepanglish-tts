"""Wake-word detection modules.

Each detector implements the same interface:
    process_frame(data: bytes) -> bool
        Returns True when wake word is detected.
        Must be called with each audio frame in sequence.

The EnergyWakeDetector uses RMS energy threshold.
Swap it for an ML-based detector (Porcupine, Vosk, etc.)
without changing any other module.
"""

from collections import deque

WAKE_THRESHOLD = 800
WAKE_CONFIRM_FRAMES = 5
PRE_BUFFER_SIZE = 25


class EnergyWakeDetector:
    """Simple energy-based wake-word detector.

    Detects sustained audio energy above a threshold.
    Uses a pre-buffer that can be flushed when wake triggers,
    so no audio context is lost.

    Usage:
        det = EnergyWakeDetector(threshold=800, confirm_frames=5)
        pre_buf = det.pre_buffer  # deque of recent frames
        for frame in audio_stream:
            if det.process_frame(frame):
                print("Wake detected!")
                for buf in pre_buf:
                    stream_to_server(buf)
                break
    """

    def __init__(self, threshold=WAKE_THRESHOLD, confirm_frames=WAKE_CONFIRM_FRAMES, pre_buffer_size=PRE_BUFFER_SIZE):
        self.threshold = threshold
        self.confirm_frames = confirm_frames
        self.pre_buffer = deque(maxlen=pre_buffer_size)
        self._streak = 0

    def process_frame(self, data: bytes) -> bool:
        self.pre_buffer.append(data)
        energy = self._rms_energy(data)
        if energy > self.threshold:
            self._streak += 1
            if self._streak >= self.confirm_frames:
                self._streak = 0
                return True
        else:
            self._streak = 0
        return False

    def reset(self):
        self._streak = 0
        self.pre_buffer.clear()

    @staticmethod
    def _rms_energy(data: bytes) -> float:
        samples = [int.from_bytes(data[i:i+2], 'little', signed=True) for i in range(0, len(data), 2)]
        return (sum(s*s for s in samples) / len(samples)) ** 0.5
