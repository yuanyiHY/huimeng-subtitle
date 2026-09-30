"""CTranslate2 本地翻译引擎（NLLB）——CPU 上比 transformers 快数倍、内存更低。

使用 CTranslate2 转换版模型（``model.bin`` + ``shared_vocabulary.json``），
tokenizer 复用对应的 HuggingFace 原模型目录。

模型目录约定（自动发现，无需配置）：
    models_dir/facebook__nllb-200-distilled-600M_ct2/   ← CT2 转换版
    models_dir/facebook__nllb-200-distilled-600M/       ← 原模型（tokenizer）
转换命令（离线一次性）：
    ct2-transformers-converter --model facebook/nllb-200-distilled-600M \\
        --output_dir <models_dir>/facebook__nllb-200-distilled-600M_ct2 \\
        --quantization int8
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from backend.mt.base import BaseMTEngine
from backend.mt.nllb_engine import NLLB_LANGS

_CT2_SUFFIX = "_ct2"


class CT2Engine(BaseMTEngine):
    name = "local-ct2"

    def __init__(self, models_dir: str,
                 base_model: str = "facebook/nllb-200-distilled-600M",
                 ct2_dir: Optional[str] = None,
                 compute_type: str = "default"):
        self.models_dir = Path(models_dir) if models_dir else None
        self.base_model = base_model
        self._ct2_dir = Path(ct2_dir) if ct2_dir else None
        self.compute_type = compute_type
        self._translator = None
        self._tokenizer = None

    # ---------- paths ----------
    def _resolve_ct2(self) -> Optional[Path]:
        if self._ct2_dir and self._ct2_dir.exists() and (self._ct2_dir / "model.bin").exists():
            return self._ct2_dir
        if self.models_dir:
            cand = self.models_dir / (self.base_model.replace("/", "__") + _CT2_SUFFIX)
            if (cand / "model.bin").exists():
                return cand
        return None

    def _resolve_tokenizer(self) -> Optional[Path]:
        if self.models_dir:
            cand = self.models_dir / self.base_model.replace("/", "__")
            if cand.exists():
                return cand
        return None

    def available(self) -> bool:
        try:
            import ctranslate2  # noqa: F401
            import transformers  # noqa: F401
        except Exception:
            return False
        return self._resolve_ct2() is not None and self._resolve_tokenizer() is not None

    # ---------- lazy load ----------
    def _ensure_loaded(self):
        if self._translator is None:
            import ctranslate2
            ct2_dir = self._resolve_ct2()
            if ct2_dir is None:
                raise RuntimeError("未找到 CTranslate2 转换版模型（*_ct2/model.bin）")
            self._translator = ctranslate2.Translator(
                str(ct2_dir), device="cpu", compute_type=self.compute_type,
            )
        if self._tokenizer is None:
            from transformers import AutoTokenizer
            tok_dir = self._resolve_tokenizer()
            if tok_dir is None:
                raise RuntimeError("未找到 NLLB tokenizer（原模型目录）")
            self._tokenizer = AutoTokenizer.from_pretrained(str(tok_dir))

    # ---------- translate ----------
    def translate(self, texts: List[str], src: str = "ko", tgt: str = "zh") -> List[str]:
        self._ensure_loaded()
        tok = self._tokenizer
        src_code = NLLB_LANGS.get(src, "kor_Hang")
        tgt_code = NLLB_LANGS.get(tgt, "zho_Hans")
        tok.src_lang = src_code

        out: List[str] = [""] * len(texts)
        batch_tokens: List[List[str]] = []
        idx_map: List[int] = []
        for i, text in enumerate(texts):
            if not text or not text.strip():
                continue
            ids = tok(text, truncation=True, max_length=512)["input_ids"]
            batch_tokens.append(tok.convert_ids_to_tokens(ids))
            idx_map.append(i)
        if not batch_tokens:
            return out

        results = self._translator.translate_batch(
            batch_tokens,
            target_prefix=[[tgt_code]] * len(batch_tokens),
            beam_size=1,
            max_batch_size=16,
            batch_type="tokens",
        )
        for pos, res in zip(idx_map, results):
            hyp = list(res.hypotheses[0]) if res.hypotheses else []
            # 结果回带 target_prefix（语言 token），去掉
            if hyp and hyp[0] == tgt_code:
                hyp = hyp[1:]
            out[pos] = tok.decode(tok.convert_tokens_to_ids(hyp)).strip()
        return out
