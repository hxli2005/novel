# 小说转剧本工具

当前状态：开发前研究、系统设计、技术选型与 Schema 设计阶段。

目标是开发一款 AI 辅助剧本创作工具，支持将 3 个章节以上的小说文本转换为可编辑的结构化剧本 YAML 初稿，帮助小说作者降低改编门槛。

## 已完成文档

- [开发前研究与竞品分析](docs/pre-development-research.md)
- [系统设计收束](docs/system-design.md)
- [技术选型](docs/technology-selection.md)
- [剧本 YAML Schema v0.1 设计说明](docs/script-yaml-schema.md)

## 下一步建议

1. 建立 Python 项目骨架和 CLI 基础命令。
2. 建立示例小说输入和目标 YAML 样例。
3. 基于 Schema 建立机器校验文件。
4. 按系统设计实现章节解析、故事档案、场景大纲、逐场生成和质量报告。
5. 按 PR 规范拆分为多个小功能逐步提交。
