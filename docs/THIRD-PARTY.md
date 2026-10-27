# 第三方组件与许可

| 组件 | 版本 | 许可 | 用途 |
| --- | --- | --- | --- |
| PySide6 (Qt 6) | 6.12 | LGPL-3.0 | 图形界面 |
| sherpa-onnx | 2.0.1 | Apache-2.0 | 语音识别推理 |
| SenseVoice-Small | 2024-07-17 | Apache-2.0 | 中文/多语识别模型 |
| NumPy | 2.4 | BSD-3-Clause | 数值计算 |
| FFmpeg | 7.1 | LGPL-2.1 | 音视频解码（作为独立程序调用，未链接） |
| imageio-ffmpeg | 0.6 | BSD-2-Clause | 提供 ffmpeg 可执行文件 |

## 分发注意事项

1. **PySide6 为 LGPL-3.0**：动态链接（PyInstaller 打包的 dll 是独立文件）满足 LGPL 要求，
   但需要随包提供 LGPL 文本，并允许用户替换 Qt 库。使用 onedir 形式打包天然满足这一点。
2. **FFmpeg 为 LGPL-2.1**：本程序以子进程方式调用 ffmpeg.exe，未链接其代码。
   需附 LGPL 文本，并在文档中说明可从此处获取源码：https://ffmpeg.org/download.html
3. **SenseVoice 为 Apache-2.0**：可商用，需随包附许可证文本并保留版权声明。
4. 若将来替换为 GPL 构建的 FFmpeg（如含 libx264），整个分发物可能受 GPL 传染。
   本项目只做解码，务必坚持使用 LGPL 构建。
