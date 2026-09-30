"""AI 备课引擎（随堂笔记 + 课堂问答）— Coursedude 风格的学习闭环。

两个能力：
- live-notes：录音进行中，把新增字幕片段增量喂给主模型，产出结构化笔记
  （定义 / 要点 / 例子 / 待复习），前端随录音滚动追加；
- ask：基于课堂/录音转写稿回答问题（轻量 RAG，转写稿直接当上下文）。

主模型未配置或不可用时全部优雅降级：返回 ok=false + 人话提示，
不阻塞录音主链路。
"""
from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

_LIVE_NOTES_SYSTEM = (
    "你是一位随堂笔记助手，服务对象是正在听课的学生。"
    "你会收到课堂实时字幕的最新片段和此前已经整理过的笔记。"
    "请只针对【新字幕片段】补充结构化笔记，输出 Markdown 列表，每条形如：\n"
    "- **定义**：……\n"
    "- **要点**：……\n"
    "- **例子**：……\n"
    "- **待复习**：……\n"
    "规则：\n"
    "1) 不要重复【已有笔记】中已经出现过的内容；\n"
    "2) 新片段里没有对应类型的小节就不要输出；\n"
    "3) 输出语言严格按【输出要求】执行；\n"
    "4) 只输出新增的笔记条目本身，不要输出标题、不要解释你在做什么；\n"
    "5) 若新片段没有值得记录的实质内容，只输出一个空字符串。"
)

# 实时总结的输出语言要求
_LIVE_OUTPUT_RULE = {
    "source": "【输出要求】\n用原文语言输出笔记。",
    "target": ("【输出要求】\n用译文语言输出笔记；遇到关键术语、专有名词、人名、产品名、"
               "数字与关键决策时，在译法后面用括号附上原文词段，格式如：术语（original）。"
               "普通叙述不要附原文，只在关键处附。"),
    "both": ("【输出要求】\n双语输出：每条笔记先写译文，紧接一行以「原文：」开头给出对应的原文词句，"
             "两行成一组，不要省略译文。"),
}

_ASK_SYSTEM = (
    "你是一位课程助教。请基于【课堂转写稿】回答学生的问题。"
    "如果转写稿中没有相关信息，先明确说“课堂内容里没有提到”，"
    "再给出你的最佳推测并标注（推测）。"
    "回答简洁、结构清晰，用与提问相同的语言。"
)


class LiveNotesRequest(BaseModel):
    new_lines: List[str]
    notes_so_far: str = ""
    max_tokens: int = 1200
    content: str = "target"  # source（原文）| target（译文）| both（双语）


class AskRequest(BaseModel):
    question: str
    transcript: str = ""


def _main_model(request: Request):
    s = request.app.state.settings
    return s.main_base_url, s.main_api_key, s.main_model


def _light_model(request: Request):
    """轻量实时模型：未单独配置时回退到主模型。"""
    s = request.app.state.settings
    return s.light_base_url, s.light_api_key, s.light_model


async def _complete(request: Request, system: str, user: str,
                    max_tokens: int, timeout: int, light: bool = False):
    """Run a model off the event loop. Returns (text, code, error)."""
    from backend.orchestrator import _chat_completion_ex
    from backend.errors import ErrorCode, humanize
    settings = request.app.state.settings
    base_url, api_key, model = _light_model(request) if light else _main_model(request)
    thinking = (settings.light_thinking if light else settings.main_thinking) or ""
    if not base_url or not model:
        return None, ErrorCode.MAIN_MODEL_MISSING, \
            f"{'轻量实时模型' if light else '主模型'}未配置（设置 → 模型设置 里填好 Base URL / Key / Model 即可启用）"
    loop = asyncio.get_running_loop()
    text, code = await loop.run_in_executor(
        None, lambda: _chat_completion_ex(base_url, api_key, model,
                                          system, user, max_tokens, timeout,
                                          thinking=thinking),
    )
    if text is None:
        code = code or ErrorCode.INTERNAL
        return None, code, f"{humanize(code)}（检查 Key / 网络后重试）"
    return text, None, None


@router.post("/coach/notes")
async def live_notes(request: Request, body: LiveNotesRequest):
    """增量生成随堂笔记片段（只针对新字幕）。"""
    lines = [ln.strip() for ln in body.new_lines if ln and ln.strip()]
    if not lines:
        return {"ok": True, "notes": "", "message": "没有新内容"}
    rule = _LIVE_OUTPUT_RULE.get(body.content, _LIVE_OUTPUT_RULE["target"])
    user = (
        rule
        + "\n\n【已有笔记（勿重复）】\n"
        + (body.notes_so_far.strip()[-1800:] or "（暂无）")
        + "\n\n【新字幕片段】\n"
        + "\n".join(lines[-40:])
    )
    # 实时阶段由轻量实时模型负责，低延迟优先
    text, code, err = await _complete(request, _LIVE_NOTES_SYSTEM, user,
                                      max_tokens=body.max_tokens, timeout=30, light=True)
    if err:
        return {"ok": False, "degraded": True, "notes": "",
                "code": getattr(code, "value", str(code)), "message": err}
    return {"ok": True, "notes": text or ""}


@router.post("/coach/ask")
async def ask(request: Request, body: AskRequest):
    """基于课堂转写稿回答问题。"""
    question = (body.question or "").strip()
    if not question:
        return {"ok": False, "message": "问题为空"}
    ctx = (body.transcript or "").strip()
    user = (
        "【课堂转写稿】\n"
        + (ctx[:6000] if ctx else "（暂无转写稿，请只基于常识作答，并说明这是推测）")
        + f"\n\n【学生问题】\n{question}"
    )
    text, code, err = await _complete(request, _ASK_SYSTEM, user,
                                      max_tokens=1600, timeout=45)
    if err:
        return {"ok": False, "degraded": True, "answer": "",
                "code": getattr(code, "value", str(code)), "message": err}
    return {"ok": True, "answer": text or ""}
