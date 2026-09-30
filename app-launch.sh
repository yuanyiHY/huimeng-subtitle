#!/bin/bash
# 绘梦subtitle 启动脚本（桌面路径版）
# 职责：环境自检 → 启动后端 + 原生窗口（若后端已在运行则只开窗口）

PROJECT="/Users/fengqishui/Desktop/国际实时翻译/Int-RealTime-Translate"
PY="$PROJECT/.venv/bin/python"

fail_dialog() {
  /usr/bin/osascript -e "display dialog \"$1\" buttons {\"好\"} default button 1 with icon caution with title \"绘梦subtitle\"" >/dev/null 2>&1
}

# 环境自检：项目目录与 venv
if [ ! -d "$PROJECT" ]; then
  fail_dialog "找不到应用目录：\n$PROJECT\n\n请确认应用文件夹位置未被移动。"
  exit 1
fi
if [ ! -x "$PY" ]; then
  fail_dialog "未找到运行环境（.venv）。\n\n请打开「终端」，在应用目录执行：\n  python3 -m venv .venv\n  .venv/bin/pip install -r requirements.txt\n\n完成后重新双击本应用。"
  exit 1
fi

cd "$PROJECT" || exit 1

# 后端已在运行 → 仅打开窗口连接现有后端
if /usr/bin/curl -s -m 2 http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
    "$PY" - <<'PY'
import webview
webview.create_window(
    "绘梦subtitle",
    "http://127.0.0.1:8000/",
    width=1240, height=780, min_size=(980, 640),
    background_color="#FAFAF8",
)
webview.start()
PY
    exit 0
fi

# 全新启动：后端 + 原生窗口
exec "$PY" run.py --window
