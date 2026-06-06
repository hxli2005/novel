# 小说转剧本工具

[![CI](https://github.com/hxli2005/novel/actions/workflows/ci.yml/badge.svg)](https://github.com/hxli2005/novel/actions/workflows/ci.yml)

当前状态：开发前研究、Schema 设计、Python CLI、章节解析、实体分析、场景大纲和规则型剧本 YAML 生成阶段。

目标是开发一款 AI 辅助剧本创作工具，支持将 3 个章节以上的小说文本转换为可编辑的结构化剧本 YAML 初稿，帮助小说作者降低改编门槛。

## 已完成文档

- [开发前研究与竞品分析](docs/pre-development-research.md)
- [系统设计收束](docs/system-design.md)
- [技术选型](docs/technology-selection.md)
- [剧本 YAML Schema v0.1 设计说明](docs/script-yaml-schema.md)

## 机器校验

- [剧本 JSON Schema](schemas/screenplay.schema.json)

## 示例

- [三章小说输入样例](examples/novels/three_chapters.txt)
- [目标剧本 YAML 样例](examples/outputs/three_chapters_screenplay.yaml)

## 本地运行

```bash
uv run novel2script --help
uv run novel2script status
uv run novel2script providers
uv run novel2script check-provider --provider mock
uv run novel2script parse examples/novels/three_chapters.txt --out runs/demo
uv run novel2script analyze runs/demo
uv run novel2script outline runs/demo
uv run novel2script generate runs/demo --title 第七页 --author 示例作者
uv run novel2script draft-scenes runs/demo --provider mock
uv run novel2script validate runs/demo
```

或使用一条命令贯通全流程（解析 → 分析 → 大纲 → 生成 → AI 逐场扩写 → Schema 校验）：

```bash
uv run novel2script run examples/novels/three_chapters.txt --out runs/demo --provider mock
```

`run` 会直接产出**已扩写、已校验**的剧本初稿，写入 `runs/demo/output/screenplay.yaml`；上面分步命令用于需要逐阶段检查或人工介入的场景。

`run` 全程使用同一个 `--provider`：`mock` 时实体抽取与分场走离线规则（仅适用于内置示例），配置 DeepSeek 后使用 `--provider deepseek`，则**分析、分场、逐场扩写全部由模型驱动**，可泛化到任意题材小说：

```bash
uv run novel2script run path/to/novel.txt --out runs/demo --provider deepseek
```

`check` 对生成的剧本做故事级一致性检查（确定性、离线），并把发现写入 `quality_report.warnings`，供作者复核：

- `CHAPTER_NOT_ADAPTED`：某章节未被任何场景改编（可能遗漏剧情）。
- `CHARACTER_UNUSED`：人物已登记但从未出场。
- `CHARACTER_NO_DIALOGUE`：人物在场却全程没有台词。

配置 DeepSeek 后用 `check --provider deepseek`，会在确定性检查之外**追加 LLM 故事级复审**：伏笔是否回收（`FORESHADOW_UNRESOLVED`）、人物弧光是否连贯（`ARC_INCONSISTENCY`）、跨场因果是否成立（`CAUSALITY_GAP`）。模型返回异常时静默跳过，不影响确定性结果。

```bash
uv run novel2script check runs/demo --provider deepseek
```

写入的发现仍满足剧本 JSON Schema，`check` 后再 `validate` 依然通过。

## 改编参数

`run` 与 `generate` 支持改编旋钮，写入剧本的 `adaptation` 块：

- `--target-format`：`screenplay` | `tv_episode` | `web_series_episode` | `microdrama_episode` | `stage_play`
- `--fidelity`：`faithful` | `balanced` | `loose`（贴合原著的程度）
- `--pacing`：`slow_burn` | `balanced` | `compressed` | `fast`
- `--runtime`：目标时长（分钟）

```bash
uv run novel2script run examples/novels/three_chapters.txt --out runs/demo \
  --target-format microdrama_episode --fidelity faithful --pacing fast --runtime 2
```

这些参数除写入 `adaptation` 块外，配置 LLM provider 后还会**注入逐场扩写的 prompt**：体裁（target_format）、还原度（fidelity）、节奏与对白密度（pacing）、对白风格与旁白处理都会据此影响实际生成的剧本片段。`mock` 离线扩写不受影响。

## DeepSeek Provider 配置

项目支持 DeepSeek OpenAI 兼容接口。复制 `.env.example` 后在本地 shell 中导出环境变量：

```bash
export DEEPSEEK_API_KEY=sk-your-deepseek-api-key
export DEEPSEEK_MODEL=deepseek-v4-pro
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export DEEPSEEK_THINKING=disabled
uv run novel2script check-provider --provider deepseek
uv run novel2script analyze runs/demo --provider deepseek
uv run novel2script outline runs/demo --provider deepseek
uv run novel2script draft-scenes runs/demo --provider deepseek --max-tokens 2048
```

`DEEPSEEK_THINKING` 默认为 `disabled`，用于让连通性检查和后续剧本扩写直接返回 `content`。如需开启 DeepSeek thinking mode，可设为 `enabled`，但需要为推理内容预留更高 `max_tokens`。

`analyze` 默认使用 `mock`（离线规则）抽取人物、地点与伏笔；这套规则只对内置示例小说有效。配置 DeepSeek 后使用 `--provider deepseek`，则逐章调用模型抽取要素，可泛化到任意题材的小说。

`outline` 同样支持 `--provider deepseek`：模型基于章节分析规划场景顺序（一章可拆多场或多章合并），并对返回的章节、人物、地点、事件 id 做引用校验，保证下游 id 一致；`mock` 仍走规则型一章一场。

`draft-scenes` 会读取 `runs/demo/output/screenplay.yaml`，逐场替换 `script` 内容。使用 `--provider mock` 可离线演示，配置 DeepSeek 后可使用 `--provider deepseek` 调用真实模型。

## 下一步建议

1. 增加故事级一致性检查，复核伏笔、人物弧光和跨场因果链。
2. 按 PR 规范拆分为多个小功能逐步提交。
