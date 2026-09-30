"""Local NLLB MT engine via transformers (Seq2Seq). Loads the local model dir if
present; otherwise uses the HF repo id (auto-downloaded to HF cache)."""

from __future__ import annotations

from pathlib import Path
from typing import List

from backend.mt.base import BaseMTEngine

SRC_LANG = "kor_Hang"
TGT_LANG = "zho_Hans"

NLLB_LANGS = {
    "ko": "kor_Hang", "zh": "zho_Hans", "en": "eng_Latn", "ja": "jpn_Jpan",
    "fr": "fra_Latn", "de": "deu_Latn", "es": "spa_Latn", "ru": "rus_Cyrl",
}


class NLLBEngine(BaseMTEngine):
    name = "local-nllb"

    def __init__(self, model: str = "facebook/nllb-200-distilled-600M",
                 int8: bool = True, models_dir: str | None = None):
        self.model_id = model
        self.int8 = int8
        self.models_dir = Path(models_dir) if models_dir else None
        self._pipe = None
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
            import transformers  # noqa: F401
            return True
        except Exception:
            return False

    def _get_pipe(self):
        if self._pipe is None:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            model_path = self._resolve()
            tok = AutoTokenizer.from_pretrained(model_path, src_lang=SRC_LANG)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_path)
            self._pipe = (tok, model)
        return self._pipe

    def translate(self, texts: List[str], src: str = "ko", tgt: str = "zh") -> List[str]:
        tok, model = self._get_pipe()
        src_code = NLLB_LANGS.get(src, "kor_Hang")
        tgt_code = NLLB_LANGS.get(tgt, "zho_Hans")
        tok.src_lang = src_code
        out: List[str] = []
        for text in texts:
            if not text.strip():
                out.append("")
                continue
            inputs = tok(text, return_tensors="pt", truncation=True, max_length=512)
            generated = model.generate(
                **inputs, forced_bos_token_id=tok.convert_tokens_to_ids(tgt_code),
                max_new_tokens=80,
            )
            out.append(tok.batch_decode(generated, skip_special_tokens=True)[0].strip())
        return out
