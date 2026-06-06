# 小说转剧本工具

当前状态：开发前研究、系统设计、技术选型与 Schema 设计阶段。

目标是开发一款 AI 辅助剧本创作工具，支持将 3 个章节以上的小说文本转换为可编辑的结构化剧本 YAML 初稿，帮助小说作者降低改编门槛。

## 已完成文档

- [开发前研究与竞品分析](docs/pre-development-research.md)
- [系统设计收束](docs/system-design.md)
- [技术选型](docs/technology-selection.md)
- [剧本 YAML Schema v0.1 设计说明](docs/script-yaml-schema.md)

## 示例

- [三章小说输入样例](examples/novels/three_chapters.txt)
- [目标剧本 YAML 样例](examples/outputs/three_chapters_screenplay.yaml)

## 下一步建议

1. 基于 Schema 建立机器校验文件。
2. 实现章节解析、实体抽取、场景大纲生成、逐场剧本生成和 YAML 校验流程。
3. 按 PR 规范拆分为多个小功能逐步提交。
