# AI Voiceover Studio — 开源 AI 配音与无人出镜视频生成器
**AI Voiceover Studio** 是一个开源的 Python 命令行工具：把一份文字脚本自动变成 AI 配音（文字转语音）、SRT 字幕和带逐字字幕的无人出镜视频，一条命令完成短视频自动生成，自带免费音色，无需 API Key。

<div align="center">

[English](README.md) · **简体中文** · [日本語](README.ja.md) · [Español](README.es.md)

[![Tests](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Dependencies: none](https://img.shields.io/badge/core%20deps-zero-brightgreen.svg)](pyproject.toml)

<table>
<tr>
<td align="center"><img src="docs/assets/demo.gif" alt="由 examples/demo.en.md 生成的 16:9 无人出镜视频：电影感配图、Ken Burns 运镜、动态开场标题、逐词高亮字幕" width="560"></td>
<td align="center"><img src="docs/assets/demo-short-zh.gif" alt="由 examples/demo.zh.md 生成的 9:16 中文短视频：星空配图与逐词大字幕" width="200"></td>
</tr>
<tr>
<td align="center"><sub>16:9 YouTube · <a href="docs/assets/demo.mp4">带声音完整视频（MP4，34 秒）</a></sub></td>
<td align="center"><sub>9:16 竖屏 · <a href="docs/assets/demo-short-zh.mp4">MP4，23 秒</a></sub></td>
</tr>
</table>

<sub>各由一条命令生成、未经剪辑：免费 Edge 语音，自动生成的氛围音乐在说话时自动压低，配图来自 <a href="examples/broll">examples/broll</a> · <a href="docs/assets/sample-voiceover.mp3">纯配音（MP3）</a> · <a href="docs/assets/sample-voiceover.srt">字幕（SRT）</a></sub>

</div>

## 快速开始（三行命令）

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio && cd ai-voiceover-studio
pip install -e ".[edge]"
voiceover video --script examples/demo.zh.md --vertical --music ambient -o out/short.mp4
```

就这些。你会得到 `out/short.mp4`（竖屏 1080x1920：逐段配图 + Ken Burns 运镜与转场、动态开场标题、逐词高亮字幕、说话时自动压低的背景音乐）、`out/short.srt`，以及 `out/short_voiceover/` 里的配音音轨。想要和演示完全一样的字体，用 `--font` 指定粗体字体文件（演示用的是免费的 Noto Sans SC Bold 和 Montserrat ExtraBold）。需要 Python 3.9+ 和 [ffmpeg](https://ffmpeg.org)，`voiceover doctor` 会帮你检查。

```bash
voiceover script examples/script.zh.md -o out/      # 只要音频：out/voiceover.mp3 + .srt + manifest.json
voiceover say "欢迎回到我的频道！" -o hello.mp3
voiceover video --script examples/demo.en.md --style tiktok --music ambient -o video.mp4   # 16:9 YouTube
voiceover doctor                                    # 检查 ffmpeg、引擎、密钥、中文字体
```

不需要音色配置文件：脚本里的每个角色会按脚本语言自动分配不同的声音（中文默认云希 / 晓晓）。

## AI Voiceover Studio 是什么？

AI Voiceover Studio 是一个免费、MIT 开源的命令行工具和 Python 库，用来把文字脚本做成带配音的视频。你用 Markdown 写旁白——可以加角色标签、停顿，并给每段配一张图或一段视频——`voiceover` 命令就会生成配音音频（MP3/WAV）、SRT 字幕，以及一个 MP4：逐段配图、Ken Burns 运镜和转场、抖音风格的逐字（逐词）动态字幕、说话时自动压低的背景音乐。它在你自己的电脑上运行（Python 3.9+ 和 ffmpeg），默认使用免费的微软 Edge 神经网络语音（300+ 音色、70+ 种语言），加一个参数即可换成 OpenAI 或 Miragea（声音克隆）等其他文字转语音引擎。

## 适合谁用

- **无人出镜 YouTube / B 站频道**：定期发布讲解、盘点、历史、科普类配音视频。
- **短视频创作者**：做抖音、快手、视频号、YouTube Shorts、Reels 竖屏视频，需要醒目的逐字字幕。
- **老师和课程作者**：用一份可以反复修改的脚本给教程、课件配音。
- **本地化和配音团队**：根据翻译好的脚本，把同一个视频做成多种语言版本。
- **播客和有声书制作者**：需要脚本化的片头、预告、口播广告和试听章节。
- **开发者和 AI Agent**：在代码、CI 或 Claude Code、Codex、Cursor 中批量生成配音和视频。

## 使用场景

每篇指南都有一条可以直接复制运行的命令（使用仓库自带示例）。

| 场景 | 得到什么 | 指南（英文） |
| --- | --- | --- |
| 无人出镜 YouTube 视频 | 一份脚本生成 16:9 配音视频：配图、字幕、音乐 | [faceless-youtube.md](docs/use-cases/faceless-youtube.md) |
| 抖音 / Shorts / Reels / TikTok | 9:16 竖屏视频，安全区内的大号逐字字幕 | [shorts-reels-tiktok.md](docs/use-cases/shorts-reels-tiktok.md) |
| 知识讲解、电影解说配音 | 给你自己的素材或幻灯片配旁白，按段落对齐 | [explainer-and-recap-narration.md](docs/use-cases/explainer-and-recap-narration.md) |
| 多语言配音 | 用翻译后的脚本把同一个视频配成多种语言 | [multilingual-dubbing.md](docs/use-cases/multilingual-dubbing.md) |
| 播客、有声书片段 | 多角色音频片段（片头、预告、试听章节）+ SRT | [podcast-and-audiobook-snippets.md](docs/use-cases/podcast-and-audiobook-snippets.md) |

## 为什么做这个

做 YouTube 讲解、教程或无人出镜频道，配音流程往往是：写脚本 → 一段段粘进 TTS 工具 → 下载一堆音频 → 在剪辑软件里对齐 → 再转写一遍做字幕。AI Voiceover Studio 直接从一个 Markdown 文件完成这一整套流程，并且可重复执行：改了脚本只需重跑一条命令，只有改动的那几行会重新生成。

## 功能

| | 能做什么 |
| --- | --- |
| 🆓 **免注册即用** | 默认引擎为免费的微软 Edge 神经网络语音（`edge-tts`），322 个声音、75 种语言，无需账号和密钥 |
| 🎭 **多角色脚本** | Markdown/TXT 中写 `[旁白]:`、`[小林]:`，每个角色自动分配不同声音，也可在 `voices.json` 指定 |
| 🎞️ **无人出镜视频** | 每段一个画面（脚本里写 `![](clip.mp4)`）→ Ken Burns 运镜、滑动/缩放/淡化转场、电影感调色、动态开场标题的 MP4 |
| 🔤 **动态字幕** | 抖音 / 剪映风格逐词高亮（按真实词级时间）、弹出动画、关键词变色（脚本里 `**加粗**`），横竖屏安全区 |
| 🎵 **背景音乐自动闪避** | 内置自动生成的氛围音乐（无版权风险），或用你自己的音乐，说话时自动压低 |
| ✨ **没有图片也好看** | 没配图的段落用流动渐变 + 关键词大字动态排版，不再是空白背景 |
| 💬 **精准字幕** | 按引擎返回的句子边界计时生成 SRT，或对成品音轨做语音识别；中文断行友好 |
| 🎨 **字幕样式** | `tiktok`（竖屏默认）、`clean`（横屏默认）、`bold`、`minimal`、`box`；横竖屏自动适配字号 |
| 🧬 **声音克隆** | 使用 Miragea 引擎：用参考音频 URL（及其原文）代替现成音色 |
| ♻️ **可安全重跑** | 分段缓存 + 确定性幂等键，未改动的行不会重复生成 |
| 🔌 **可插拔引擎** | `edge`、`miragea`、`openai`、离线 `dummy`，或通过 `VoiceProvider` 接口接入自己的引擎 |
| 🩺 **`voiceover doctor`** | 检查 ffmpeg（libass）、引擎、API 密钥和中文字体，并给出具体修复方法 |
| 🤖 **适配 Agent** | 附带 Agent 技能文件和 `--json` 输出，适用于 Claude Code、Codex、Cursor |
| 🪶 **轻量核心** | 核心只用标准库；引擎为可选扩展；视频直接由 ffmpeg 渲染 |

## 配音引擎

| 引擎 | 配置 | 适合 |
| --- | --- | --- |
| `edge`（未设置密钥时的默认） | `pip install -e ".[edge]"`，无需账号和密钥 | 快速试用、出草稿、多语言 |
| `miragea`（设置 `MIRAGEA_API_KEY` 后的默认） | `export MIRAGEA_API_KEY=...`（[创建密钥](https://miragea.ai/workspace/api)） | 参考音频声音克隆、带情绪标签的表现力模型、字幕识别 |
| `openai` | `export OPENAI_API_KEY=...` | OpenAI 音色（`alloy`、`nova`、`onyx` 等） |
| `dummy` | 无（`--dry-run`） | 离线测试和 CI：带真实时长的静音音频 |

用 `--provider 名称` 或 `VOICEOVER_PROVIDER` 选择引擎。`voiceover voices --provider edge --filter zh-CN` 列出 Edge 声音（如 `zh-CN-XiaoxiaoNeural`）；`voiceover voices` 列出 Miragea 账号里保存的角色。`MIRAGEA_BASE_URL`（默认 `https://miragea.ai/v1`）可指向私有部署。密钥只从环境变量读取，不会被打印或写入 `manifest.json`。

Edge 声音来自微软在线朗读服务（通过社区包 `edge-tts`），需要联网，并受微软条款约束。若所在网络的 HTTPS 代理无法被 edge-tts 使用，可设置 `VOICEOVER_EDGE_PROXY`。

## 多角色脚本（对话与配音）

```markdown
# 三十秒讲清楚：为什么天空是蓝色的

[旁白]: 晴天抬头，天空是蓝色的。可阳光明明是白色的，蓝色从哪里来？

[小林](tags=好奇): 阳光是白色的？我一直以为是黄色的。

[pause 0.8]

[旁白](speed=1.05): 波长短的蓝光更容易被散射，于是整片天空都泛着蓝。
```

规则：`[名字]:` 指定说话人；没有标签的行沿用当前说话人；空行开始新的一段；`[pause 1.5]` 插入停顿；`(tags=a|b, speed=1.1, model=..., lang=...)` 设置单行参数。标题、HTML 注释、代码块和表格会被跳过，Markdown 强调与链接按纯文本朗读。过长的段落会在句末自动拆分，以符合引擎单次字数上限。

不写配置时每个角色会自动分配不同声音；想自己指定，在 `voices.json` 中为角色设置音色（Edge 声音名如 `zh-CN-YunjianNeural`，或 Miragea 的 actor id，参见 [examples/voices.example.json](examples/voices.example.json)）：

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

声音克隆使用 Miragea 引擎（需 `MIRAGEA_API_KEY`）：

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
| `--subtitles timing`（默认） | 按引擎返回的句子边界（edge）或每段实际时长生成，文字取自脚本 | 以脚本为准，无额外 API 调用，没有识别错误 |
| `--subtitles recognize` | 把成品音轨提交到 Miragea 字幕识别接口 | 需要严格跟随实际语音的时间轴 |
| `--subtitles none` | 不生成字幕 | 纯音频项目 |

字幕在句子和分句处切分，并按两行换行（支持中日韩文字）。可以在 YouTube 工作室 →「字幕」上传 `.srt`，或直接烧录进视频。

## 用脚本生成无人出镜 YouTube 视频和竖屏短视频

画面直接写在脚本里：Markdown 图片行指定下一段的图片或视频片段，`**加粗**` 的词会在字幕中高亮：

```markdown
# 你看到的星星，可能早就不在了

![](broll/zh/01-stars.jpg)
今晚抬头看到的星光，可能来自一颗**早已消失**的恒星。
```

```bash
voiceover video --script examples/demo.zh.md --vertical --music ambient -o short.mp4          # 9:16 抖音 / Shorts / Reels
voiceover video --script examples/demo.en.md --style tiktok --music ambient -o video.mp4      # 16:9 YouTube
voiceover video --script 笔记.md -o explainer.mp4                                              # 没有图片：关键词动态大字
voiceover video --images slides/ --script script.md --music song.mp3 --music-volume 0.4 -o video.mp4
```

| 选项 | 默认 | 作用 |
| --- | --- | --- |
| 脚本中的 `![](文件)` | — | 该段的画面（图片或视频片段），路径相对脚本 |
| `--images 目录` | — | 给没写 `![](...)` 的段落按文件名顺序配图 |
| `--style tiktok\|clean\|bold\|minimal\|box` | 竖屏 `tiktok`，横屏 `clean` | `tiktok`：1–4 个大字词，当前词弹出变黄、关键词绿色 · `bold`：超大字随读随现 · `clean`：两行安静字幕 · `minimal` / `box`：静态字幕 |
| `--music ambient\|pulse\|文件` | 无 | 背景音乐；`ambient`、`pulse` 由本项目渲染时现场合成（无版权问题），也可用任意音频文件（自动循环） |
| `--music-volume 0-1` | `0.5` | 响度归一后的音乐音量 |
| `--no-duck` | 默认闪避 | 说话时不压低音乐 |
| `--hook 文本` / `--no-hook` | 脚本第一个 `#` 标题 | 开头 `--hook-seconds`（2.2 秒）的动态标题卡 |
| `--vertical` / `--size 宽x高` | `1920x1080` | `--vertical` 即 `1080x1920`；字幕避开抖音 / Shorts 按钮区域 |
| `--transition-style mix\|fade\|slide\|zoom\|cut` | `mix` | 转场风格；`--transition 秒` 控制时长（0.5） |
| `--grade cinematic\|none` | `cinematic` | 对比度、暗角和胶片颗粒 |
| `--motion kenburns\|none` | `kenburns` | 静态图运镜 |
| `--font 字体名或文件` | Inter，缺字回退系统字体 | 中文字幕需中文字体，例如 `--font NotoSansSC-Bold.otf`（`voiceover doctor` 会检查） |
| `--subtitles burn\|sidecar\|none` | `burn` | 烧录字幕（同时输出 `.srt`）、仅外挂、或不要 |

整个视频由一条 ffmpeg 命令渲染（zoompan、xfade、libass、sidechaincompress），不依赖 Python 视频库；34 秒 1080p 演示在双核 CPU 上约 80 秒渲染完。[`examples/broll`](examples/broll) 里的演示配图为本项目生成，可按仓库许可证自由使用。

## 在 Python 中使用

```python
from voiceover_studio import Studio

studio = Studio()   # 默认 edge；设置了 MIRAGEA_API_KEY 时为 miragea
studio.say("你好！", None, "hello.mp3")                      # 按文字语言自动选声音
studio.say("你好！", "zh-CN-XiaoxiaoNeural", "xiaoxiao.mp3", speed=1.1)
result = studio.render_script("script.md", "out/")          # 每个角色自动分配声音
print(result.audio_path, result.srt_path)
```

## 在 AI 编程 Agent 中使用

[`skills/ai-voiceover/SKILL.md`](skills/ai-voiceover/SKILL.md) 可直接用于 Claude Code、Codex、Cursor 等 Agent。把该目录复制到 Agent 的技能目录后，直接说：“用 voices.json 里的音色给 script.md 配音，并生成字幕。” 所有命令都支持 `--json`，退出码固定（0 成功、1 任务失败、2 参数/API 错误）。

## 架构

脚本解析（`script.py`）→ 角色音色映射（`config.py`）→ 分段缓存与调度（`studio.py`）→ 引擎（`providers/`：`miragea.py` 异步任务 + 轮询 + 下载，`dummy.py` 离线）→ 拼接与导出（`audio.py`）→ 字幕（`subtitles.py`）→ 可选视频（`video.py`）。详见英文版 [Architecture](README.md#architecture)。

可靠性：异步任务按服务端 `poll_after_seconds` 轮询，等待超时会返回任务 ID，可用 `voiceover task <id> --wait` 继续；每个创建请求都带有由请求内容计算出的 `Idempotency-Key`，网络中断后重试或重跑脚本都会返回原任务；只在 API 标记 `retryable` 时用同一个键重试；401/403/409/413/429 都有明确提示。

## 支持的语言

- **edge**：75 种语言（`voiceover voices --provider edge`）；中、英、日、韩、西、法、德、意、葡、俄会按脚本文字或 `--lang` 自动选声音。
- **miragea**：中文、英语、日语、韩语、德语、法语、俄语、葡萄牙语、西班牙语、意大利语，支持声音克隆。

## 对比

与两种最常见的“配音 + 字幕视频”做法的中立对比。“通常”指这一类工具的一般情况，不针对任何具体产品。

| | 剪辑软件手动流程（如剪映 / CapCut） | 在线 AI 视频生成平台（SaaS，一般情况） | 自己写代码调用 TTS API | **AI Voiceover Studio** |
| --- | --- | --- | --- | --- |
| 输入方式 | 时间线：粘贴文字、手动拖素材 | 网页表单或提示词 | 你的代码 | 一个 Markdown 脚本（可用 git 管理） |
| 运行位置 | 桌面 / 手机 App | 平台的云端 | 你的代码运行处 | 你自己的电脑（Python + ffmpeg）；文字只发送给你选择的语音引擎 |
| 源代码 / 许可 | 闭源 | 通常闭源，需要注册账号 | 取决于 API | 开源，MIT |
| 改了脚本里的一句话 | 手动重新编辑、对齐 | 在网页里重新生成 | 自己实现缓存 | 重跑一条命令，只重新生成改动的行 |
| 逐字字幕 | 有自动字幕，样式逐个项目调整 | 因产品而异 | 另做 | 内置，按引擎返回的词级时间对齐 |
| 多角色脚本 | 一次处理一条配音轨 | 因产品而异 | 自己写代码 | `[角色]:` 标签，每个角色自动分配声音 |
| 批量、CI、AI Agent | 否 | 部分产品提供 API | 是 | 命令行 `--json`、Python API、Agent 技能 |
| 语音引擎 | App 自带音色 | 平台自带音色 | 单一 API | 免费 Edge 音色、OpenAI、Miragea（声音克隆）或自定义引擎 |
| 时间线剪辑、模板、素材库 | ✅ 完整剪辑器 | ✅ 通常提供 | — | ❌ 不提供：自带配图，或使用关键词大字动画 |

如果需要完整的时间线剪辑或口型同步，请搭配剪辑软件使用——本工具专注做好一件事：输入脚本，输出配音、字幕和干净的成片。

## 常见问题

更多见 [docs/FAQ.md](docs/FAQ.md)。

**怎么给 YouTube 视频加 AI 配音？** 把旁白写进 Markdown，运行 `voiceover script script.md --voices voices.json -o out/`，把 `out/voiceover.mp3` 放进剪辑时间线，并把 `out/voiceover.srt` 上传为字幕。完全不想剪辑，可用 `voiceover video` 直接生成视频。

**能克隆我自己的声音吗？** 可以。把一段清晰的录音放在 API 能访问的 URL，用 `--voice https://.../me.wav --ref-text "录音原文"`；也可以在 Miragea 账号里保存为角色后用 actor id。

**支持哪些语言？** 中文、英语、日语、韩语、德语、法语、俄语、葡萄牙语、西班牙语、意大利语。

**没有 API Key 能用吗？** 能。默认的 `edge` 引擎免费、无需账号；`--dry-run` 完全离线。Miragea 密钥额外提供声音克隆和表现力音色。

## 路线图

已完成：演示 GIF 与示例视频、免费默认引擎（edge）与 OpenAI 引擎、Ken Burns 动效与字幕样式、`voiceover doctor`、脚本内嵌配图、背景音乐自动闪避、逐词高亮动态字幕。计划中：按关键词搜索素材；翻译并配音；并发生成；发布到 PyPI。

## 参与贡献

欢迎提交问题、文档、新引擎和功能，见 [CONTRIBUTING.md](CONTRIBUTING.md)。

```bash
pip install -e ".[dev,edge,yaml]"
pytest            # 完全离线，无需 API Key
```

## 许可证

[MIT](LICENSE) © 2026 Miragea contributors
