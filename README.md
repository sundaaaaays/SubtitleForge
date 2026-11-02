# 字幕工坊 SubtitleForge

Windows 本地离线字幕生成工具。把音频 / 视频转成 SRT 字幕和 TXT 文稿，全程不联网。

- **多文件各自成页**：一次导入多个视频，每个文件一个标签页，结果互不覆盖
- **视频预览窗**：左侧实时预览画面，点字幕行跳到对应时间，播放时表格自动跟读
- **夜间模式**：深浅两套配色，切换后记忆选择
- 断句可调（字数 / 时长 / 静音阈值），参数面板可折叠
- 时间轴自动对齐，导出前可在表格里逐条校对
- 导出 SRT / TXT / VTT，支持 UTF-8 BOM、GBK 等编码
- 完全离线：不发起任何网络请求，断网、内网隔离环境都能用

## 直接下载（普通用户看这里）

不想碰代码的话，去 [Releases](https://github.com/sundaaaaays/SubtitleForge/releases) 下载
最新版 `SubtitleForge-v0.2.0-win64.zip`，解压后双击 `SubtitleForge.exe` 就能用。

免安装、不写注册表、不需要装 Python 或 FFmpeg，模型已打包在内。

系统要求：Windows 10 / 11 64 位，内存 4GB 以上。

## 界面说明

```
┌──────────────────────────────────────────────────────────────┐
│ 标题栏                         模型状态 · 夜间模式 · 模型目录 │
├────────────────────┬─────────────────────────────────────────┤
│ 待转写文件         │ 进度条 + 阶段提示                        │
│  ● demo.mp4        │ ┌─ demo.mp4 ─┬─ 第二集 ─┬─ 第三集 ─┐   │
│  ○ 第二集          │ │ #  开始  结束  时长  文本        │   │
│                    │ │ 1  00:00 00:02  2.0s  ……          │   │
├────────────────────┤ │ 2  ……                             │   │
│ 视频预览（可播放） │ └───────────────────────────────────┘   │
│  ▓▓ 画面 ▓▓        │ ▶ 播放选中   位置              统计      │
├────────────────────┤ 导出  SRT TXT VTT  排版  编码  [导出…]   │
│ ▸ 识别参数（折叠） │                                         │
│ [开始转写] [取消]  │                                         │
└────────────────────┴─────────────────────────────────────────┘
```

要点：

- 左侧文件列表点谁，右边就切到谁的标签页，两个方向都联动
- 点表格的「开始 / 结束 / 时长」列会从那句开始播；点「文本」列是编辑，不播放
- 播放时表格会自动高亮当前这句，预览画面同步走
- 「识别参数」默认收起，展开时预览窗自动收矮，避免列表被挤没

---

## 一、快速开始（开发环境）

```powershell
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 准备模型（见下一节），然后启动
python run.py
```

启动后把音视频文件拖进窗口，点「开始转写」即可。

## 二、模型准备

程序启动时会检查 `models/sensevoice/` 下是否有模型，没有则进入「演示模式」
（界面可用、导出格式正确，但识别结果是占位文本）。

放好下面两个文件后重启即可启用真实识别：

```
models/
└── sensevoice/
    ├── model.int8.onnx     约 229 MB
    └── tokens.txt          约 309 KB
```

来源：sherpa-onnx 官方模型库中的 **SenseVoice-Small**
（`sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`），License 为 Apache-2.0，可商用。

国内网络可直接用镜像下载：

```powershell
$repo = "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
curl -L -o models/sensevoice/model.int8.onnx "https://hf-mirror.com/$repo/resolve/main/model.int8.onnx"
curl -L -o models/sensevoice/tokens.txt        "https://hf-mirror.com/$repo/resolve/main/tokens.txt"
```

## 三、项目结构

```
SubtitleForge/
├── run.py                     开发环境入口
├── requirements.txt
├── models/                    模型（不纳入版本管理）
├── assets/                    图标与界面资源
├── src/subtitle_forge/
│   ├── core/                  纯逻辑层，不依赖 Qt，可独立单测
│   │   ├── models.py          数据模型（Cue / SpeechSegment / 参数）
│   │   ├── textutil.py        时间码、视觉宽度、标点规范化、词边界
│   │   ├── splitter.py        断句 + 时间轴校准
│   │   ├── vad.py             能量 VAD（双门限 + 滞回）
│   │   ├── exporters.py       SRT / VTT / TXT 生成与落盘
│   │   └── pipeline.py        四阶段转写编排
│   ├── audio/decoder.py       FFmpeg 解码封装
│   ├── asr/                   ASR 引擎接口与 SenseVoice 实现
│   └── ui/                    PySide6 界面
│       ├── main_window.py     主窗口：标签页、队列、导出、主题切换
│       ├── document.py        每个文件一份 Document + 独立表格 DocView
│       ├── preview.py         视频预览：QVideoSink 取帧自绘到画布
│       ├── styles.py          令牌化 QSS，亮 / 暗两套调色板
│       └── worker.py          后台转写线程
├── tools/                     开发期脚本（测试、截图、发版、图标生成）
├── build/build.spec           PyInstaller 打包配置
├── build/pack.py              一键打包
└── docs/                      截图与发行说明
```

**分层原则**：`core/` 不导入 Qt，所有断句和导出逻辑都能脱离界面测试，
这也是 `tests/test_core.py` 能在毫秒级跑完的原因。

**为什么视频画面要自绘**：`QVideoWidget` 走独立原生表面，截图和录屏抓不到
（全黑），圆角与样式表也容易被它顶掉。现在改成从 `QVideoSink` 取帧、
用 `QPainter` 等比画到画布上，行为完全可预期，30fps 上限也不至于白烧 CPU。

## 四、打包成 exe

一键打包（推荐，会自动清旧产物、放模型、跑自检）：

```powershell
.venv\Scripts\python.exe build\pack.py
```

手动打包：

```powershell
.venv\Scripts\pyinstaller.exe --noconfirm --clean --distpath dist --workpath build/work build/build.spec
```

产物在 `dist/SubtitleForge/`，把模型复制进去即可分发：

```powershell
# 注意必须先建好 models 目录，否则 cp 会把 sensevoice 的内容直接摊平到 models/ 里
mkdir dist\SubtitleForge\models
xcopy models\sensevoice dist\SubtitleForge\models\sensevoice\ /E /I
```

最终目录结构：

```
dist/SubtitleForge/
├── SubtitleForge.exe
├── models/sensevoice/model.int8.onnx
├── models/sensevoice/tokens.txt
├── _internal/                依赖的 Qt、onnxruntime，以及 assets/ 图标
└── ...
```

合计约 511MB（程序 283MB + 模型 229MB）。少了模型程序也能启动，但只会走
演示引擎输出占位文本——界面右上角的模型徽标会变成灰色提示。

**为什么用 onedir 而不是单文件 exe**：PySide6 的 Qt 动态库有 150MB+，
单文件模式下每次启动都要解压到临时目录，冷启动会慢 5~10 秒。
如果确实需要单文件，把 `build.spec` 里的 `COLLECT` 去掉、改成一个
`EXE(..., a.binaries, a.datas, ...)` 即可，但要接受启动变慢。

**打包后自检**：

```powershell
dist\SubtitleForge\SubtitleForge.exe --selftest
type dist\SubtitleForge\selftest.log
```

日志里看到 `SELFTEST OK` 说明模块、模型、ffmpeg 都正常。

**批量转写（无界面）**：GUI 程序没有控制台，结果靠日志文件回传。

```powershell
# 单个文件
dist\SubtitleForge\SubtitleForge.exe --run D:\video\a.mp4 --out D:\video --format srt,txt

# 指定日志位置和语言（auto / zh / en / ja / ko / yue）
dist\SubtitleForge\SubtitleForge.exe --run D:\video\a.mp4 --out D:\out --lang zh --log D:\out\a.log
```

参数说明：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--run` | 必填 | 输入音视频文件 |
| `--out` | 输入文件所在目录 | 输出目录，不存在会自动创建 |
| `--format` | `srt,txt` | 逗号分隔，可选 `srt` / `txt` / `vtt` |
| `--lang` | `auto` | 识别语言，`auto` 让模型自己判断 |
| `--env` | `quiet` | 声学环境：`quiet` 安静 / `noisy` 嘈杂 |
| `--log` | `<out>\subtitleforge.log` | 过程日志路径 |

日志末尾出现 `CLI_OK` 表示成功，同时会列出每个产出文件的完整路径；
出现 `CLI_FAILED` 时日志里带完整异常栈。退出码 0 成功 / 1 失败 / 2 输入文件不存在。

## 五、开发期脚本

| 脚本 | 用途 |
| --- | --- |
| `tests/test_core.py` | 断句、时间码、标点、导出格式的单元测试，44 条，不需要模型 |
| `tools/test_pipeline.py` | 用 `testdata/` 里的音频跑完整链路 |
| `tools/test_e2e_ui.py` | 模拟点击「开始转写」，验证界面到导出的全流程 |
| `tools/test_queue.py` | 多文件连续转写，确认各自结果互不覆盖 |
| `tools/shot_v2.py` | 生成亮 / 暗两套界面截图到 `docs/` |
| `tools/shot.py` | 旧版单页截图 |
| `tools/diag_video.py` | 视频解码诊断，判断画面到底有没有出来 |
| `tools/release.py` | 压缩 + 建 Release + 上传 + 回填 SHA256 |
| `tools/make_icon.py` | 生成 `assets/app.ico` |
| `tools/probe*.py` | 模型 / VAD 行为探测，调参时用 |

## 六、已知限制

- **只做文件转写**，不做实时麦克风字幕。
- **不做说话人分离**（区分「谁在说话」）。
- **不做视频字幕压制**，导出 SRT 后用剪映 / Premiere 合成即可。
- **纯静音片段可能出幻觉文本**（如 `그.`）。SenseVoice 在长静音上会「编」字，
  所以管线在送进模型前加了 -50dBFS 的能量闸门；自检里直接调模型、绕过闸门，
  因此 `selftest.log` 里看到这行怪字符是预期现象，不代表故障。
- 中文断句按字切分，遇到「技术选型」这类词可能切在词中间。这是有意取舍：
  引入分词器会增加 10MB 体积和启动开销，而中文观众对断字容忍度较高。
- 商用分发前请随包附上 SenseVoice（Apache-2.0）与 FFmpeg（LGPL）的许可文本。

## 七、许可

代码 MIT。第三方组件许可见 `docs/THIRD-PARTY.md`。

## 八、版本历史

### v0.2.0

- **多文件标签页**：每个文件一份独立文档和表格，转写结果不再互相覆盖
- **视频预览窗**：左侧实时画面，点字幕跳转、播放时表格跟读
- **夜间模式**：深浅两套配色，Ctrl+D 切换，选择持久化
- **参数折叠**：识别参数默认收起，展开时预览自动收矮
- **批量队列**：一次点击排队转写所有未完成文件
- 修复：窄窗口下「取消」按钮被挤出可视区

### v0.1.0

首个版本：导入音视频、SenseVoice 离线识别、断句与时间轴校准、导出 SRT / TXT / VTT。
