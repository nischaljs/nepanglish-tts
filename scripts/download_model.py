"""Download and unpack the Piper Nepali (chitwan-medium) model.

Run this once after cloning the repo. Pulls about 25 MB; ends up at
~70 MB on disk after extraction (most of it is espeak-ng's phoneme data).
"""

import sys
import tarfile
import urllib.request
from pathlib import Path

# Add project root to path so `import nepali_tts.config` works when the
# script is run directly without installing the package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nepali_tts import config  # noqa: E402

ARCHIVE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    f"{config.MODEL_NAME}.tar.bz2"
)


def _report_progress(block_num: int, block_size: int, total_size: int) -> None:
    """urllib's tiny built-in progress hook — good enough for a one-off."""
    if total_size <= 0:
        return
    downloaded = min(block_num * block_size, total_size)
    pct = downloaded * 100 // total_size
    bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
    sys.stdout.write(
        f"\r  [{bar}] {pct:3d}% ({downloaded // 1024} / {total_size // 1024} KB)"
    )
    sys.stdout.flush()


def main() -> int:
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Already present and unpacked? No-op.
    if config.MODEL_DIR.exists() and any(config.MODEL_DIR.glob("*.onnx")):
        print(f"Model already present at {config.MODEL_DIR} — nothing to do.")
        return 0

    archive_path = config.MODELS_DIR / f"{config.MODEL_NAME}.tar.bz2"

    print(f"Downloading {ARCHIVE_URL}")
    try:
        urllib.request.urlretrieve(ARCHIVE_URL, archive_path, _report_progress)
        print()  # newline after the progress bar
    except Exception as e:
        print(f"\n!! download failed: {e}", file=sys.stderr)
        return 1

    print(f"Extracting to {config.MODELS_DIR}")
    with tarfile.open(archive_path, "r:bz2") as tar:
        tar.extractall(config.MODELS_DIR)

    archive_path.unlink()  # don't leave the tarball lying around
    print(f"Done. Model lives at {config.MODEL_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
