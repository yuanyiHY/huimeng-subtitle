"""MT engine base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class BaseMTEngine(ABC):
    name: str = "base"

    @abstractmethod
    def available(self) -> bool:
        """Whether the engine's backing deps are installed."""

    @abstractmethod
    def translate(self, texts: List[str], src: str = "ko", tgt: str = "zh") -> List[str]:
        """Translate a list of strings. Raise EngineUnavailable if needed."""
