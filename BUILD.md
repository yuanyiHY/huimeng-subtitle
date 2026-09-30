# 构建与发布说明（v1.2.1）

本文档说明「绘梦subtitle」应用的构建、打包与发布流程。

## 应用结构

```
绘梦subtitle.app            ← 启动器（双击入口）
  └── Contents/MacOS/IntRealTimeTranslate   ← launcher.c 编译的薄壳
        └─ 执行 app-launch.sh（项目目录下）
              ├─ 环境自检（venv 缺失 → 弹窗指引）
              ├─ 后端未运行 → `run.py --window`（后端 + 原生窗口）
              └─ 后端已运行 → 仅打开窗口连接既有后端
```

**依赖关系**：.app 是"薄壳"，实际运行依赖机器上的项目目录
（`~/Desktop/国际实时翻译/Int-RealTime-Translate`）+ 其中 `.venv` 环境。
适合"自己的机器 + 固定路径"的双击启动；分发到他人机器需先准备好项目目录与依赖。

## 构建步骤

```bash
cd ~/Desktop/国际实时翻译/Int-RealTime-Translate

# 1) 编译/更新 launcher（改了 launcher.c 或移动了项目路径后必须重做）
cc launcher.c -o "绘梦subtitle.app/Contents/MacOS/IntRealTimeTranslate"

# 2) 同步版本号（VERSION 文件与 Info.plist 保持一致）
plutil -replace CFBundleShortVersionString -string "1.2.0" "绘梦subtitle.app/Contents/Info.plist"
plutil -replace CFBundleVersion -string "1.2.0" "绘梦subtitle.app/Contents/Info.plist"

# 3) ad-hoc 签名（本机使用足够；分发需 Developer ID + 公证）
codesign --force --deep -s - "绘梦subtitle.app"

# 4) 打 DMG
./create-dmg-simple.sh     # 或 ./create-dmg.sh（带布局美化，需要 Finder 权限）
```

## 版本管理

| 位置 | 用途 |
|---|---|
| `VERSION` 文件 | 应用运行时读取的当前版本（更新检查用） |
| `Info.plist` CFBundleShortVersionString | Finder/系统显示的版本 |
| `create-dmg*.sh` 里的 VERSION | DMG 文件名 |

发新版本时三处同步修改。

## 更新检查机制

`config.yaml`：

```yaml
update:
  feed_url: "https://your-host/irt/latest.json"
```

更新源 JSON 格式（托管在任意静态服务器/CDN 上）：

```json
{
  "version": "1.2.1",
  "download_url": "https://your-host/irt/绘梦subtitle-1.2.1.dmg",
  "notes": "本次更新：修复 xxx，新增 yyy"
}
```

应用内：「设置 → 关于 → 检查更新」对比 `VERSION` 与 feed 中的 `version`，
有新版时显示下载链接。错误统一走错误码层（网络失败 → `NETWORK_ERROR` 等）。

## 关于"完全独立分发"（PyInstaller / py2app）的评估

当前不采用全量打包，原因：

1. **重依赖体积**：本应用依赖 mlx-whisper / torch / transformers，
   打包后约 2–4 GB，且 MLX 为 Apple 动态库，PyInstaller 对其支持不完整，
   容易出现"打包成功但运行崩溃"；
2. **模型分离**：模型（4.8 GB）本就按需下载（见 `backend/models/manifest.v1.json`），
   与 App 一起打包无意义；
3. **性价比**：面向"自己 + 固定机器"的分发，薄壳 + 环境自检已达到双击即用。

若未来面向陌生用户分发，建议路径（按优先级）：

- **A. 安装器方案（推荐）**：DMG 内放「安装.command」，首次运行自动创建 venv、
  安装依赖、拉取模型；对用户仍是"双击 → 等待 → 可用"；
- **B. PyInstaller onedir 试验**：先打"核心瘦身版"（fastapi/uvicorn/pywebview/
  soundfile，不含 mlx/torch），重依赖首启时按需安装；
- **C. 签名与公证**：上架级分发需 Developer ID 证书 + notarytool 公证，
  否则 Gatekeeper 会拦截（参考 Coursedude 的 `hdiutil` 产物：Developer ID 已签、未公证）。

## 模型与许可

`backend/models/manifest.v1.json` 是模型分发的发布权威（下载 / 校验 / 原子安装），
每个模型标注 SPDX 许可与是否允许商业分发：

| 模型 | 许可 | 商用 |
|---|---|---|
| whisper-large-v3-turbo | MIT | ✅ |
| nllb-200-distilled-600M | CC-BY-NC-4.0 | ❌ 仅限个人/研究 |
| Qwen2.5-7B-Instruct | Apache-2.0 | ✅ |

⚠️ 若产品化商业化，本地翻译建议替换为可商用引擎（如 OPUS-MT / m2m100，
均为宽松许可），或引导用户配置云端翻译 API。
