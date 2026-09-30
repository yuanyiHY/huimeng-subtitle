"""mlx-whisper local ASR engine (Apple MLX). Loads a model from a local dir if
present, otherwise falls back to the MLX repo id."""

from __future__ import annotations

from pathlib import Path
from typing import List

from backend.asr.base import BaseASREngine, EngineUnavailable, Segment


class MLXWhisperEngine(BaseASREngine):
    name = "mlx-whisper"

    def __init__(self, model: str = "mlx-community/whisper-large-v3-turbo",
                 device: str = "auto", language: str = "ko", models_dir: str | None = None):
        self.model_id = model
        self.device = device
        self.language = language
        self.models_dir = Path(models_dir) if models_dir else None
        self._model = None
        self._resolved = None

    def _resolve(self) -> str:
        if self._resolved:
            return self._resolved
        path = self.model_id
        if self.models_dir and self.models_dir.exists():
            lp = self.models_dir / self.model_id.replace("/", "__")
            if any(lp.iterdir()):
                path = str(lp)
        self._resolved = path
        return path

    def available(self) -> bool:
        try:
            import mlx_whisper  # noqa: F401
            return True
        except Exception:
            return False

    def _transcribe(self, audio, language: str) -> List[Segment]:
        try:
            import mlx_whisper
        except Exception as exc:  # pragma: no cover
            raise EngineUnavailable(f"mlx-whisper 未安装：{exc}") from exc
        # "auto" 要让 whisper 自己检测（传 None），不能把字符串 "auto" 当语言代码丢进去；
        # 另外 whisper 只支持 "zh"，不支持 "zh-TW"
        if not language or language == "auto":
            whisper_lang = None
        elif language in ("zh", "zh-TW"):
            whisper_lang = "zh"
        else:
            whisper_lang = language
        model_path = self._resolve()
        result = mlx_whisper.transcribe(
            audio, path_or_hf_repo=model_path, language=whisper_lang
        )
        segments: List[Segment] = []
        for seg in result.get("segments", []):
            segments.append(Segment(
                start=float(seg.get("start", 0)),
                end=float(seg.get("end", 0)),
                text=str(seg.get("text", "")).strip(),
            ))
        # 繁体转换（zh-TW）
        if language == "zh-TW":
            try:
                from opencc import OpenCC
                cc = OpenCC("s2t")  # 简体 → 繁体
                segments = [
                    Segment(text=cc.convert(s.text), start=s.start, end=s.end)
                    for s in segments
                ]
            except Exception as e:
                print(f"[asr] 繁体转换失败: {e}", flush=True)
        return segments

    def transcribe_file(self, wav_path: str, language: str = "ko") -> List[Segment]:
        return self._transcribe(_read_audio_mono_16k(wav_path), language)

    def transcribe_array(self, audio, language: str = "ko") -> List[Segment]:
        """Transcribe a float32 mono @16kHz numpy array (used by live streaming)."""
        return self._transcribe(audio, language)


def _read_audio_mono_16k(path: str):
    """Decode any soundfile-readable audio (wav/flac/mp3/ogg...) to mono float32
    @16kHz using soundfile, so we do not depend on a system ffmpeg binary."""
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if sr != 16000:
        import scipy.signal
        new_len = int(len(mono) * 16000 / sr)
        mono = np.asarray(scipy.signal.resample_poly(mono, 16000, sr), dtype=np.float32)
    return mono
