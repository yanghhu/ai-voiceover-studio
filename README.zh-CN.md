<div align="center">

[English](README.md) · **简体中文** · [日本語](README.ja.md) · [Español](README.es.md)

# AI Voiceover Studio — 面向 YouTube 与无人出镜视频的 AI 配音、文字转语音与声音克隆

**AI Voiceover Studio 是一个开源的 Python 命令行工具和库：一条命令把写好的脚本变成完整的 AI 配音——多角色旁白、声音克隆、SRT 字幕，以及简单的无人出镜（faceless）视频。**

[![Tests](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Dependencies: none](https://img.shields.io/badge/core%20deps-zero-brightgreen.svg)](pyproject.toml)

</div>

```bash
voiceover script video-script.md --voices voices.json -o out/
# -> out/voiceover.mp3  out/voiceover.srt  out/manifest.json
```

## 演示

<!-- 演示占位：替换为 docs/assets/demo.gif（终端操作 + 生成的视频，约 15 秒，小于 5 MB） -->

> 🎬 *演示 GIF 即将补上。* 在此之前可以先跑下面的离线试运行：它用静音音频走完整条流程（分段计时、字幕、视频），不需要 API Key。

## 为什么做这个

做 YouTube 讲解、教程或无人出镜频道，配音流程往往是：写脚本 → 一段段粘进 TTS 工具 → 下载一堆音频 → 在剪辑软件里对齐 → 再转写一遍做字幕。AI Voiceover Studio 直接从一个 Markdown 文件完成这一整套流程，并且可重复执行：改了脚本只需重跑一条命令，只有改动的那几行会重新生成。

## 功能：AI 配音、文字转语音与字幕

| | 能做什么 |
| --- | --- |
| 🗣️ **文字转语音** | `voiceover say "..."`，一句话输出 MP3/WAV，可调语速、风格/情绪标签 |
| 🎭 **多角色脚本** | Markdown/TXT 中写 `[旁白]:`、`[ALEX]:`，每个角色映射到不同音色 |
| 🧬 **声音克隆** | 用参考音频 URL（及其文本）代替现成音色 |
| 💬 **字幕** | 按分段时长精确生成 SRT，或对成品音轨做语音识别 |
| 🎞️ **无人出镜视频** | 图片 + 脚本 → 带配音和外挂/烧录字幕的 MP4 幻灯片视频 |
| ♻️ **可安全重跑** | 分段缓存 + 确定性幂等键，未改动的行不会重复生成 |
| 🔌 **可插拔引擎** | 精简的 `VoiceProvider` 接口；内置远程引擎为 [Miragea](https://miragea.ai)，另有离线 `dummy` 引擎 |
| 🤖 **适配 Agent** | 附带 Agent 技能文件和 `--json` 输出，适用于 Claude Code、Codex、Cursor |
| 🪶 **轻量** | 仅依赖 Python 3.9+ 标准库；`moviepy`、`PyYAML` 为可选，检测到 `ffmpeg` 时自动使用 |

## 快速开始：60 秒完成文字转语音

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio.git
cd ai-voiceover-studio
pip install -e .                # 视频功能加 [video]，YAML 配置加 [yaml]

# 1) 离线试运行：无需密钥、不联网，输出带真实时长的静音音频
voiceover script examples/script.md --dry-run -o out/

# 2) 真实配音
export MIRAGEA_API_KEY=...      # 在 https://miragea.ai/workspace/api 创建
voiceover voices                # 列出账号里的音色（actor id）
voiceover say "欢迎回到我的频道！" --voice <actor_id> -o hello.mp3
```

`MIRAGEA_BASE_URL`（默认 `https://miragea.ai/v1`）可指向私有部署。密钥只从环境变量读取，只在请求 API 时放进 `Authorization` 头，不会被打印、记录或写入 `manifest.json`。

> 输出 MP3/M4A 或转换非 WAV 格式时需要已安装 [ffmpeg](https://ffmpeg.org)；没有 ffmpeg 时请输出 `.wav`（`--name voiceover.wav`）。

## 多角色脚本（对话与配音）

```markdown
# 三十秒讲清楚：为什么天空是蓝色的

[旁白]: 晴天抬头，天空是蓝色的。可阳光明明是白色的，蓝色从哪里来？

[小林](tags=好奇): 阳光是白色的？我一直以为是黄色的。

[pause 0.8]

[旁白](speed=1.05): 波长短的蓝光更容易被散射，于是整片天空都泛着蓝。
```

规则：`[名字]:` 指定说话人；没有标签的行沿用当前说话人；空行开始新的一段；`[pause 1.5]` 插入停顿；`(tags=a|b, speed=1.1, model=..., lang=...)` 设置单行参数。标题、HTML 注释、代码块和表格会被跳过，Markdown 强调与链接按纯文本朗读。过长的段落会在句末自动拆分，以符合引擎单次字数上限。

在 `voices.json` 中为角色指定音色（参见 [examples/voices.example.json](examples/voices.example.json)）：

```json
{
  "default": { "actor_id": "YOUR_ACTOR_ID" },
  "旁白":    { "actor_id": "YOUR_ACTOR_ID", "model": "standard" },
  "小林":    { "reference_audio_url": "https://example.com/lin.wav",
               "reference_text": "lin.wav 里实际说出的内容。" }
}
```

```bash
voiceover script examples/script.zh.md --voices voices.json -o out/ --gap 0.4
```

输出：`out/voiceover.mp3`（完整音轨）、`out/voiceover.srt`（对齐字幕）、`out/segments/*.wav`（每段音频，也是下次运行的缓存）、`out/manifest.json`（每段的说话人、文本、起止时间、任务 ID 与幂等键）。改一行再跑，只会重新生成那一行；想全部重新录一版用 `--fresh`。

## 用参考音频克隆声音

```bash
voiceover say "这是用文字生成的我自己的声音。" \
  --voice https://example.com/my-voice.wav \
  --ref-text "my-voice.wav 里我实际说的话。" \
  --lang zh -o cloned.mp3
```

`--voice` 以 `http(s)://` 开头时视为参考音频，否则视为 actor id。URL 需要能被 API 服务器访问。提供准确的参考文本（`--ref-text`）效果最可靠；省略时由引擎自动识别参考音频。请只克隆你本人或已获授权的声音。

## 字幕（SRT）

| 模式 | 方式 | 适用场景 |
| --- | --- | --- |
| `--subtitles timing`（默认） | 按每段的实际时长生成，文字直接取自脚本 | 以脚本为准，无额外 API 调用，没有识别错误 |
| `--subtitles recognize` | 把成品音轨提交到引擎的字幕识别接口 | 需要严格跟随实际语音的时间轴 |
| `--subtitles none` | 不生成字幕 | 纯音频项目 |

字幕在句子和分句处切分，并按两行换行（支持中日韩文字）。可以在 YouTube 工作室 →「字幕」上传 `.srt`，或直接烧录进视频。

## 用图片和脚本生成无人出镜 YouTube 视频

```bash
pip install -e ".[video]"
voiceover video --images examples/slides/ --script examples/script.md \
  --voices voices.json -o video.mp4 --subtitles burn          # 或 sidecar | none
voiceover video ... --size 1080x1920 -o short.mp4              # 竖屏，适合 Shorts / 抖音
```

图片按文件名排序。图片数量与脚本段数相同时，每张图正好对应一段旁白；否则平均分配时长。`--fit cover` 裁切铺满画面，`--fit contain` 以模糊背景补边。烧录字幕需要带 libass 的 ffmpeg。

## 在 Python 中使用

```python
from voiceover_studio import Studio

studio = Studio()   # 默认引擎 miragea，读取 MIRAGEA_API_KEY
studio.say("你好！", voice="ACTOR_ID", output="hello.mp3")
result = studio.render_script("script.md", "out/", voices="voices.json")
print(result.audio_path, result.srt_path)
```

## 在 AI 编程 Agent 中使用

[`skills/ai-voiceover/SKILL.md`](skills/ai-voiceover/SKILL.md) 可直接用于 Claude Code、Codex、Cursor 等 Agent。把该目录复制到 Agent 的技能目录后，直接说：“用 voices.json 里的音色给 script.md 配音，并生成字幕。” 所有命令都支持 `--json`，退出码固定（0 成功、1 任务失败、2 参数/API 错误）。

## 架构

脚本解析（`script.py`）→ 角色音色映射（`config.py`）→ 分段缓存与调度（`studio.py`）→ 引擎（`providers/`：`miragea.py` 异步任务 + 轮询 + 下载，`dummy.py` 离线）→ 拼接与导出（`audio.py`）→ 字幕（`subtitles.py`）→ 可选视频（`video.py`）。详见英文版 [Architecture](README.md#architecture)。

可靠性：异步任务按服务端 `poll_after_seconds` 轮询，等待超时会返回任务 ID，可用 `voiceover task <id> --wait` 继续；每个创建请求都带有由请求内容计算出的 `Idempotency-Key`，网络中断后重试或重跑脚本都会返回原任务；只在 API 标记 `retryable` 时用同一个键重试；401/403/409/413/429 都有明确提示。

## 支持的语言

内置 Miragea 引擎支持：**中文、英语、日语、韩语、德语、法语、俄语、葡萄牙语、西班牙语、意大利语**。

## 对比

| | 自己录音 | 网页 TTS 编辑器 | 直接调用 TTS API | **AI Voiceover Studio** |
| --- | --- | --- | --- | --- |
| 一个文件写完多角色脚本 | 手动 | 通常逐段 | 需自己写代码 | ✅ 内置 |
| 只重新生成改动的行 | 重录 | 手动 | 需自己写代码 | ✅ 缓存 + 幂等 |
| 字幕 | 另做 | 不一定 | 另做 | ✅ 自带 SRT |
| 无人出镜视频 | 剪辑软件 | 不一定 | 无 | ✅ 可选 |
| 可脚本化 / CI / Agent | 否 | 否 | 是 | ✅ |
| 更换引擎 | — | 否 | 重写 | ✅ 引擎接口 |
| 真人表演感 | ✅ 最好 | 取决于引擎 | 取决于引擎 | 取决于引擎 |

## 常见问题

更多见 [docs/FAQ.md](docs/FAQ.md)。

**怎么给 YouTube 视频加 AI 配音？** 把旁白写进 Markdown，运行 `voiceover script script.md --voices voices.json -o out/`，把 `out/voiceover.mp3` 放进剪辑时间线，并把 `out/voiceover.srt` 上传为字幕。完全不想剪辑，可用 `voiceover video` 直接生成视频。

**能克隆我自己的声音吗？** 可以。把一段清晰的录音放在 API 能访问的 URL，用 `--voice https://.../me.wav --ref-text "录音原文"`；也可以在 Miragea 账号里保存为角色后用 actor id。

**支持哪些语言？** 中文、英语、日语、韩语、德语、法语、俄语、葡萄牙语、西班牙语、意大利语。

**没有 API Key 能试吗？** 能，`--dry-run` 完全离线。

## 路线图

演示 GIF；脚本内嵌图片控制切换；背景音乐自动闪避；幻灯片缩放平移与转场；字幕样式预设；翻译并配音；并发生成；更多社区引擎。

## 参与贡献

欢迎提交问题、文档、新引擎和功能，见 [CONTRIBUTING.md](CONTRIBUTING.md)。

```bash
pip install -e ".[dev,video,yaml]"
pytest            # 完全离线，无需 API Key
```

## 许可证

[MIT](LICENSE) © 2026 Miragea contributors
