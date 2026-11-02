# testdata

测试用音频不入库（体积与本机环境相关），需要时自行放两个文件进来：

| 文件 | 内容 | 时长 |
| --- | --- | --- |
| `zh.wav` | 中文单句：「开放时间早上9点至下午5点。」 | ~5.6s |
| `en.wav` | 英文两句：The tribal chieftain called for the boy. / And presented him with 50 pieces of gold. | ~7.2s |
| `demo.mp4` | 彩条测试画面 + 440Hz 正弦音，验证视频预览用 | 6s |

要求：音频为 16kHz 单声道 16bit PCM。

生成办法：用任意录音工具录一段，再转成目标格式——

```powershell
ffmpeg -i 输入.m4a -ar 16000 -ac 1 -c:a pcm_s16le testdata\zh.wav
```

测试视频可以这样造：

```powershell
ffmpeg -f lavfi -i "testsrc2=size=640x360:rate=25:duration=6" `
       -f lavfi -i "sine=frequency=440:duration=6" `
       -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest testdata\demo.mp4
```

没有测试文件也能跑全部单元测试（`python -m unittest discover -s tests`），
只有 `tools/test_pipeline.py`、`tools/test_queue.py`、`tools/shot_v2.py` 需要它们。
