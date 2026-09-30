# 绘梦subtitle - 常见问题解答（FAQ）

## 🌟 快速导航

- [安装与启动](#安装与启动)
- [权限问题](#权限问题)
- [API 配置](#api-配置)
- [功能使用](#功能使用)
- [性能优化](#性能优化)
- [错误排查](#错误排查)

---

## 安装与启动

### Q1: 双击应用后无法打开，提示"来自身份不明的开发者"？

**A:** 这是 macOS 的安全机制，解决方法：

**方法一（推荐）**：
1. 按住 `Control` 键点击应用图标
2. 选择「打开」
3. 在弹出的对话框中点击「打开」

**方法二**：
1. 打开「系统偏好设置」
2. 进入「隐私与安全性」
3. 在底部找到被阻止的应用
4. 点击「仍要打开」

### Q2: 启动后页面空白或无响应？

**A:** 可能是后端未正常启动：

1. **检查后端进程**：
   ```bash
   ps aux | grep python | grep app.py
   ```

2. **手动启动后端**：
   ```bash
   cd ~/Desktop/国际实时翻译/Int-RealTime-Translate
   source .venv/bin/activate
   python run.py
   ```

3. **查看错误日志**：
   - 终端会显示详细错误信息
   - 检查是否缺少依赖或 API Key

### Q3: 更新后应用无法启动？

**A:** 清理旧缓存：

```bash
# 删除旧的虚拟环境
cd ~/Desktop/国际实时翻译/Int-RealTime-Translate
rm -rf .venv

# 重新安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 重新启动
python run.py
```

---

## 权限问题

### Q4: 麦克风权限被拒绝，无法录音？

**A:** 完整的权限配置步骤：

**Step 1: 系统权限**
1. 打开「系统偏好设置」→「隐私与安全性」
2. 左侧选择「麦克风」
3. 勾选以下项目之一：
   - 「绘梦subtitle」（应用模式）
   - 「Safari」或「Chrome」（浏览器模式）

**Step 2: 浏览器权限**（仅浏览器模式）
1. 点击地址栏左侧的锁图标（🔒）
2. 找到「麦克风」选项
3. 选择「允许」
4. 刷新页面（`Cmd + R`）

**Step 3: 验证权限**
1. 打开应用「设置」页
2. 点击「测试麦克风」
3. 说话时应看到音量条波动

### Q5: 系统检测不到麦克风？

**A:** 排查步骤：

1. **检查硬件连接**：
   - 确认麦克风已插好（如果是外置）
   - 尝试换个 USB 口

2. **系统声音设置**：
   - 打开「系统偏好设置」→「声音」→「输入」
   - 确认麦克风设备可见
   - 说话时输入电平应有响应

3. **切换默认设备**：
   - 如果有多个麦克风
   - 在系统设置中切换到另一个
   - 重启应用重试

### Q6: 麦克风被占用怎么办？

**A:** 关闭以下可能占用麦克风的应用：

- 🎥 Zoom / 腾讯会议 / 钉钉
- 💬 微信语音通话
- 🎙️ 其他录音软件
- 🎮 游戏语音（Discord、QQ 语音等）

关闭后刷新页面重试。

---

## API 配置

### Q7: 在哪里获取 API Key？

**A:** 根据使用模式获取对应 Key：

**实时同传模式**（阿里云百炼）：
1. 访问 [https://dashscope.console.aliyun.com/](https://dashscope.console.aliyun.com/)
2. 注册/登录阿里云账号
3. 进入「API-KEY 管理」
4. 点击「创建新的 API-KEY」
5. 复制 Key（格式：`sk-xxx`）

**本地翻译模式**（DeepSeek）：
1. 访问 [https://platform.deepseek.com/](https://platform.deepseek.com/)
2. 注册/登录账号
3. 进入「API Keys」页面
4. 点击「Create API Key」
5. 复制 Key（格式：`sk-xxx`）

### Q8: API Key 配置后不生效？

**A:** 检查清单：

- ✅ Key 是否复制完整（没有多余空格）
- ✅ Key 格式是否正确（通常以 `sk-` 开头）
- ✅ 账户是否已实名认证（部分服务要求）
- ✅ 账户余额是否充足
- ✅ Key 是否已被禁用或过期

**验证方法**：
```bash
# 测试阿里云百炼 Key
curl -X POST 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions' \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-turbo","messages":[{"role":"user","content":"你好"}]}'

# 测试 DeepSeek Key
curl -X POST 'https://api.deepseek.com/v1/chat/completions' \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"你好"}]}'
```

### Q9: API 配额用完了怎么办？

**A:** 解决方案：

1. **查看用量**：
   - 阿里云：控制台 → 费用中心 → 用量明细
   - DeepSeek：Dashboard → Usage

2. **充值续费**：
   - 阿里云支持支付宝充值
   - DeepSeek 支持信用卡

3. **切换引擎**：
   - 如果实时同传配额用完，切换到本地模式
   - 本地模式只需翻译 API，成本极低

---

## 功能使用

### Q10: 实时字幕延迟太高？

**A:** 优化建议：

**硬件因素**：
- 💻 Apple Silicon Mac（M1/M2/M3）性能最佳
- 🌐 稳定的网络连接（实时同传模式）

**设置优化**：
1. 切换到「实时同传」模式（延迟 1-3 秒）
2. 检查网络速度：
   ```bash
   curl -o /dev/null -s -w '%{speed_download}\n' https://dashscope.aliyuncs.com
   ```
3. 关闭其他占用网络的应用

**模式对比**：
- 实时同传：1-3 秒（云端，推荐）
- 本地模式：3-5 秒（离线，隐私）

### Q11: 翻译质量不理想？

**A:** 提升翻译质量的方法：

1. **选择更好的引擎**：
   - 实时同传：自然流畅，口语化
   - OpenAI GPT：准确度高，书面化
   - DeepSeek：高性价比平衡选择

2. **优化音频输入**：
   - 说话清晰，语速适中
   - 减少环境噪音
   - 使用高质量麦克风

3. **调整设置**：
   - 进入「设置」→「翻译引擎」
   - 尝试不同的模型参数
   - 切换目标语言方言（如：中文简体 vs 繁体）

### Q12: 如何导出字幕文件？

**A:** 导出步骤：

**实时字幕导出**：
1. 录音完成后，点击「停止」
2. 在字幕区域点击「导出」按钮
3. 选择格式：
   - SRT（通用字幕格式）
   - TXT（纯文本）
   - JSON（结构化数据）

**录音仓库批量导出**：
1. 进入「录音仓库」页面
2. 勾选需要导出的录音
3. 点击「批量导出」
4. 选择导出格式和保存位置

### Q13: 会议整理功能如何使用？

**A:** 使用流程：

1. **完成录音**：
   - 在「实时字幕」页录制完整的会议

2. **生成纪要**：
   - 进入「会议整理」页
   - 选择录音文件
   - 点击「生成会议纪要」

3. **AI 处理**：
   - 自动识别发言人
   - 提取关键要点
   - 生成决策清单
   - 整理待办事项

4. **导出文档**：
   - 支持 Markdown、PDF、Word 格式
   - 可自定义模板样式

---

## 性能优化

### Q14: 应用占用内存过高？

**A:** 优化方法：

1. **清理缓存**：
   ```bash
   cd ~/Desktop/国际实时翻译/Int-RealTime-Translate
   rm -rf recordings/.cache
   rm -rf __pycache__
   ```

2. **限制并发任务**：
   - 避免同时开启多个录音
   - 及时删除不需要的旧录音

3. **重启应用**：
   - 定期重启释放内存
   - macOS 会自动管理内存压力

### Q15: 本地模式首次使用很慢？

**A:** 这是正常现象：

**首次运行**：
- 需要下载 Whisper 模型（约 1.5GB）
- 下载完成后会自动缓存
- 进度可在终端查看

**后续使用**：
- 模型已缓存，启动快速
- Apple Silicon Mac 性能最佳

**加速下载**：
```bash
# 手动预下载模型
cd ~/Desktop/国际实时翻译/Int-RealTime-Translate
source .venv/bin/activate
python -c "import mlx_whisper; mlx_whisper.load_model('mlx-community/whisper-large-v3-mlx')"
```

---

## 错误排查

### Q16: "连接断开"错误频繁出现？

**A:** 排查步骤：

**1. 检查后端状态**：
```bash
# 查看后端进程
ps aux | grep "python.*app.py"

# 重启后端
cd ~/Desktop/国际实时翻译/Int-RealTime-Translate
source .venv/bin/activate
python run.py
```

**2. 检查端口占用**：
```bash
# 默认端口 8765
lsof -i :8765
```

**3. 清理浏览器缓存**：
- Chrome: `Cmd + Shift + Delete`
- Safari: `Cmd + Option + E`

**4. 查看日志**：
- 终端中的错误信息
- 浏览器控制台（F12）

### Q17: WebSocket 连接失败？

**A:** 解决方案：

**网络检查**：
```bash
# 测试本地连接
curl http://localhost:8765/health

# 应返回：{"status":"ok"}
```

**防火墙设置**：
1. 系统偏好设置 → 安全性与隐私 → 防火墙
2. 确保应用有网络访问权限

**代理冲突**：
- 关闭 VPN 或代理
- 或将 `localhost` 加入代理例外

### Q18: 模型加载失败？

**A:** 常见原因和解决：

**磁盘空间不足**：
```bash
# 检查可用空间（至少需要 5GB）
df -h ~/Desktop

# 清理空间
rm -rf ~/Library/Caches/*
```

**网络问题**：
```bash
# 测试 HuggingFace 连接
curl -I https://huggingface.co

# 如果被墙，使用镜像：
export HF_ENDPOINT=https://hf-mirror.com
```

**依赖缺失**：
```bash
# 重新安装 MLX
pip install --upgrade mlx mlx-whisper
```

### Q19: 翻译结果出现乱码？

**A:** 检查编码设置：

1. **确认输入语言**：
   - 实时字幕页选择正确的源语言
   - 如韩语应选「ko」而非「en」

2. **检查终端编码**：
   ```bash
   echo $LANG
   # 应显示：zh_CN.UTF-8 或类似
   ```

3. **浏览器编码**：
   - Chrome: 设置 → 高级 → 语言
   - 确保启用「UTF-8」

### Q20: 其他问题怎么办？

**A:** 获取帮助的途径：

1. **查看日志**：
   ```bash
   cd ~/Desktop/国际实时翻译/Int-RealTime-Translate
   tail -f backend.log
   ```

2. **重置配置**：
   ```bash
   rm .env
   cp .env.example .env
   # 重新配置 API Key
   ```

3. **完全重装**：
   ```bash
   rm -rf .venv
   rm -rf __pycache__
   rm -rf recordings/.cache
   # 然后按照安装说明重新安装
   ```

4. **联系支持**：
   - GitHub Issues: 提交详细的错误信息
   - 邮件支持: support@example.com
   - 附带日志和截图更快解决

---

## 💡 使用技巧

### 技巧 1: 快捷键
- `Cmd + R` - 刷新页面
- `Cmd + ,` - 打开设置（应用模式）
- `Space` - 开始/停止录音（焦点在页面时）

### 技巧 2: 批量处理
- 录音仓库支持批量选择
- 可批量导出或删除
- 支持日期范围筛选

### 技巧 3: 自定义模板
- 会议纪要模板可自定义
- 在设置页编辑 Markdown 模板
- 支持变量插值（如 `{{date}}`, `{{title}}`）

---

**还有问题？欢迎在 GitHub Issues 提问！** 🙋‍♂️

---

📅 最后更新：2026-08-30  
📌 版本：v1.1.0
