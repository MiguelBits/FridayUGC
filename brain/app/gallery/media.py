from __future__ import annotations

import base64
import io
import subprocess
import tempfile
from pathlib import Path

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}


def is_image_path(path: str) -> bool:
    return Path(path).suffix.lower() in _IMAGE_SUFFIXES


def is_video_path(path: str) -> bool:
    return Path(path).suffix.lower() in _VIDEO_SUFFIXES


def image_bytes_to_jpeg_b64(raw: bytes, max_side: int = 768) -> str | None:
    """Resize/compress to JPEG base64 for vision model input."""
    try:
        from PIL import Image
    except ImportError:
        return base64.b64encode(raw).decode("ascii")

    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None

    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def video_frame_to_jpeg_b64(raw: bytes, suffix: str, max_side: int = 768) -> str | None:
    """Extract first frame via ffmpeg (must be installed on the brain host)."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as vf:
        vf.write(raw)
        video_path = vf.name

    frame_path = video_path + ".jpg"
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                video_path,
                "-vframes",
                "1",
                "-q:v",
                "2",
                frame_path,
            ],
            capture_output=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return None
        return image_bytes_to_jpeg_b64(Path(frame_path).read_bytes(), max_side=max_side)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    finally:
        Path(video_path).unlink(missing_ok=True)
        Path(frame_path).unlink(missing_ok=True)


def media_to_vision_b64(raw: bytes, filename: str, max_side: int = 768) -> str | None:
    """Turn gallery media bytes into a JPEG base64 frame for the vision model."""
    lower = filename.lower()
    if any(lower.endswith(ext) for ext in _IMAGE_SUFFIXES):
        return image_bytes_to_jpeg_b64(raw, max_side=max_side)
    if any(lower.endswith(ext) for ext in _VIDEO_SUFFIXES):
        suffix = Path(filename).suffix or ".mp4"
        return video_frame_to_jpeg_b64(raw, suffix, max_side=max_side)
    return None
