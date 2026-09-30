"""Audio helpers (ffmpeg decode / resample to 16k mono)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True,
                       timeout=5)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def decode_to_wav(src: Path, dst: Path, sample_rate: int = 16000) -> Path:
    """Decode any audio/video file to a 16k mono WAV using ffmpeg."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-ac", "1", "-ar", str(sample_rate),
            "-f", "wav", str(dst),
        ],
        check=True,
        capture_output=True,
    )
    return dst


def probe_duration(src: Path) -> Optional[float]:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(src)],
            capture_output=True, check=True, text=True, timeout=10,
        )
        import json
        return float(json.loads(out.stdout)["format"]["duration"])
    except Exception:
        return None
