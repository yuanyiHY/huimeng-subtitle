#!/usr/bin/env python3
"""从 HuggingFace 拉取模型文件清单，生成 backend/models/manifest.v1.json。

manifest 是模型分发的"发布权威"（参考 Coursedude 的做法）：
每个模型记录 repo、revision、许可（SPDX + 是否允许商业分发）、
逐文件的 byteSize 与 sha256（HF LFS 提供时），供下载器校验和原子安装。

用法：
    .venv/bin/python scripts/gen_model_manifest.py
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from huggingface_hub import HfApi  # noqa: E402

REPOS = {
    "whisper": {
        "repo": "mlx-community/whisper-large-v3-turbo",
        "engineKind": "mlx-whisper",
        "purpose": "语音转写（多语言）",
        "license": {"spdx": "MIT", "commercialDistributionAllowed": True},
    },
    "nllb": {
        "repo": "facebook/nllb-200-distilled-600M",
        "engineKind": "transformers",
        "purpose": "本地翻译（多语言）",
        "license": {"spdx": "CC-BY-NC-4.0", "commercialDistributionAllowed": False},
    },
    "qwen": {
        "repo": "Qwen/Qwen2.5-7B-Instruct",
        "engineKind": "mlx-llm",
        "purpose": "本地 LLM（翻译 / 课程整理 / 复习题）",
        "license": {"spdx": "Apache-2.0", "commercialDistributionAllowed": True},
    },
}


def file_meta(f) -> dict:
    size = getattr(f, "size", None) or 0
    sha = None
    lfs = getattr(f, "lfs", None)
    if lfs is not None:
        sha = lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)
    entry = {"path": f.rfilename, "byteSize": int(size)}
    if sha:
        entry["sha256"] = sha
    return entry


def main() -> int:
    api = HfApi()
    manifest = {
        "schemaVersion": 1,
        "manifestVersion": "1.0.0",
        "note": "模型发布权威清单：下载/校验/原子安装均以本文件为准。",
        "models": {},
    }
    for mid, meta in REPOS.items():
        print(f"[manifest] fetching {meta['repo']} ...", flush=True)
        info = api.model_info(meta["repo"], files_metadata=True)
        files = [file_meta(f) for f in info.siblings]
        total = sum(f["byteSize"] for f in files)
        manifest["models"][mid] = {
            "id": mid,
            **meta,
            "revision": info.sha,
            "totalBytes": total,
            "files": files,
        }
        print(f"[manifest]   {mid}: {len(files)} files, {total / 1e9:.3f} GB", flush=True)

    out = ROOT / "backend" / "models" / "manifest.v1.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[manifest] written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
