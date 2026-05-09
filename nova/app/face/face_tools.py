import os
import sys
import threading
import time
from collections import deque

import cv2
import numpy as np

FACE_RECO_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "face-recognition"
)
sys.path.insert(0, FACE_RECO_PATH)

from face_recognition_system import FaceRecognitionSystem
from face_recognition_system.detector import detect_faces
from face_recognition_system.embedder import generate_embedding
from face_recognition_system.matcher import find_best_match


DATA_DIR = os.path.join(FACE_RECO_PATH, "face_data")
THRESHOLD = 0.363
DETECT_SCALE = 0.5


class FrameBuffer:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._frame = None
            cls._instance._timestamp = 0.0
        return cls._instance

    def update(self, frame: np.ndarray):
        with self._lock:
            self._frame = frame
            self._timestamp = time.time()

    def get(self) -> tuple[np.ndarray | None, float]:
        with self._lock:
            return self._frame, self._timestamp

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame


class RegistrationCollector:
    def __init__(self, max_samples=15, min_gap=1.5):
        self.samples = deque(maxlen=max_samples)
        self.min_gap = min_gap
        self._last_sample = 0.0

    def add(self, frame: np.ndarray, score: float):
        now = time.time()
        if now - self._last_sample < self.min_gap:
            return False
        self.samples.append((frame.copy(), score))
        self._last_sample = now
        return True

    @property
    def count(self):
        return len(self.samples)

    @property
    def full(self):
        return self.count == self.samples.maxlen

    def clear(self):
        self.samples.clear()


class FaceRecognitionBridge:
    def __init__(self, data_dir=DATA_DIR, threshold=THRESHOLD):
        self.system = FaceRecognitionSystem(data_dir=data_dir, threshold=threshold)
        self._recog_lock = threading.Lock()

    def has_face(self, image: np.ndarray) -> bool:
        small = cv2.resize(image, None, fx=DETECT_SCALE, fy=DETECT_SCALE) if image.shape[1] > 320 else image
        faces = detect_faces(small)
        return len(faces) > 0

    def recognize(self, image: np.ndarray) -> dict | None:
        with self._recog_lock:
            try:
                small = cv2.resize(image, None, fx=DETECT_SCALE, fy=DETECT_SCALE) if image.shape[1] > 320 else image
                faces = detect_faces(small)
                if not faces:
                    return None
                face = faces[0]
                embedding = generate_embedding(small, face["raw"])
                matrix, ids = self.system.storage.load_matrix()
                if matrix is None:
                    return {"unknown": True, "face_bbox": face["bbox"]}
                match = find_best_match(embedding, matrix, ids, THRESHOLD)
                if not match:
                    return {"unknown": True, "face_bbox": face["bbox"]}
                meta = self.system.storage.get_metadata(match["id"]) or {}
                return {
                    "id": match["id"],
                    "name": meta.get("name", "unknown"),
                    "confidence": match["confidence"],
                    "face_bbox": face["bbox"],
                    "unknown": False,
                }
            except Exception as e:
                return None

    def register(self, image: np.ndarray, name: str) -> dict | None:
        with self._recog_lock:
            try:
                return self.system.register(image, {"name": name})
            except Exception as e:
                return None

    def delete(self, identity_id: str) -> bool:
        return self.system.delete(identity_id)

    def list_identities(self) -> dict:
        return self.system.list_identities()


FACES_BRIDGE = None
REG_COLLECTOR = None


def get_bridge():
    global FACES_BRIDGE
    if FACES_BRIDGE is None:
        FACES_BRIDGE = FaceRecognitionBridge()
    return FACES_BRIDGE


def get_collector():
    global REG_COLLECTOR
    if REG_COLLECTOR is None:
        REG_COLLECTOR = RegistrationCollector()
    return REG_COLLECTOR
