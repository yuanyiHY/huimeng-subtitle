"""Silero VAD (onnxruntime). Skeleton: report availability; segmentation stubbed."""
from __future__ import annotations

from typing import List, Tuple


def vad_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def detect_speech_segments(
    samples: List[float],
    sample_rate: int = 16000,
    sample_size: int = 512,
) -> List[Tuple[int, int]]:
    """Return list of (start_ms, end_ms) speech segments.

    TODO: wire real Silero VAD here. For the skeleton, return the whole buffer
    as a single utterance so downstream transcription still works.
    """
    return [(0, int(len(samples) / sample_rate * 1000))]
