"""Face detection (and embedding, since InsightFace bundles both).

Loads InsightFace's buffalo_sc model lazily on first use — pays a ~2-3s
model-load cost once per process, then ~50-150ms per frame on a Pi 4.

Detect_faces() returns a list of dicts so the caller can pass `face["raw"]`
back to embedder.generate_embedding() without re-running detection. The
"raw" payload is the InsightFace `Face` object itself, which already
carries the 512-d embedding produced during detection — so embedding is
effectively free once we've detected.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

# Module-level singleton: InsightFace's FaceAnalysis is heavy to construct
# (~2-3s) and not thread-safe to construct from multiple threads at once.
_LOCK = threading.Lock()
_app = None


def _get_app():
    """Return the shared FaceAnalysis instance, building it on first call."""
    global _app
    if _app is not None:
        return _app
    with _LOCK:
        if _app is not None:
            return _app
        import insightface

        # Models live under face-recognition/models/buffalo_sc/. The
        # `root` arg is what InsightFace uses to find/cache models;
        # passing the parent of `models/` keeps everything inside the
        # face-recognition/ folder so the project stays self-contained.
        repo_root = Path(__file__).resolve().parent.parent  # → face-recognition/
        app = insightface.app.FaceAnalysis(
            name="buffalo_sc",
            root=str(repo_root),
            providers=["CPUExecutionProvider"],
            # Detection-only modules; we use the bundled embedding via
            # the Face object's `embedding` attribute directly.
            allowed_modules=["detection", "recognition"],
        )
        # det_size is the resize the detector runs at. 640 is the default
        # and gives the right speed/accuracy tradeoff on a Pi 4 — smaller
        # (e.g. 320) would be ~2x faster but miss small faces.
        app.prepare(ctx_id=-1, det_size=(640, 640))
        _app = app
        return _app


def detect_faces(image, *args: Any, **kwargs: Any) -> list[dict]:
    """Detect every face in `image`. Returns a list, possibly empty.

    Each entry is:
      {
        "bbox":  [x1, y1, x2, y2],   # ints, in image coords
        "score": float,              # detector confidence 0..1
        "raw":   <insightface Face>, # opaque — pass to generate_embedding()
      }
    """
    app = _get_app()
    faces = app.get(image)
    out = []
    for f in faces:
        bbox = f.bbox.astype(int).tolist()  # [x1, y1, x2, y2]
        out.append(
            {
                "bbox": bbox,
                "score": float(f.det_score),
                "raw": f,
            }
        )
    return out
