"""Cloud MT engine (OpenAI-compatible /v1/chat/completions).

Supports two flavors:
- Dedicated translation models (qwen-mt-*): plain text content + top-level
  `translation_options` {source_lang, target_lang} per DashScope compatible-mode.
- General LLMs: instruction-style system/user prompt.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List, Optional

from backend.mt.base import BaseMTEngine

LANG_NAMES = {
    "ko": "Korean",
    "zh": "Chinese",  # qwen-mt 官方标准：Chinese = 简体中文
    "zh-TW": "Traditional Chinese",  # 繁体中文
    "en": "English",
    "ja": "Japanese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ru": "Russian",
}


class OpenAIMTEngine(BaseMTEngine):
    name = "cloud"

    def __init__(self, base_url: Optional[str], api_key: Optional[str],
                 model: Optional[str], timeout: int = 15):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.is_mt_model = bool(model) and "mt" in str(model).lower()

    def available(self) -> bool:
        return bool(self.base_url and self.model)

    def translate(self, texts: List[str], src: str = "ko", tgt: str = "zh") -> List[str]:
        return [self._translate_one(t, src, tgt) for t in texts]

    def _translate_one(self, text: str, src: str = "ko", tgt: str = "zh") -> str:
        if not text.strip():
            return ""
        url = self.base_url.rstrip("/") + "/chat/completions"
        if self.is_mt_model:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": text}],
                "translation_options": {
                    "source_lang": LANG_NAMES.get(src, src),
                    "target_lang": LANG_NAMES.get(tgt, tgt),
                },
            }
        else:
            src_name = LANG_NAMES.get(src, src)
            tgt_name = LANG_NAMES.get(tgt, tgt)
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system",
                     "content": f"You are a professional {src_name}-to-{tgt_name} translator."},
                    {"role": "user",
                     "content": f"将下面这段{src_name}翻译成{tgt_name}，只输出译文：\n{text}"},
                ],
                "max_tokens": 300,
                "temperature": 0.2,
            }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or ''}",
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return str(body["choices"][0]["message"]["content"]).strip()
        except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError):
            return ""
