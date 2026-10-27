# testdata

测试用音频不入库（体积与本机环境相关），需要时自行放两个文件进来：

| 文件 | 内容 | 时长 |
| --- | --- | --- |
| `zh.wav` | 中文单句：「开放时间早上9点至下午5点。」 | ~5.6s |
| `en.wav` | 英文两句：The tribal chieftain called for the boy. / And presented him with 50 pieces of gold. | ~7.2s |

要求：16kHz 单声道 16bit PCM。

生成办法：用任意录音工具录一段，再转成目标格式——

```powershell
ffmpeg -i 输入.m4a -ar 16000 -ac 1 -c:a pcm_s16le testdata\zh.wav
```

没有测试音频也能跑全部单元测试（`python -m unittest discover -s tests`），
只有 `tools/test_pipeline.py` 和 `tools/test_e2e_ui.py` 需要它们。
