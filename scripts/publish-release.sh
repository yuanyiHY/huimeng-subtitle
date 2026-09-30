#!/bin/bash
# 发布新版本到 GitHub Releases（同时生成应用内「检查更新」用的 latest.json）
#
# 用法：
#   GITHUB_TOKEN=ghp_xxx ./scripts/publish-release.sh <owner/repo> [更新说明文件]
#
# 例：
#   GITHUB_TOKEN=ghp_xxx ./scripts/publish-release.sh fengqishui/huimeng-subtitle
#
# 做四件事：
#   1) 生成 dist/latest.json（更新源，格式见 README）
#   2) 打 tag 并推送当前分支与 tag
#   3) 在 GitHub 上建 Release
#   4) 上传 DMG 与 latest.json 作为 Release 资产
set -euo pipefail

REPO="${1:?用法: GITHUB_TOKEN=xxx $0 owner/repo [说明文件]}"
TOKEN="${GITHUB_TOKEN:?请通过环境变量提供 GITHUB_TOKEN}"
NOTES_FILE="${2:-}"

cd "$(dirname "$0")/.."
VERSION="$(tr -d '[:space:]' < VERSION)"
TAG="v${VERSION}"
DMG="dist/绘梦subtitle-v${VERSION}.dmg"
NAME="$(basename "$DMG")"
API="${GITHUB_API_BASE:-https://api.github.com}/repos/${REPO}"
UPLOAD="${GITHUB_UPLOAD_BASE:-https://uploads.github.com}/repos/${REPO}"

say() { printf '\033[1;36m▸ %s\033[0m\n' "$1"; }
die() { printf '\033[1;31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

[ -f "$DMG" ] || die "找不到安装包：$DMG\n请先执行 ./build-dmg.sh"
[ -n "${GITHUB_TOKEN:-}" ] || die "缺少 GITHUB_TOKEN"

# ---------------------------------------------------------------- 1. 更新源
say "生成 dist/latest.json（应用内更新源）"
if [ -n "$NOTES_FILE" ] && [ -f "$NOTES_FILE" ]; then
  NOTES="$(cat "$NOTES_FILE")"
else
  NOTES="v${VERSION} 更新"
fi
python3 - "$DMG" "$REPO" "$TAG" "$NAME" "$NOTES" > dist/latest.json <<'PY'
import json, os, sys
dmg, repo, tag, name, notes = sys.argv[1:6]
json.dump({
    "version": tag.lstrip("v"),
    "download_url": f"https://github.com/{repo}/releases/download/{tag}/{name}",
    "size": os.path.getsize(dmg),
    "notes": notes,
}, sys.stdout, ensure_ascii=False, indent=2)
PY
cat dist/latest.json
echo

# ---------------------------------------------------------------- 2. 推送
say "推送代码与 tag 到 ${REPO}"
git tag -a "$TAG" -m "v${VERSION}" 2>/dev/null || echo "  （tag $TAG 已存在，跳过）"
git push "${GITHUB_PUSH_URL:-https://x-access-token:${TOKEN}@github.com/${REPO}.git}" HEAD --tags

# ---------------------------------------------------------------- 3. 建 Release
say "创建 GitHub Release ${TAG}"
RELEASE_ID="$(python3 - "$API" "$TOKEN" "$TAG" "$NOTES" <<'PY'
import json, sys, urllib.request
api, token, tag, notes = sys.argv[1:5]
body = json.dumps({"tag_name": tag, "name": tag, "body": notes, "draft": False,
                   "prerelease": False}).encode()
req = urllib.request.Request(api + "/releases", data=body, method="POST",
                             headers={"Authorization": f"token {token}",
                                      "Accept": "application/vnd.github+json",
                                      "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print(json.loads(r.read().decode())["id"])
except urllib.error.HTTPError as e:
    detail = e.read().decode()[:300]
    if e.code == 422 and "already_exists" in detail:
        # 已存在则复用
        req2 = urllib.request.Request(api + f"/releases/tags/{tag}",
                                      headers={"Authorization": f"token {token}"})
        with urllib.request.urlopen(req2, timeout=30) as r:
            print(json.loads(r.read().decode())["id"])
    else:
        sys.stderr.write(f"创建 Release 失败：{e.code} {detail}\n")
        sys.exit(1)
PY
)" || die "创建 Release 失败"
echo "  release id = $RELEASE_ID"

# ---------------------------------------------------------------- 4. 上传资产
upload() {
  local file="$1" mime="$2"
  say "上传 $(basename "$file")（$(du -h "$file" | awk '{print $1}')）"
  local code
  # 资产名可能是中文（如 绘梦subtitle-v3.3.1.dmg），放进 query string 前必须做
  # 百分号编码；否则 GitHub 直接返回 400 Bad Request
  local name enc
  name="$(basename "$file")"
  enc="$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$name")"
  code="$(curl -sS -o /tmp/gh_upload.json -w '%{http_code}' -X POST \
    -H "Authorization: token ${TOKEN}" \
    -H "Content-Type: ${mime}" \
    --data-binary @"$file" \
    "${UPLOAD}/releases/${RELEASE_ID}/assets?name=${enc}")"
  if [ "$code" = "201" ] || [ "$code" = "200" ]; then
    say "  上传成功"
  elif [ "$code" = "422" ]; then
    echo "  （同名资产已存在，跳过）"
  else
    die "上传失败：HTTP $code $(head -c 200 /tmp/gh_upload.json)"
  fi
}

upload "$DMG" "application/x-apple-diskimage"
upload "dist/latest.json" "application/json"

say "完成"
echo "  下载页   : https://github.com/${REPO}/releases/tag/${TAG}"
echo "  更新源   : https://github.com/${REPO}/releases/latest/download/latest.json"
echo
echo "把上面这个「更新源」填进 config.yaml 的 update.feed_url，应用内就能检查更新了。"
