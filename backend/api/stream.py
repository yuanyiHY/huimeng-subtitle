"""WebSocket live subtitles: receive mono float32 @16kHz PCM chunks, buffer to a
sentence-ish window, run mlx-whisper + MT, push segment_final frames, and on
disconnect save the whole recording (WAV + subtitles JSON) named by start time.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

router = APIRouter()

CHUNK_SECONDS = 2.5
SR = 16000

# Kept for the live-subtitles polling endpoint.
LIVE_SUBTITLES: list = []


def _state(ws: WebSocket):
    return ws.scope["app"].state


def _write_recording(rec_dir: Path, started_at: str,
                     chunks: list, subtitles: list) -> None:
    """Persist a finished recording as <started_at>.wav + .json."""
    if not chunks:
        return
    audio = np.concatenate(chunks).astype(np.float32)
    if len(audio) < SR * 1.0:  # shorter than 1s: skip
        return
    try:
        import soundfile as sf
        rec_dir = Path(rec_dir)
        rec_dir.mkdir(parents=True, exist_ok=True)
        wav_path = rec_dir / f"{started_at}.wav"
        sf.write(str(wav_path), audio, SR)
        meta_path = rec_dir / f"{started_at}.json"
        meta_path.write_text(
            json.dumps({"started_at": started_at, "duration": len(audio) / SR,
                        "subtitles": subtitles}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[stream] 录音已保存: {wav_path.name} "
              f"({len(audio)/SR:.1f}s, {len(subtitles)} 条字幕)", flush=True)
    except Exception as exc:  # pragma: no cover
        print(f"[stream] 保存录音失败: {exc}", flush=True)


@router.websocket("/stream")
async def stream(websocket: WebSocket):
    await websocket.accept()
    state = _state(websocket)
    asr = state.asr_engine
    mt = state.mt_engine
    rec_dir = state.settings.recordings_dir

    # 语言方向：?src=ko&tgt=zh  模式：?mode=local|realtime
    src = websocket.query_params.get("src", "ko")
    tgt = websocket.query_params.get("tgt", "zh")
    mode = websocket.query_params.get("mode", "local")
    print(f"[stream] 语言方向: {src} -> {tgt}, 模式: {mode}", flush=True)

    LIVE_SUBTITLES.clear()
    started_at = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    all_chunks: list = []

    # Push engine status once so the client renders state immediately.
    await websocket.send_json({
        "type": "engine_status",
        "engine": "realtime" if mode == "realtime" else asr.name,
        "degraded": not asr.available() or not mt.available(),
    })

    if mode == "realtime":
        await _stream_realtime(websocket, state, src, tgt, rec_dir,
                               started_at, all_chunks)
        return

    buffer: list = []
    total_samples = 0
    elapsed_samples = 0
    proc_lock = asyncio.Lock()

    MIN_SAMPLES = int(1.5 * SR)   # 最短转写长度
    MAX_SAMPLES = int(12 * SR)    # 最长强制切段
    TAIL_SAMPLES = int(0.6 * SR)  # 静音尾巴判断窗口

    def _cut_and_transcribe(force: bool = False):
        nonlocal buffer, total_samples
        if total_samples < MIN_SAMPLES and not force:
            return
        audio = np.concatenate(buffer).astype(np.float32)
        start_sec = (elapsed_samples - total_samples) / SR
        buffer, total_samples = [], 0
        asyncio.create_task(_process_chunk(websocket, asr, mt, audio, proc_lock,
                                           start_sec, src, tgt))

    async def _save_later():
        # Wait briefly so the last pending transcription can land.
        await asyncio.sleep(2.0)
        _write_recording(rec_dir, started_at, all_chunks, list(LIVE_SUBTITLES))

    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if not data:
                continue
            arr = np.frombuffer(data, dtype=np.float32)
            all_chunks.append(arr)
            buffer.append(arr)
            total_samples += len(arr)
            elapsed_samples += len(arr)

            if total_samples >= MAX_SAMPLES:
                # 说太久没停顿，强制切
                _cut_and_transcribe(force=True)
                continue
            if total_samples >= MIN_SAMPLES + TAIL_SAMPLES:
                # 停顿检测：尾部 0.6s 静音则切（一句话说完才切）
                tail = np.concatenate(buffer)[-TAIL_SAMPLES:]
                tail_rms = float(np.sqrt(np.mean(tail.astype(np.float64) ** 2)))
                if tail_rms < 0.015:
                    _cut_and_transcribe()
    except WebSocketDisconnect:
        pass
    finally:
        # Flush any remaining buffered audio.
        if buffer:
            audio = np.concatenate(buffer).astype(np.float32)
            start_sec = (elapsed_samples - total_samples) / SR
            try:
                await _process_chunk(websocket, asr, mt, audio, proc_lock,
                                     start_sec, src, tgt)
            except Exception:
                pass
        asyncio.create_task(_save_later())


async def _stream_realtime(websocket: WebSocket, state, src: str, tgt: str,
                           rec_dir, started_at: str, all_chunks: list) -> None:
    """实时同传模式：音频直发百炼，流式字幕写入 LIVE_SUBTITLES。"""
    from backend.mt.livetranslate_engine import (LiveTranslateSession,
                                                 SubtitleAccumulator)
    api_key = state.settings.mt_cloud_api_key
    if not api_key:
        try:
            await websocket.send_json({"type": "engine_error",
                                       "code": "API_KEY_MISSING",
                                       "message": "未配置云端 API Key（实时同传需要联网）"})
        except Exception:
            pass
        return
    elapsed = [0]
    acc = SubtitleAccumulator(LIVE_SUBTITLES, lambda: elapsed[0] / SR)
    session = LiveTranslateSession(api_key, src, tgt, on_event=acc.on_event,
                                   model=state.settings.livetranslate_model)
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, session.start)
    if not ok:
        try:
            await websocket.send_json({"type": "engine_error",
                                       "code": "ENGINE_UNAVAILABLE",
                                       "message": session.error or "实时同传连接失败"})
        except Exception:
            pass
        return
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if not data:
                continue
            arr = np.frombuffer(data, dtype=np.float32)
            all_chunks.append(arr)
            elapsed[0] += len(arr)
            pcm16 = (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            session.send_audio(pcm16)
    except WebSocketDisconnect:
        pass
    finally:
        await loop.run_in_executor(None, session.stop)
        acc.finish()
        import threading as _threading
        _threading.Thread(target=_write_recording,
                          args=(rec_dir, started_at, all_chunks, list(LIVE_SUBTITLES)),
                          daemon=True).start()


async def _process_chunk(websocket: WebSocket, asr, mt, audio: np.ndarray,
                         proc_lock: asyncio.Lock, start_sec: float = 0.0,
                         src: str = "ko", tgt: str = "zh") -> None:
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(audio)))
    print(f"[stream] 音频幅度 rms={rms:.4f} peak={peak:.4f} ({len(audio)/SR:.1f}s)", flush=True)
    if rms < 0.015:
        print(f"[stream] 音频近乎静音(rms={rms:.4f})，跳过转写", flush=True)
        return
    try:
        # 串行执行转写+翻译，避免多线程同时加载/运行模型
        async with proc_lock:
            import time as _time
            loop = asyncio.get_running_loop()
            _t0 = _time.time()
            segs = await loop.run_in_executor(None, asr.transcribe_array, audio, src)
            _t1 = _time.time()
            text = " ".join(s.text for s in segs).strip()
            print(f"[stream] transcribe({len(audio)/SR:.1f}s) -> {text!r} ({_t1-_t0:.2f}s)", flush=True)
            if not text:
                print(f"[stream] 空文本，跳过", flush=True)
                return
            zh = ""
            if mt.available():
                translations = await loop.run_in_executor(None, mt.translate, [text], src, tgt)
                zh = (translations[0] if translations else "").strip()
            _t2 = _time.time()
            print(f"[stream] translate -> {zh!r} ({_t2-_t1:.2f}s)", flush=True)
        payload = {
            "type": "segment_final",
            "start": round(start_sec, 1),
            "end": round(start_sec + len(audio) / SR, 1),
            "ko": text,
            "zh": zh,
        }
        LIVE_SUBTITLES.append({
            "ko": text, "zh": zh,
            "start": round(start_sec, 1),
            "end": round(start_sec + len(audio) / SR, 1),
        })
        print(f"[stream] send segment_final (ko={len(text)}字, zh={len(zh)}字)", flush=True)
        try:
            await websocket.send_json(payload)
        except Exception as exc:
            print(f"[stream] send失败(客户端已关闭?): {exc}", flush=True)
            # client may have closed the connection mid-inference; ignore.
            pass
    except Exception as exc:  # pragma: no cover
        from backend.errors import classify_exception
        try:
            await websocket.send_json({
                "type": "engine_error",
                "code": classify_exception(exc).value,
                "message": str(exc)[:200],
            })
        except Exception:
            pass


@router.get("/live/subtitles")
async def live_subtitles():
    return {"ok": True, "subtitles": list(LIVE_SUBTITLES)}


@router.post("/live/wslog")
async def ws_log(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    print(f"[wslog] 前端WS关闭: {data}", flush=True)
    return {"ok": True}
