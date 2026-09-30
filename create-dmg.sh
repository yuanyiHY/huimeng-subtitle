#!/bin/bash

# 绘梦subtitle DMG 打包脚本

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
cp README.md "$BUILD_DIR/" 2>/dev/null || echo "  (README.md 不存在，跳过)"

# 5. 创建自述文件
echo "📝 生成自述文件..."
cat > "$BUILD_DIR/README.txt" << 'READMEEOF'
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

# 6. 创建临时 DMG
echo "💿 创建临时 DMG..."
hdiutil create -volname "$VOLUME_NAME" \
  -srcfolder "$BUILD_DIR" \
  -ov -format UDRW \
  -fs HFS+ \
  temp.dmg

# 7. 挂载 DMG
echo "🔧 配置 DMG 布局..."
MOUNT_DIR=$(hdiutil attach -readwrite -noverify -noautoopen "temp.dmg" | egrep '^/dev/' | sed 1q | awk '{print $3}')

if [ -z "$MOUNT_DIR" ]; then
  echo "❌ 错误: 无法挂载 DMG"
  exit 1
fi

echo "  挂载点: $MOUNT_DIR"

# 8. 设置 DMG 样式
echo "🎨 设置外观..."

# 设置背景色（如果有背景图可以用 osascript 设置）
# 这里用简单的 Finder 设置
osascript <<EOD
tell application "Finder"
  tell disk "$VOLUME_NAME"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {100, 100, 700, 500}
    set viewOptions to the icon view options of container window
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 96
    set background color of viewOptions to {65535, 65535, 65535}
    
    -- 设置图标位置
    set position of item "${APP_NAME}.app" of container window to {150, 180}
    set position of item "应用程序" of container window to {450, 180}
    set position of item "README.txt" of container window to {300, 320}
    
    close
    open
    update without registering applications
    delay 2
  end tell
end tell
EOD

# 9. 卸载临时 DMG
echo "💾 卸载临时 DMG..."
hdiutil detach "$MOUNT_DIR"

# 10. 压缩为最终 DMG
echo "🗜️  压缩最终 DMG..."
hdiutil convert temp.dmg \
  -format UDZO \
  -imagekey zlib-level=9 \
  -o "$DMG_NAME"

# 11. 清理
echo "🧹 清理临时文件..."
rm -f temp.dmg
rm -rf "$BUILD_DIR"

# 12. 完成
echo ""
echo "✅ 打包完成！"
echo ""
echo "📦 文件: $DMG_NAME"
ls -lh "$DMG_NAME"
echo ""
echo "🎉 可以分发了！"
