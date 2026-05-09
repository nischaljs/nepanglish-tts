"""Persistent storage for registered face embeddings + metadata.

Two files inside `data_dir`:
  embeddings.npy   plain numpy array, shape (N, 512) float32 — pickle-free
  metadata.json    {"order": [id, id, ...], "identities": {id: {...}}}

`metadata.json["order"]` is the source of truth for which row of the
matrix corresponds to which identity, so embeddings.npy stays a clean
numeric blob (no object arrays, no pickle).

Atomic writes via tmp-file + rename so a crash mid-write can't leave a
half-baked database. Embeddings are stored L2-normalized so the matcher
can use plain dot products.

Concurrency note: this isn't process-safe (no fcntl locks), but Nova
runs face I/O serially under FaceRecognitionBridge._recog_lock, so a
single-process lock is enough here.
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import uuid
from pathlib import Path

import numpy as np

EMBEDDINGS_FILE = "embeddings.npy"
METADATA_FILE = "metadata.json"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def _atomic_save_npy(path: Path, arr: np.ndarray) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Use an open file so np.save doesn't auto-append `.npy` to the name —
    # which it does when given a string path. allow_pickle=False keeps
    # the file plain numeric (no executable code on load).
    with open(tmp, "wb") as f:
        np.save(f, arr, allow_pickle=False)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


class FaceStorage:
    """Read methods (load_matrix, get_metadata, list_all) and mutating
    methods (add, delete) that persist to disk.
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.embeddings_path = self.data_dir / EMBEDDINGS_FILE
        self.metadata_path = self.data_dir / METADATA_FILE
        self._lock = threading.Lock()

    # ---- read paths ---------------------------------------------------

    def load_matrix(self) -> tuple[np.ndarray | None, list[str]]:
        """Return (matrix, ids). Both are None/[] if no faces are registered yet."""
        meta_blob = self._load_meta_blob()
        order = list(meta_blob.get("order", []))
        if not self.embeddings_path.exists() or not order:
            return None, []
        try:
            matrix = np.load(self.embeddings_path, allow_pickle=False).astype(np.float32)
        except Exception:
            return None, []
        if matrix.size == 0 or matrix.shape[0] != len(order):
            return None, []
        return matrix, order

    def get_metadata(self, identity_id: str) -> dict | None:
        return self._load_meta_blob().get("identities", {}).get(identity_id)

    def list_all(self) -> dict:
        return dict(self._load_meta_blob().get("identities", {}))

    # ---- write paths --------------------------------------------------

    def add(self, embedding: np.ndarray, metadata: dict) -> str:
        """Append a new identity, return its assigned id."""
        identity_id = uuid.uuid4().hex[:12]
        emb = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
        # Make sure stored embeddings are L2-normalized so the matcher
        # can dot-product them as cosine similarities.
        norm = np.linalg.norm(emb, axis=1, keepdims=True)
        emb = np.divide(emb, norm, where=norm > 0)

        with self._lock:
            matrix, ids = self.load_matrix()
            if matrix is None:
                new_matrix = emb
                new_ids = [identity_id]
            else:
                new_matrix = np.vstack([matrix, emb]).astype(np.float32)
                new_ids = [*ids, identity_id]
            _atomic_save_npy(self.embeddings_path, new_matrix)

            blob = self._load_meta_blob()
            identities = dict(blob.get("identities", {}))
            identities[identity_id] = {
                **metadata,
                "registered_at": datetime.datetime.now().isoformat(timespec="seconds"),
            }
            self._save_meta_blob({"order": new_ids, "identities": identities})

        return identity_id

    def delete(self, identity_id: str) -> bool:
        with self._lock:
            matrix, ids = self.load_matrix()
            blob = self._load_meta_blob()
            identities = dict(blob.get("identities", {}))

            removed = False
            if matrix is not None and identity_id in ids:
                keep = [i for i, x in enumerate(ids) if x != identity_id]
                if not keep:
                    # Last identity gone — remove the file outright.
                    self.embeddings_path.unlink(missing_ok=True)
                    new_ids: list[str] = []
                else:
                    new_matrix = matrix[keep]
                    new_ids = [ids[i] for i in keep]
                    _atomic_save_npy(self.embeddings_path, new_matrix)
                removed = True
            else:
                new_ids = list(ids)

            if identity_id in identities:
                del identities[identity_id]
                removed = True

            self._save_meta_blob({"order": new_ids, "identities": identities})
            return removed

    # ---- metadata helpers ---------------------------------------------

    def _load_meta_blob(self) -> dict:
        if not self.metadata_path.exists():
            return {"order": [], "identities": {}}
        try:
            with open(self.metadata_path, encoding="utf-8") as f:
                blob = json.load(f)
        except Exception:
            return {"order": [], "identities": {}}
        # Backward-tolerance: if someone hand-edits and drops a key.
        blob.setdefault("order", [])
        blob.setdefault("identities", {})
        return blob

    def _save_meta_blob(self, blob: dict) -> None:
        data = json.dumps(blob, ensure_ascii=False, indent=2).encode("utf-8")
        _atomic_write_bytes(self.metadata_path, data)
