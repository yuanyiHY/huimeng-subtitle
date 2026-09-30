#!/bin/bash
# 一键把本项目发布到 GitHub（建仓库 + 推送 + 可选建首个 Release）
#
# 用法：
#   GITHUB_TOKEN=github_pat_xxx ./scripts/init-github.sh <owner> [repo-name]
#
# 例：
#   GITHUB_TOKEN=github_pat_xxx ./scripts/init-github.sh fengqishui huimeng-subtitle
#
# Token 权限（Fine-grained）：
#   Repository access : All repositories（新账号还没有仓库，只能选这个）
#   Permissions       : Contents: Read and write
#                       Administration: Read and write   ← 建仓库需要
set -euo pipefail

OWNER="${1:?用法: GITHUB_TOKEN=xxx $0 <owner> [repo]}"
REPO="${2:-huimeng-subtitle}"
TOKEN="${GITHUB_TOKEN:?请通过环境变量提供 GITHUB_TOKEN}"

API_BASE="${GITHUB_API_BASE:-https://api.github.com}"
PUSH_URL="${GITHUB_PUSH_URL:-}"

cd "$(dirname "$0")/.."

say() { printf '\033[1;36m▸ %s\033[0m\n' "$1"; }
die() { printf '\033[1;31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------- 0. 提交前体检
say "提交前体检"
if git grep -qE "sk-[A-Za-z0-9_-]{32,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}" HEAD 2>/dev/null; then
  die "当前提交里发现疑似密钥，先清理再发布"
fi
git rev-parse --verify HEAD >/dev/null 2>&1 || die "还没有任何提交"
echo "  ✓ 无明文密钥"
echo "  ✓ 提交数 $(git rev-list --count HEAD)，文件数 $(git ls-files | wc -l | tr -d ' ')"

# ---------------------------------------------------------------- 1. 建仓库
say "创建仓库 ${OWNER}/${REPO}"
CODE="$(curl -sS -o /tmp/gh_newrepo.json -w '%{http_code}' -X POST \
  -H "Authorization: token ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "${API_BASE}/user/repos" \
  -d "{\"name\":\"${REPO}\",\"description\":\"绘梦subtitle —— macOS 实时语音翻译与智能整理\",\"private\":false,\"has_issues\":true,\"has_wiki\":false}")"
case "$CODE" in
  201) echo "  ✓ 仓库已创建"
       python3 -c "import json;d=json.load(open('/tmp/gh_newrepo.json'));print('   ',d['html_url'])" ;;
  422) echo "  （仓库已存在，直接使用）" ;;
  *)   die "创建失败：HTTP $CODE $(head -c 300 /tmp/gh_newrepo.json)" ;;
esac

# ---------------------------------------------------------------- 2. 推送
say "推送代码"
# token 只出现在这一次性的 URL 里，不写进 git 配置
[ -n "$PUSH_URL" ] || PUSH_URL="https://x-access-token:${TOKEN}@github.com/${OWNER}/${REPO}.git"
git push "$PUSH_URL" HEAD 2>&1 | tail -3
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/${OWNER}/${REPO}.git"
echo "  ✓ 已推送（git 配置里只留不带 token 的地址）"

echo
say "完成"
echo "  仓库地址 : https://github.com/${OWNER}/${REPO}"
echo "  下一步   : GITHUB_TOKEN=xxx ./scripts/publish-release.sh ${OWNER}/${REPO}"
