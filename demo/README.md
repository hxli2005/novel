# demo/

- **`inkdraft-demo.mp4`** — 带中文语音讲解的演示视频（约 1:30），覆盖核心模块。
- **`shots/`** — 视频用到的截图（真实 DeepSeek 运行素材）。
- **`capture.py`** — 用 headless Chrome 截取 Web 各页面（自动冻结入场动画、强制亮色皮肤）。
- **`build_video.py`** — 用 macOS `say` 中文配音 + ffmpeg 合成视频。

分镜与逐字旁白、复现步骤见 [`../docs/demo-script.md`](../docs/demo-script.md)。
