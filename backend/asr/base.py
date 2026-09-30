"""ASR engine base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Segment:
    start: float
    end: float
    text: str


class BaseASREngine(ABC):
    name: str = "base"

    @abstractmethod
    def available(self) -> bool:
        """Whether the engine's backing deps are installed."""

    @abstractmethod
    def transcribe_file(self, wav_path: str, language: str = "ko") -> List[Segment]:
        """Transcribe a decoded WAV file. Raise EngineUnavailable if needed."""

    def transcribe_stream(self, chunk_path: str, language: str = "ko") -> List[Segment]:
        """Fallback: stream chunk is just a partial file transcribe."""
        return self.transcribe_file(chunk_path, language)


class EngineUnavailable(RuntimeError):
    pass
