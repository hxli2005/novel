# 墨稿 Inkdraft · 小说转剧本工具

[![CI](https://github.com/hxli2005/novel/actions/workflows/ci.yml/badge.svg)](https://github.com/hxli2005/novel/actions/workflows/ci.yml)

把 3 章以上的小说，转换为**可编辑、可机器校验、可导出**的结构化剧本初稿，帮助小说作者降低改编门槛。提供**命令行**与**「墨稿」网页**两种用法，离线 `mock` 即可演示，配置 DeepSeek 后由大模型全程驱动、泛化到任意题材。

## 核心能力

- **结构化剧本 YAML 中间层**：不是最终排版，而是面向作者编辑、程序校验、回溯原文的结构化文档（人物 / 地点 / 场景 / 来源引用 / 质量报告）。详见 [Schema 设计说明](docs/script-yaml-schema.md)。
- **墨稿 Web UI**：上传小说 → 实时进度时间轴 → 纸墨风格阅读 → 一键导出，零构建（FastAPI + Jinja + 原生 SSE）。
- **真·LLM 驱动**：实体抽取、分场、逐场扩写全部可由模型完成；`mock` 走离线规则用于演示，`deepseek` 泛化到任意题材小说。
- **质量报告 + AI 深度复审**：确定性结构检查（章节覆盖 / 人物出场 / 台词）+ 可选的 LLM 故事级复审（伏笔回收 / 人物弧光 / 跨场因果）。
- **三种专业导出**：Fountain、Final Draft（`.fdx`）、Word（`.docx`）——可直接被主流剧本工具导入。
- **长篇友好**：可选择只转换某段章节范围；超长章节自动分块抽取再合并。

## 快速开始

### 方式一：网页（推荐）

```bash
uv run novel2script serve            # 默认 http://127.0.0.1:8000
```

打开浏览器，上传 `.txt` / `.md` 小说（或点「用三章示例试一下」），选择引擎与改编参数，即可看到实时进度并在线阅读、导出。

### 方式二：命令行一条龙

```bash
uv run novel2script run examples/novels/three_chapters.txt --out runs/demo --provider mock
```

`run` 贯通全流程（解析 → 分析 → 大纲 → 生成 → 逐场扩写 → 一致性检查 → Schema 校验），直接产出**已扩写、已校验**的剧本初稿到 `runs/demo/output/screenplay.yaml`。

> 真实改编请配置 DeepSeek 后改用 `--provider deepseek`（见下文），分析 / 分场 / 扩写全部由模型驱动。

## 墨稿 Web UI

`novel2script serve` 启动的网页应用提供端到端体验：

- **上传与示例**：拖拽或点选 `.txt` / `.md`；一键加载内置三章示例。
- **改编参数**：体裁、还原度、节奏、目标时长、章节范围、改编引擎（离线 `mock` / DeepSeek）。
- **实时进度**：六段「盖印」时间轴（解析 → 提取人物地点 → 规划分场 → 组装剧本 → 逐场扩写 → 质量校验）经 SSE 实时推送，含已用时与逐场进度；可**随时取消**正在进行的转换。
- **纸墨阅读**：纸张质感的剧本阅读视图，场景标题（内 / 外 · 日 / 夜）、动作、对白（含括号提示与潜台词）、转场。
- **抽屉**：「人物 · 地点」（角色 / 别名 chips）与「质量报告」（结构检查 / 故事级复审 / 生成说明分组 + 跳转到场景）。
- **AI 深度复审**：结果页一键触发 LLM 故事级复审，发现写入质量报告（需 DeepSeek 引擎）。
- **导出**：YAML / Fountain / Final Draft / Word 一键下载。
- **重新生成**：换章节范围用已暂存的原文重跑，无需重新上传。
- **历史记录**：`/history` 列出生成过的剧本（标题 / 作者 / 引擎 / 章节范围 / 时间）并提供快捷导出，服务重启后仍在。

## 命令行

| 命令 | 作用 |
| --- | --- |
| `run` | 端到端跑全流程，产出已扩写、已校验的剧本 YAML |
| `serve` | 启动「墨稿」网页应用（`--host` / `--port` / `--reload`） |
| `parse` | 解析章节 → `parsed_chapters.yaml` |
| `analyze` | 抽取人物 / 地点等要素（`--provider`） |
| `outline` | 规划分场大纲（`--provider` / `--target-format` / `--pacing`） |
| `generate` | 由前序阶段组装 `output/screenplay.yaml` |
| `draft-scenes` | 逐场扩写 `script`（`--provider` / `--scene-limit`） |
| `validate` | 按 JSON Schema 与 ID 引用校验 |
| `check` | 故事级一致性检查，写入 `quality_report`（`--provider`） |
| `export` | 导出可读 / 可导入格式（`--format fountain\|docx\|fdx`） |
| `providers` / `check-provider` | 查看 / 连通性检查 LLM provider |
| `status` | 打印 CLI 就绪状态 |

分步命令用于需要逐阶段检查或人工介入的场景：

```bash
uv run novel2script parse examples/novels/three_chapters.txt --out runs/demo
uv run novel2script analyze runs/demo
uv run novel2script outline runs/demo
uv run novel2script generate runs/demo --title 第七页 --author 示例作者
uv run novel2script draft-scenes runs/demo --provider mock
uv run novel2script check runs/demo
uv run novel2script validate runs/demo
```

## 导出格式

`export`（及网页下载）把剧本 YAML 转成**可读、可被剧本软件导入**的格式：

- `--format fountain`：[Fountain](https://fountain.io) 开放纯文本标准（Final Draft / WriterDuet / Highland / Scrivener 等均可导入），写入 `output/screenplay.fountain`。中文人物名用强制标记（`@角色名`、`> 转场`）保证被正确识别。
- `--format fdx`：[Final Draft](https://www.finaldraft.com/) 的 `.fdx`（XML）交换格式，影视行业事实标准，可直接在 Final Draft / WriterDuet / Fade In / Highland 等打开，写入 `output/screenplay.fdx`。基于标准库 ElementTree 生成，文本自动转义、始终良构。
- `--format docx`：Word 文档（`output/screenplay.docx`），标准中文剧本排版（场景标题、`人物：对白`、转场右对齐），契合国内以 Word 为主的流转习惯。

```bash
uv run novel2script export runs/demo --format fdx
```

## 改编参数

`run` / `generate` 支持全部四个改编旋钮，写入剧本的 `adaptation` 块（`outline` 只取 `--target-format` / `--pacing` 来影响分场密度）：

- `--target-format`：`screenplay` | `tv_episode` | `web_series_episode` | `microdrama_episode` | `stage_play`
- `--fidelity`：`faithful` | `balanced` | `loose`（贴合原著的程度）
- `--pacing`：`slow_burn` | `balanced` | `compressed` | `fast`
- `--runtime`：目标时长（分钟）

```bash
uv run novel2script run examples/novels/three_chapters.txt --out runs/demo \
  --target-format microdrama_episode --fidelity faithful --pacing fast --runtime 2
```

配置 LLM provider 后，这些参数除写入 `adaptation` 块外还会**注入生成 prompt**：`pacing` 决定每章拆几场（fast/compressed 倾向合并、slow_burn 倾向拆分），体裁 / 还原度 / 节奏 / 对白风格 / 旁白处理影响实际生成的剧本片段。`mock` 离线路径走规则，不受这些参数影响。

## 质量报告与 AI 深度复审

`check`（以及 `run` 内置的检查阶段）做**确定性、离线**的结构检查，把发现写入 `quality_report.warnings`：

- `CHAPTER_NOT_ADAPTED`：某章节未被任何场景改编。
- `CHARACTER_UNUSED`：人物已登记但从未出场。
- `CHARACTER_NO_DIALOGUE`：人物在场却全程没有台词。

配置 DeepSeek 后用 `check --provider deepseek`（或网页结果页的「AI 深度复审」按钮），在确定性检查之外**追加 LLM 故事级复审**：伏笔是否回收（`FORESHADOW_UNRESOLVED`）、人物弧光是否连贯（`ARC_INCONSISTENCY`）、跨场因果是否成立（`CAUSALITY_GAP`）。模型返回异常时静默跳过，不影响确定性结果；写入的发现仍满足剧本 JSON Schema。

```bash
uv run novel2script check runs/demo --provider deepseek
```

## DeepSeek Provider 配置

项目支持 DeepSeek OpenAI 兼容接口。复制 `.env.example` 后在本地 shell 中导出环境变量：

```bash
export DEEPSEEK_API_KEY=sk-your-deepseek-api-key
export DEEPSEEK_MODEL=deepseek-v4-pro            # 默认
export DEEPSEEK_BASE_URL=https://api.deepseek.com # 默认
export DEEPSEEK_THINKING=disabled                 # 默认；设为 enabled 需预留更高 max_tokens
uv run novel2script check-provider --provider deepseek
uv run novel2script run path/to/novel.txt --out runs/demo --provider deepseek
```

`run` 全程使用同一个 `--provider`。配置 DeepSeek 后，实体抽取、分场、逐场扩写全部由模型驱动，可泛化到任意题材；超长章节会自动按段分块、逐段抽取再合并（人物 / 地点去重）以支撑长篇。瞬时网络抖动（连接断开 / 超时 / 5xx）会自动重试，单次抖动不会中断整段运行。

> 网页端使用 DeepSeek 时，需让 `serve` 进程能读到 `DEEPSEEK_API_KEY`，例如：`set -a; source .env; set +a; uv run novel2script serve`。

## 文档

- [剧本 YAML Schema 设计说明](docs/script-yaml-schema.md) ｜ [机器可校验 JSON Schema](schemas/screenplay.schema.json)
- [开发前研究与竞品分析](docs/pre-development-research.md) ｜ [系统设计](docs/system-design.md) ｜ [技术选型](docs/technology-selection.md)
- 示例：[三章小说输入](examples/novels/three_chapters.txt) ｜ [目标剧本 YAML](examples/outputs/three_chapters_screenplay.yaml)

## 开发

```bash
uv run pytest          # 测试
uv run ruff check .    # 代码风格
```
