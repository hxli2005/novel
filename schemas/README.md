# 剧本 JSON Schema

本目录保存剧本 YAML 的机器校验文件。YAML 解析为 JSON 兼容对象后，可使用 `schemas/screenplay.schema.json` 校验基础结构。

## 文件

- `screenplay.schema.json`：对应 `screenplay_yaml/v0.1` 的 JSON Schema。

## 校验范围

当前 Schema 负责校验：

1. 顶层字段是否完整。
2. 章节、人物、地点、场景等核心对象是否具备必要字段。
3. 枚举值是否合法。
4. 场景是否至少包含一个 `chapter_refs` 和一个 `script` 元素。
5. 对白和旁白是否包含 `character_id`、`character_name` 和 `text`。

跨字段引用校验，例如 `dialogue.character_id` 是否真实存在于 `characters`、`scene_heading.location_id` 是否真实存在于 `locations`，后续由应用层验证器实现。
