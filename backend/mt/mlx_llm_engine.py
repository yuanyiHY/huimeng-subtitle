"""Local Qwen LLM MT engine (mlx-lm)."""
from __future__ import annotations

from typing import List

from backend.mt.base import BaseMTEngine


class MLXLLMEngine(BaseMTEngine):
    name = "local-qwen"

    def __init__(self, model: str = "Qwen2.5-7B-Instruct-4bit-MLX"):
        self.model_path = model

    def available(self) -> bool:
        try:
            import mlx_lm  # noqa: F401
            return True
        except Exception:
            return False

    def translate(self, texts: List[str], src: str = "ko", tgt: str = "zh") -> List[str]:
        if not self.available():
            return ["" for _ in texts]
        # TODO: wire MLX-LM generation loop for offline Qwen translation.
        return ["" for _ in texts]
