#!/bin/bash
# 绘梦subtitle 自包含打包脚本
#
# 目标：产出一个「拷给别人就能用」的 DMG —— Python 运行时、依赖、程序代码
# 全部塞进 .app 包内，不依赖本机任何路径、虚拟环境或已装 Python。
#
# 用法：
#   ./build-dmg.sh              正常打包，输出 dist/绘梦subtitle-v<版本>.dmg
#   ./build-dmg.sh --keep       保留 dist/stage 下已解开的 .app（排错用）
#
# 两个关键点（都是踩过的坑）：
#   1) 不用 venv。内置 Python 的二进制里带着编译期写死的路径，venv 的
#      pyvenv.cfg 又是绝对路径 —— 两者都会让 App 一挪位置就找不到标准库。
#      做法是把依赖直接合并进内置 Python，启动时用 PYTHONHOME 钉死位置。
#   2) 不打包 .env（里面有你的 API Key）；对方首次使用自己在设置里填。
#
# 语音识别模型（whisper）体积大且按需下载，不打进包里。
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="绘梦subtitle"
EXEC_NAME="HuimengSubtitle"
VERSION="$(tr -d '[:space:]' < "$PROJECT_ROOT/VERSION")"
DIST="$PROJECT_ROOT/dist"
STAGE="$DIST/stage"
BUNDLE="$STAGE/$APP_NAME.app"
DMG="$DIST/${APP_NAME}-v${VERSION}.dmg"

# 内置 Python 的来源：uv 管理的独立 CPython（自带 lib，无外部动态库依赖）
PYTHON_SRC="${PYTHON_SRC:-$HOME/.local/share/uv/python/cpython-3.11-macos-aarch64-none}"
SITE_SRC="$PROJECT_ROOT/.venv/lib/python3.11/site-packages"

say() { printf '\033[1;36m▸ %s\033[0m\n' "$1"; }
ok()  { printf '\033[1;32m  ✓ %s\033[0m\n' "$1"; }
die() { printf '\033[1;31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

[ -d "$PYTHON_SRC" ] || die "找不到 Python 运行时：$PYTHON_SRC（可用 PYTHON_SRC=... 指定）"
[ -d "$SITE_SRC" ]   || die "找不到依赖目录：$SITE_SRC"
[ -f "$PROJECT_ROOT/app-icon.icns" ] || die "找不到图标 app-icon.icns"

# ---------------------------------------------------------------- 1. 清理
say "清理旧的构建产物"
rm -rf "$BUNDLE" "$DMG"
mkdir -p "$BUNDLE/Contents/MacOS" "$BUNDLE/Contents/Resources"

# ---------------------------------------------------------------- 2. 程序代码
say "复制程序代码（不含 .env / 虚拟环境 / 截图 / 历史备份）"
APP_DIR="$BUNDLE/Contents/Resources/app"
mkdir -p "$APP_DIR"
rsync -a \
  --exclude '.venv' --exclude '.env' --exclude '.env.example' \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
  --exclude 'dist' --exclude '*.app' --exclude '*.dmg' \
  --exclude '_backup_v2' --exclude '截图-v3' --exclude '.git' \
  --exclude 'create-dmg*.sh' --exclude 'build-dmg.sh*' \
  "$PROJECT_ROOT/" "$APP_DIR/"

# 对方机器上没有你的云端 Key：翻译引擎固定走云端。若留 auto，
# 未配置时会回退本地 NLLB，触发 2.5GB 模型下载
python3 - "$APP_DIR/config.yaml" <<'PY'
import io, re, sys
path = sys.argv[1]
text = io.open(path, encoding="utf-8").read()
text = re.sub(r"^(mt:\n(?:.*\n)*?\s+engine:\s*).*$", r"\1cloud", text, count=1, flags=re.M)
text = ("# 打包版配置：翻译固定走云端。\n"
        "# 首次使用请在「设置 → 模型设置」里填入你自己的 API Key。\n") + text
io.open(path, "w", encoding="utf-8").write(text)
PY
# 更新源：优先取环境变量 UPDATE_FEED_URL，其次取仓库根的 update-feed.txt。
# 有了它，用户装完就能在「设置 → 关于／更新」里直接检查更新，无需手工配置。
FEED_URL="${UPDATE_FEED_URL:-}"
if [ -z "$FEED_URL" ] && [ -f "$PROJECT_ROOT/update-feed.txt" ]; then
  FEED_URL="$(tr -d '[:space:]' < "$PROJECT_ROOT/update-feed.txt")"
fi
if [ -n "$FEED_URL" ]; then
  python3 - "$APP_DIR/config.yaml" "$FEED_URL" <<'PYEOF'
import io, re, sys
path, feed = sys.argv[1], sys.argv[2]
text = io.open(path, encoding="utf-8").read()
text = re.sub(r'^(\s*feed_url:\s*).*$', lambda m: m.group(1) + '"' + feed + '"',
              text, count=1, flags=re.M)
io.open(path, "w", encoding="utf-8").write(text)
PYEOF
  ok "config.yaml: mt.engine -> cloud, 更新源已内置"
  echo "     $FEED_URL"
else
  ok "config.yaml: mt.engine -> cloud（未指定更新源，应用内会提示未配置）"
fi

# ---------------------------------------------------------------- 3. Python 运行时 + 依赖
say "复制 Python 运行时"
rsync -a --exclude '__pycache__' "$PYTHON_SRC/" "$BUNDLE/Contents/Resources/python/"
ok "$(du -sh "$BUNDLE/Contents/Resources/python" | awk '{print $1}')"

say "合并依赖到内置 Python（约 1.3GB，稍慢）"
rsync -a --exclude '__pycache__' "$SITE_SRC/" \
  "$BUNDLE/Contents/Resources/python/lib/python3.11/site-packages/"
ok "site-packages 就位"

# .pth 里如果写着构建机的绝对路径，换台机器就会指向不存在的目录
BAD_PTH="$(grep -rl '^/' "$BUNDLE/Contents/Resources/python/lib/python3.11/site-packages/"*.pth 2>/dev/null || true)"
if [ -n "$BAD_PTH" ]; then
  printf '\033[1;33m  ! 以下 .pth 含绝对路径，请确认目标机也存在：\n%s\033[0m\n' "$BAD_PTH"
fi

# ---------------------------------------------------------------- 4. 图标与元信息
cp "$PROJECT_ROOT/app-icon.icns" "$BUNDLE/Contents/Resources/app-icon.icns"
cp "$PROJECT_ROOT/VERSION" "$BUNDLE/Contents/Resources/VERSION"

cat > "$BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key><string>${APP_NAME}</string>
  <key>CFBundleExecutable</key><string>${EXEC_NAME}</string>
  <key>CFBundleIdentifier</key><string>com.fengqishui.intrealtimetranslate</string>
  <key>CFBundleIconFile</key><string>app-icon.icns</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>${APP_NAME} 需要使用麦克风，用于实时语音转写和多语言翻译。</string>
</dict>
</plist>
PLIST

# ---------------------------------------------------------------- 5. 启动器
cat > "$BUNDLE/Contents/MacOS/$EXEC_NAME" <<'LAUNCHER'
#!/bin/bash
# 绘梦subtitle 启动器（自包含版）：所有路径相对于本 App 包，不依赖任何外部目录
set -u

CONTENTS="$(cd "$(dirname "$0")/.." && pwd)"
RES="$CONTENTS/Resources"
APP="$RES/app"
PY="$RES/python/bin/python3.11"
DATA="$HOME/Library/Application Support/intrealtimetranslate"

fail() {
  /usr/bin/osascript -e "display dialog \"$1\" buttons {\"好\"} default button 1 with icon caution with title \"绘梦subtitle\"" >/dev/null 2>&1
  exit 1
}

[ -x "$PY" ] || fail "应用包不完整：找不到内置运行环境。\n请重新下载安装包，或把 App 拖到「应用程序」文件夹后再打开。"
[ -f "$APP/run.py" ] || fail "应用包不完整：找不到程序文件（run.py）。"

# 钉死 Python 位置：内置解释器里带着打包机的路径，不钉的话换台电脑会找不到标准库
export PYTHONHOME="$RES/python"
export PYTHONDONTWRITEBYTECODE=1

# 配置写在用户数据目录：App 包内只读且带签名，不能往里写
mkdir -p "$DATA"
export IRT_ENV_FILE="$DATA/.env"

# 日志落到文件：从 Finder 启动的 App 没有终端，出问题时否则无从查起
LOGDIR="$HOME/Library/Logs"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/绘梦subtitle.log"
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 2000000 ]; then
  mv -f "$LOG" "$LOG.1"
fi
exec >> "$LOG" 2>&1
echo ""
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 启动 ====="
echo "PYTHONHOME=$PYTHONHOME"
echo "IRT_ENV_FILE=$IRT_ENV_FILE"

# 从旧的「桌面项目目录」版本升级时，把已有配置（API Key）带过来，只做一次
if [ ! -f "$IRT_ENV_FILE" ]; then
  for old in "$HOME/Desktop/国际实时翻译/Int-RealTime-Translate/.env" \
             "$HOME/Desktop/绘梦subtitle/Int-RealTime-Translate/.env"; do
    if [ -f "$old" ]; then cp "$old" "$IRT_ENV_FILE"; break; fi
  done
fi

# 首次下载语音识别模型走国内镜像，避免 HuggingFace 连不上
[ -z "${HF_ENDPOINT:-}" ] && export HF_ENDPOINT="https://hf-mirror.com"

cd "$APP" || fail "无法进入程序目录：$APP"

# 后端已经在跑 → 只开窗口，避免重复启动抢端口
if /usr/bin/curl -s -m 2 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  exec "$PY" - <<'PYEOF'
import webview
webview.create_window("绘梦subtitle", "http://127.0.0.1:8000/",
                      width=1240, height=780, min_size=(980, 640),
                      background_color="#FAFAF8")
webview.start()
PYEOF
fi

exec "$PY" run.py --window
LAUNCHER
chmod +x "$BUNDLE/Contents/MacOS/$EXEC_NAME"

# ---------------------------------------------------------------- 6. 自检
say "自检：确认运行时完全落在包内"
SELF_TEST="$(PYTHONHOME="$BUNDLE/Contents/Resources/python" \
  "$BUNDLE/Contents/Resources/python/bin/python3.11" -c "
import os
print(os.__file__)
try:
    import fastapi, uvicorn, numpy, soundfile, webview, sounddevice, websockets, mlx.core
    print('IMPORTS_OK')
except Exception as exc:
    print('IMPORT_FAIL', exc)
" 2>&1)"

echo "$SELF_TEST" | grep -q "IMPORTS_OK" || die "自检失败，依赖导入不通过：$SELF_TEST"
echo "$SELF_TEST" | head -1 | grep -q "$BUNDLE" || die "自检失败：标准库仍指向包外（$(echo "$SELF_TEST" | head -1)）"
ok "运行时路径正确，依赖导入通过"

# 包里有两份 VERSION：Resources/VERSION（给人看）与 Resources/app/VERSION（后端读，
# 决定"检查更新"里的当前版本）。两者不一致会导致装完新版仍上报旧版本、反复提示更新。
APP_VERSION_FILE="$BUNDLE/Contents/Resources/app/VERSION"
[ -f "$APP_VERSION_FILE" ] || die "自检失败：缺少 Resources/app/VERSION"
APP_VER="$(tr -d '[:space:]' < "$APP_VERSION_FILE")"
[ "$APP_VER" = "$VERSION" ] || die "自检失败：版本号不一致（外层 ${VERSION}，后端读到 ${APP_VER}）"
ok "版本号一致（${VERSION}）"

# ---------------------------------------------------------------- 7. 签名
say "ad-hoc 签名"
codesign --force --deep -s - "$BUNDLE" >/dev/null 2>&1 || die "签名失败"
codesign -v "$BUNDLE" || die "签名校验失败"
ok "签名有效"

# ---------------------------------------------------------------- 8. 打包 DMG
say "生成 DMG"
ln -sfn /Applications "$STAGE/Applications"
cat > "$STAGE/安装说明.txt" <<'TXT'
绘梦subtitle · 安装说明
============================

【安装】
  1. 把左边的「绘梦subtitle」拖到右边的「Applications（应用程序）」文件夹
  2. 打开「启动台」或「应用程序」，找到 绘梦subtitle 双击

【第一次打开被系统拦下怎么办】
  因为这是个人开发的应用、没有购买苹果开发者证书，macOS 会提示
  「无法打开，因为无法验证开发者」。这是正常的，按下面做一次即可：

    在「应用程序」里找到 绘梦subtitle
    → 按住 Control 键点它（或右键）
    → 选「打开」
    → 弹窗里再点一次「打开」

  之后就能正常双击启动了，不用每次都这样操作。
  （如果还是不行：系统设置 → 隐私与安全性 → 拉到底部 → 点「仍要打开」）

【第一次使用要配置】
  应用本身不含 API Key（每个人用自己的）。
  打开后进「设置 → 模型设置」，填三个模型的配置：
    · 深度思考模型：负责会议整理 / 随堂笔记（推荐 DeepSeek）
    · 轻量实时模型：负责录音时的实时总结（可以直接填同一个）
    · 专用翻译模型：负责翻译（推荐阿里云百炼 qwen-mt-lite）
  填完点「测试全部连接」确认通了，再点「保存设置」。

【语音识别】
  首次使用「实时翻译 / 文件转写」时，会自动下载语音识别模型（约 500MB），
  需要联网并等待一会儿，之后就一直用本地的、不再下载。
  想更准可以改包内 config.yaml 的 asr.local.model
  （改成 mlx-community/whisper-large-v3-turbo，约 1.5GB）。

【出问题了怎么查】
  应用日志在：~/Library/Logs/绘梦subtitle.log
  出问题时的报错都记在这里，反馈时把最后几十行发过来就行。

【系统要求】
  · Apple 芯片的 Mac（M1/M2/M3/M4 均可）
  · macOS 13.0 或更高
  · 麦克风权限：第一次录音时系统会弹窗，点「允许」

【数据存在哪】
  ~/Library/Application Support/intrealtimetranslate/   （记录、整理结果、配置）
  ~/Documents/intrealtimetranslate-recordings/           （录音文件）
  卸载时把这两个目录删掉即可，应用本体直接拖到废纸篓。
TXT

hdiutil create -volname "${APP_NAME}" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null

if [ "${1:-}" != "--keep" ]; then rm -rf "$STAGE"; fi

say "完成：${DMG}"
du -h "${DMG}" | awk '{print "  大小: " $1}'
echo "  双击 DMG 即可看到安装界面"
