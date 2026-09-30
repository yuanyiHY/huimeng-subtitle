#!/bin/bash

# 绘梦subtitle DMG 打包脚本（简化版）

set -e

APP_NAME="绘梦subtitle"
VERSION="1.2.1"
DMG_NAME="${APP_NAME}-v${VERSION}.dmg"
VOLUME_NAME="${APP_NAME}"
SOURCE_APP="${APP_NAME}.app"
BUILD_DIR="dmg-build"

echo "🚀 开始打包 ${APP_NAME} v${VERSION}"
echo ""

# 1. 清理旧构建
echo "🧹 清理旧构建..."
rm -rf "$BUILD_DIR"
rm -f "$DMG_NAME"
mkdir -p "$BUILD_DIR"

# 2. 复制应用
echo "📦 复制应用..."
if [ ! -d "$SOURCE_APP" ]; then
  echo "❌ 错误: 找不到 ${SOURCE_APP}"
  exit 1
fi
cp -R "$SOURCE_APP" "$BUILD_DIR/"

# 3. 创建应用程序快捷方式
echo "🔗 创建应用程序链接..."
ln -s /Applications "$BUILD_DIR/应用程序"

# 4. 复制文档
echo "📄 复制文档..."
cp 安装说明.md "$BUILD_DIR/"
cp FAQ.md "$BUILD_DIR/"
cp README.md "$BUILD_DIR/" 2>/dev/null || true

# 5. 创建自述文件
echo "📝 生成自述文件..."
cat > "$BUILD_DIR/使用说明.txt" << 'READMEEOF'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  绘梦subtitle v1.1.0
  多语言实时翻译工具
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 安装方法：

  1. 将「绘梦subtitle.app」拖到「应用程序」文件夹
  2. 双击启动，首次运行需要授权
  3. 配置 API 密钥即可开始使用

🔑 需要的 API 密钥：

  • 实时同传模式：阿里云百炼 API Key
    https://dashscope.console.aliyun.com/
    
  • 本地模式：DeepSeek API Key
    https://platform.deepseek.com/

📖 详细说明：

  请查看「安装说明.md」和「FAQ.md」

💡 快速开始：

  1. 打开应用
  2. 点击「实时字幕」
  3. 选择语言方向
  4. 点击「开始录音」

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

享受无障碍的多语言交流！🌏✨
READMEEOF

# 6. 直接创建压缩 DMG
echo "💿 创建 DMG..."
hdiutil create -volname "$VOLUME_NAME" \
  -srcfolder "$BUILD_DIR" \
  -ov -format UDZO \
  -imagekey zlib-level=9 \
  "$DMG_NAME"

# 7. 清理
echo "🧹 清理临时文件..."
rm -rf "$BUILD_DIR"

# 8. 完成
echo ""
echo "✅ 打包完成！"
echo ""
echo "📦 文件: $DMG_NAME"
ls -lh "$DMG_NAME"
echo ""
echo "🎉 可以分发了！"
