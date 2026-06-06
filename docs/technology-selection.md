# 小说转剧本工具：技术选型

## 选型结论

第一版采用 Python 本地 CLI 管线，围绕结构化数据模型、YAML 输出、Schema 校验和可测试的 AI Provider 抽象构建。

一句话方案：

> Python + uv + Pydantic + ruamel.yaml + Typer + pytest/ruff，先做本地可运行的小说转剧本数据管线；LLM 通过 provider 接口接入，测试默认使用 mock provider。

## 选型原则

1. 主分支始终可运行：每个 PR 都能用本地命令验证。
2. 结构化优先：AI 输出必须落到数据模型，再序列化为 YAML。
3. 可替换模型：不把业务逻辑绑定到某一家模型服务。
4. 本地优先：原文、中间产物、质量报告默认保存在本地。
5. 先 CLI 后 Web：先验证核心转换质量，再做界面和在线协作。
6. 少引入重框架：第一版避免过早使用复杂 agent 框架，降低调试成本。

## 技术栈

| 层级 | 选择 | 用途 | 选择原因 |
| --- | --- | --- | --- |
| 运行时 | Python 3.11+ | 核心管线、文本处理、数据建模 | 生态成熟，适合 AI 编排、文本处理和 CLI 工具。 |
| 包管理 | uv | 依赖管理、虚拟环境、运行命令 | 本地已可用，速度快，适合后续 `uv run` 固化开发命令。 |
| 项目结构 | `src/` layout | 源码组织 | 避免测试时误导入当前目录文件，适合打包和维护。 |
| 数据模型 | Pydantic v2 | 中间产物和最终 YAML 的类型定义 | 可做类型校验、默认值、枚举约束，并导出 JSON Schema。 |
| YAML 读写 | ruamel.yaml | 生成和读写 YAML | 更适合保持字段顺序、注释和人工可编辑性。 |
| Schema 校验 | Pydantic + JSON Schema | 机器校验 `screenplay.yaml` | Pydantic 负责运行时模型，JSON Schema 便于外部工具校验。 |
| CLI | Typer | 命令行入口 | 类型提示友好，适合拆成 `parse`、`analyze`、`generate`、`validate` 子命令。 |
| 终端输出 | Rich | 命令进度和错误展示 | 让校验错误、质量报告更易读。 |
| 测试 | pytest | 单元测试、集成测试、golden fixture 测试 | 生态稳定，已符合现有可批准命令前缀。 |
| 代码质量 | Ruff | lint 和 format | 速度快，能统一风格，现有环境已批准 `uv run ruff`。 |
| 本地索引 | SQLite FTS5 | 原文段落检索 | 无需额外服务，适合第一版关键词/全文检索。 |
| 日志 | Python logging + JSONL run log | 运行记录和问题定位 | 先不用额外依赖，避免日志泄露原文。 |
| 配置 | `pyproject.toml` + 环境变量 | 项目配置和模型密钥 | 配置集中，敏感信息不进入仓库。 |

## AI Provider 选型

第一版定义统一的 `LLMProvider` 接口，不直接把系统绑定到某个模型 SDK。

建议接口能力：

```text
generate_structured(prompt, response_model) -> Pydantic model
generate_text(prompt) -> str
```

Provider 分层：

| Provider | 第一版状态 | 用途 |
| --- | --- | --- |
| `MockProvider` | 必须实现 | 测试和演示使用，保证无网络、无密钥时主分支可运行。 |
| `OpenAICompatibleProvider` | 可以后续实现 | 接入支持 OpenAI-compatible API 的模型服务。 |
| `LocalModelProvider` | 暂不实现 | 后续接入本地模型或私有化部署。 |

设计原因：

- 测试不能依赖真实模型输出。
- 网络、密钥、模型版本都会变化，核心管线必须可独立验证。
- 后续可以在不改业务流程的情况下替换模型供应商。

## 不采用的方案

| 方案 | 暂不采用原因 |
| --- | --- |
| 一开始做 Web 应用 | 会把前端、后端、部署、文件上传、安全问题提前引入，影响核心改编质量验证。 |
| 一开始引入 LangChain/LlamaIndex | 第一版流程明确，直接实现更可控；后续如果检索和工具编排复杂再评估。 |
| 一开始使用向量数据库 | 对 3 章以上的 MVP，SQLite FTS5 和结构化章节索引足够；向量检索可作为后续增强。 |
| 直接生成 FDX/PDF | 第一版目标是可编辑、可校验的 YAML 中间层，FDX/PDF 可作为导出能力后置。 |
| Node.js/TypeScript 作为核心管线 | 前端生态强，但本项目核心是文本处理、模型编排和数据校验，Python 更直接。 |
| 数据库服务依赖 | 第一版用文件和 SQLite 即可，避免要求用户启动额外服务。 |

## 模块技术映射

| 系统模块 | 技术实现 |
| --- | --- |
| 章节解析 | Python 正则、文本切分、哈希计算 |
| 原文索引 | SQLite FTS5 + 段落 ID |
| 章节理解 | LLM Provider + Pydantic 输出模型 |
| 故事档案 | Pydantic models + YAML 文件 |
| 情节图 | Pydantic models，事件节点和 causes/effects 数组 |
| 伏笔表 | Pydantic models，setup/payoff 结构 |
| 场景大纲 | LLM Provider + 结构化模型 |
| 逐场剧本生成 | LLM Provider + 当前场景上下文包 |
| Schema 校验 | Pydantic validation + JSON Schema |
| 质量报告 | Python 规则检查 + 可选 LLM 审稿 |
| CLI | Typer 子命令 |

## 建议目录结构

```text
novel/
  README.md
  pyproject.toml
  src/
    novel_to_screenplay/
      __init__.py
      cli.py
      models/
        screenplay.py
        intermediates.py
      pipeline/
        parse_chapters.py
        analyze_chapters.py
        build_story_bible.py
        build_scene_outline.py
        generate_screenplay.py
        validate_screenplay.py
      providers/
        base.py
        mock.py
        openai_compatible.py
      storage/
        workspace.py
        text_index.py
      prompts/
        chapter_analysis.md
        scene_outline.md
        scene_generation.md
        consistency_review.md
  schemas/
    screenplay.schema.json
  examples/
    novels/
      three_chapters.txt
    outputs/
      screenplay.yaml
  tests/
    fixtures/
    test_parse_chapters.py
    test_validate_screenplay.py
```

## CLI 命令规划

第一版 CLI 只覆盖核心工作流：

```bash
novel2script parse examples/novels/three_chapters.txt --out runs/demo
novel2script analyze runs/demo
novel2script outline runs/demo
novel2script generate runs/demo --provider mock
novel2script validate runs/demo/screenplay.yaml
novel2script run examples/novels/three_chapters.txt --out runs/demo --provider mock
```

命令设计原因：

- 分阶段命令便于调试和局部重跑。
- `run` 提供端到端入口，方便评审复现。
- `--provider mock` 保证无密钥也能演示主流程。

## 数据存储策略

每次运行生成一个 run workspace：

```text
runs/demo/
  input/
    source.txt
  intermediates/
    parsed_chapters.yaml
    chapter_analysis.yaml
    story_bible.yaml
    characters.yaml
    locations.yaml
    timeline.yaml
    plot_graph.yaml
    foreshadowing.yaml
    scene_outline.yaml
  index/
    source.sqlite
  screenplay.yaml
  quality_report.yaml
  run.log.jsonl
```

原则：

- 中间产物全部落盘。
- 可以从任意阶段继续执行。
- 日志默认不记录大段原文。
- 输出文件可人工审阅和修改。

## 测试策略

第一版测试必须覆盖：

1. 少于 3 章时返回明确错误。
2. 章节标题识别。
3. YAML Schema 基础校验。
4. ID 引用校验。
5. 章节覆盖报告。
6. mock provider 端到端生成固定输出。
7. CLI `run` 能在本地无网络环境完成。

测试命令：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 隐私与安全约束

1. 小说原文默认只保存在本地 workspace。
2. 不把原文写入普通日志。
3. 真实 LLM provider 必须显式配置，不默认启用。
4. 输出中保留 `source_refs`，但默认不复制大段原文。
5. `.env`、`runs/`、临时索引和模型密钥不得提交到仓库。

## 版本规划

### v0.1：本地 CLI MVP

- Python 项目骨架。
- Pydantic 数据模型。
- YAML Schema 与示例。
- 章节解析。
- mock provider。
- 端到端生成样例 YAML。
- 校验和质量报告。

### v0.2：真实模型接入

- OpenAI-compatible provider。
- Prompt 模板版本化。
- 分阶段重跑和错误恢复。
- 更完整的一致性审稿。

### v0.3：检索增强

- SQLite FTS5 检索优化。
- 可选 embeddings。
- 更精细的段落级 `source_refs`。

### v0.4：导出与界面

- Fountain 导出。
- Markdown 预览。
- 轻量 Web UI 或桌面 UI。

## 当前技术决策

1. 第一版做 Python CLI，不做 Web。
2. 使用 uv 管理依赖和运行命令。
3. 使用 Pydantic 定义所有中间产物和最终剧本模型。
4. 使用 ruamel.yaml 输出人工可编辑 YAML。
5. 使用 JSON Schema 作为外部校验格式。
6. 使用 SQLite FTS5 做本地原文检索，不先引入向量数据库。
7. 使用 mock provider 保证无网络可测试。
8. 真实 LLM 接入通过 provider 接口后置实现。
