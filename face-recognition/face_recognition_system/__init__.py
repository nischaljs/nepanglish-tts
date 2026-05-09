"""Face recognition for Nova — wraps InsightFace (buffalo_sc) with the API
Nova's `app.face.face_tools` already expects.

Engine choice:
  - InsightFace's `buffalo_sc` bundle: SCRFD-500MF detector + MobileFaceNet
    embedding (w600k_mbf), ~16 MB total, ~99.4% LFW. Smallest InsightFace
    bundle that still achieves competitive accuracy.
  - Backend is onnxruntime (CPUExecutionProvider) — same runtime sherpa-onnx
    uses for the TTS model, so no extra GPU/CUDA dependency.

Models live under <project>/face-recognition/models/buffalo_sc/ (vendored
to keep everything inside the project folder). InsightFace downloads them
on first use; once downloaded they stay alongside the code.

Storage: registered face embeddings + metadata go to `data_dir`
(typically `<project>/face-recognition/face_data/`).

This module exposes:
  - FaceRecognitionSystem(data_dir, threshold) — high-level façade
  - detector.detect_faces(image)               — list of detections
  - embedder.generate_embedding(image, raw)    — 512-d vector
  - matcher.find_best_match(emb, matrix, ids, threshold)
"""

from __future__ import annotations

from .storage import FaceStorage

__all__ = ["FaceRecognitionSystem"]


class FaceRecognitionSystem:
    """High-level wrapper Nova talks to. Holds storage + thin orchestrators
    for register/delete/list_identities. Detection and embedding live in
    sibling modules so the import tree matches Nova's expectations.
    """

    def __init__(self, data_dir: str = "face_data", threshold: float = 0.363):
        self.data_dir = data_dir
        self.threshold = float(threshold)
        self.storage = FaceStorage(data_dir)

    def register(self, image, metadata: dict | None = None) -> dict | None:
        """Detect a face in `image`, embed it, persist with the given metadata.

        Returns {"id": <new_id>, "name": <name>} on success, None if no
        face was found or the image was unusable.
        """
        from .detector import detect_faces
        from .embedder import generate_embedding

        faces = detect_faces(image)
        if not faces:
            return None
        # Use the highest-confidence face if multiple are present.
        face = max(faces, key=lambda f: f.get("score", 0.0))
        embedding = generate_embedding(image, face["raw"])
        meta = dict(metadata or {})
        identity_id = self.storage.add(embedding, meta)
        return {"id": identity_id, "name": meta.get("name", "")}

    def delete(self, identity_id: str) -> bool:
        return self.storage.delete(identity_id)

    def list_identities(self) -> dict:
        """Return {id: metadata} for every registered identity."""
        return self.storage.list_all()
