免安装绿色版，解压后双击 `SubtitleForge.exe` 即可使用。全程离线运行，不联网、不写注册表、不装任何东西。

## 主要功能

- 导入音视频（mp3 / wav / m4a / flac / mp4 / mkv / mov / avi 等），自动识别语音
- 导出 **SRT**：带断句与时间轴，可直接拖进剪映、Premiere、达芬奇
- 导出 **TXT**：纯文本，支持「每句一行」「连续整段」「按段落合并」三种排版
- 字幕表格逐条可改，点某一行会跳到对应播放位置试听
- 支持批量文件排队转换
- 支持无界面命令行模式（`--run` / `--out` / `--format` / `--lang`）

## 断句怎么做的

三级优先级，尽量切在语义边界上：

1. 句末标点（。！？；）优先
2. 其次找较长的静音间隙（自研能量 VAD，10ms 精度）
3. 都没有才按长度 / 时长兜底

时间轴用 VAD 边界做线性校准，句首句尾不会飘。

## 使用方法

1. 解压到任意目录（建议非系统盘）
2. 双击 `SubtitleForge.exe`
3. 拖入音视频 → 点「开始转写」→ 点「导出…」

首次启动约 2~3 秒（要加载 229MB 模型）。转写速度大约 1 分钟音频用 3~5 秒（视 CPU 而定）。

## 系统要求

- Windows 10 / 11 64 位
- 不需要装 Python，也不需要装 FFmpeg，都已内置
- 内存 4GB 以上，磁盘预留 600MB

## 压缩包里有什么

| 路径 | 说明 |
| --- | --- |
| `SubtitleForge/SubtitleForge.exe` | 主程序 |
| `SubtitleForge/models/sensevoice/` | 识别模型，229MB，**别删** |
| `SubtitleForge/_internal/` | 运行时依赖（Qt、onnxruntime、ffmpeg），**别删** |
| `SubtitleForge/README.md` | 完整文档 |

## 已知限制

- 只做文件转写，不做实时麦克风字幕
- 不做说话人分离（区分「谁在说话」）
- 中文按字切分，可能切在词中间（有意取舍，避免引入分词器增加体积）
- 不做视频字幕压制，导出 SRT 后自行合成

## 校验

```
文件：SubtitleForge-v0.1.0-win64.zip
大小：264,858,311 字节（253 MiB）
SHA256：1b89c3e7906204aef7ba8fb4d0c75a1c3daf56323655c52adad932ebc26de2ae
```

PowerShell 校验：`Get-FileHash .\SubtitleForge-v0.1.0-win64.zip -Algorithm SHA256`

## 第三方组件

SenseVoice-Small（Apache-2.0）、sherpa-onnx（Apache-2.0）、PySide6（LGPL-3.0）、FFmpeg（LGPL-2.1）。详见仓库 `docs/THIRD-PARTY.md`。
