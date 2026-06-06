# 小说转剧本工具

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
uv run novel2script validate runs/demo
uv run novel2script run examples/novels/three_chapters.txt --out runs/demo --provider mock
```

完整运行后，最终剧本初稿会写入 `runs/demo/output/screenplay.yaml`。

## DeepSeek Provider 配置

项目支持 DeepSeek OpenAI 兼容接口。复制 `.env.example` 后在本地 shell 中导出环境变量：

```bash
export DEEPSEEK_API_KEY=sk-your-deepseek-api-key
export DEEPSEEK_MODEL=deepseek-v4-pro
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export DEEPSEEK_THINKING=disabled
uv run novel2script check-provider --provider deepseek
```

`DEEPSEEK_THINKING` 默认为 `disabled`，用于让连通性检查和后续剧本扩写直接返回 `content`。如需开启 DeepSeek thinking mode，可设为 `enabled`，但需要为推理内容预留更高 `max_tokens`。

当前版本先完成 provider 抽象和连通性检查；规则型剧本生成仍可离线运行。下一步会把 DeepSeek 接入逐场剧本扩写。

## 下一步建议

1. 使用 DeepSeek Provider 实现逐场剧本扩写 Prompt。
2. 按 PR 规范拆分为多个小功能逐步提交。
