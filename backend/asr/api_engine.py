"""Cloud ASR engine (reserved). Always reports unavailable until wired."""
from __future__ import annotations

from typing import List

from backend.asr.base import BaseASREngine, EngineUnavailable, Segment


class APIAudioEngine(BaseASREngine):
    name = "api"

    def available(self) -> bool:
        return False

    def transcribe_file(self, wav_path: str, language: str = "ko") -> List[Segment]:
        raise EngineUnavailable("云端 ASR 尚未接入，请使用本地 mlx-whisper")
