"""Match a query embedding against the stored database.

Uses cosine similarity — embeddings out of InsightFace's MobileFaceNet
(buffalo_sc) are L2-normalized, so cosine == dot product. Higher score
= better match (1.0 = identical).

Threshold semantics: a match is accepted only when similarity >= threshold.
Nova uses 0.363 today; we keep that as the default.
"""

from __future__ import annotations

import numpy as np


def find_best_match(
    embedding: np.ndarray,
    matrix: np.ndarray | None,
    ids: list[str],
    threshold: float,
) -> dict | None:
    """Find the registered identity closest to `embedding`.

    Returns None if the database is empty or no entry meets the threshold.
    Otherwise returns:
        {"id": <identity_id>, "confidence": <similarity 0..1>}
    """
    if matrix is None or len(ids) == 0:
        return None

    emb = np.asarray(embedding, dtype=np.float32).reshape(-1)
    # `matrix` is shape (N, D). cosine sim = dot product since both sides
    # are L2-normalized (storage normalizes on write; embedder normalizes
    # on extraction).
    sims = matrix @ emb  # (N,)
    best_idx = int(np.argmax(sims))
    best_score = float(sims[best_idx])

    if best_score < float(threshold):
        return None
    return {"id": ids[best_idx], "confidence": best_score}
