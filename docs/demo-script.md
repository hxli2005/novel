# 墨稿 Inkdraft · 演示视频脚本

成片：[`demo/inkdraft-demo.mp4`](../demo/inkdraft-demo.mp4)（约 1 分 30 秒，1280×800，中文语音讲解）。

视频用**真实接入 DeepSeek** 的一次运行作为素材（真实剧本内容 + 真实 AI 故事级复审发现），覆盖产品核心模块。下表为分镜与逐字旁白；成片由 `demo/` 下的脚本自动生成（截图 + macOS `say` 中文配音 + ffmpeg 合成），可一键复现。

| # | 画面 | 覆盖模块 | 旁白（逐字） |
| --- | --- | --- | --- |
| 1 | 上传页 | 上传 · 改编参数 | 墨稿，是一款 AI 小说转剧本工具。上传三章以上的小说，选好体裁、节奏和改编引擎，就能把它变成可编辑、可校验、可导出的结构化剧本初稿。 |
| 2 | 运行进度时间轴 | 实时进度（SSE）· 取消 | 转换过程实时可见。解析章节、提取人物地点、规划分场、组装剧本、逐场扩写、质量校验，六个阶段逐一完成，并且随时可以取消。 |
| 3 | 结果阅读页 | LLM 扩写 · 纸墨阅读 · 题材泛化 | 这是接入 DeepSeek 真实模型生成的剧本，以纸墨风格呈现：场景标题、动作描写、人物对白与潜台词一应俱全，可以泛化到任意题材的小说。 |
| 4 | 质量报告抽屉 | 结构检查 · AI 深度复审 | 右侧是质量报告。除了确定性的结构检查，还能一键触发 AI 深度复审，自动发现伏笔是否回收、人物弧光是否连贯、跨场因果是否成立，并跳转到对应场景。 |
| 5 | Final Draft (.fdx) 输出 | 三种专业导出 · 工具接入 | 剧本可以一键导出为 Fountain、Final Draft 和 Word 三种专业格式。这是生成的 Final Draft 文件，可以直接在 Final Draft、WriterDuet 等行业工具中打开。 |
| 6 | 历史记录页 | 历史 · 重新生成 / 导出 | 所有生成过的剧本都保存在历史记录里，随时重看、换章节范围重新生成或重新导出。墨稿，让小说落定成剧本。 |

## 复现方法

```bash
# 1. 启动 Web 服务（截图源；如需真实 DeepSeek 内容先 source .env）
uv run novel2script serve --port 8123

# 2. 截图（headless Chrome，自动冻结入场动画、强制亮色纸墨皮肤）
uv run python demo/capture.py

# 3. 合成带配音的视频（macOS say 中文配音 + imageio-ffmpeg 合成）
uv run --with imageio-ffmpeg python demo/build_video.py
# 产出 demo/inkdraft-demo.mp4
```

> `demo/capture.py` 里的 `RID` 指向用于取材的一次运行（默认是一次真实 DeepSeek 运行）。若该运行不在本地 `runs/web/` 下，换成任意已完成的 run id 即可。
