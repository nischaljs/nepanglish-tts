"""Embedding extraction.

InsightFace's FaceAnalysis.get() already runs the recognition head and
attaches a 512-d embedding to each detected Face object. So this module
is a one-liner: pull `face_raw.embedding` off the Face we got from
detector.detect_faces().

The embedding from InsightFace buffalo_sc is L2-normalized — cosine
similarity reduces to a dot product, which the matcher relies on.

Signature kept compatible with Nova's existing import: takes the full
image plus the raw face payload returned by detect_faces().
"""

from __future__ import annotations

import numpy as np


def generate_embedding(image, face_raw) -> np.ndarray:
    """Return a (512,) float32 L2-normalized embedding for the given face.

    `face_raw` is the InsightFace Face object that detect_faces() put in
    the "raw" key. We trust the embedding it computed during detection.
    """
    if face_raw is None:
        raise ValueError("face_raw is None — pass the 'raw' from detect_faces()")
    emb = np.asarray(face_raw.embedding, dtype=np.float32)
    # Belt-and-suspenders: ensure normalization in case the model variant
    # didn't normalize. Idempotent if already normalized.
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb
