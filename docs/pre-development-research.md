# 小说转剧本工具：开发前研究与竞品分析

研究日期：2026-06-06（Asia/Shanghai）

## 研究范围

本阶段只做开发前资料整理，不实现功能代码。目标产品是一款面向小说作者的 AI 辅助改编工具：输入 3 个章节以上的小说文本，输出可编辑、可校验、可继续打磨的结构化剧本 YAML 初稿。

资料主要来自公开网页、官方帮助文档、开源项目说明和论文摘要。尚未进行付费试用、封闭功能测试或用户访谈，因此涉及竞品能力时以“公开资料显示”表述。

## 核心判断

小说转剧本不是简单的格式转换，而是一次“压缩、重组、可视化、对白化”的改编过程。工具真正要解决的问题有五类：

1. 长文本一致性：多章节小说包含人物、场景、伏笔和时间线，不能只按单章生成。
2. 叙述形态转换：小说中的心理活动、旁白、背景说明，需要改写成可拍摄动作、对白、场景信息或删减备注。
3. 幻觉和遗漏控制：AI 容易编造事件、错配人物、跳过关键章节。
4. 可编辑交付：作者需要的是能修改的结构化初稿，而不是一次性 PDF 或纯文本回答。
5. 版权与隐私：作者上传的是完整稿件或重要 IP，需要明确本地存储、模型调用和数据保留策略。

## 现有工具格局

| 类型 | 代表工具 | 公开资料显示的能力 | 对本项目的启发与缺口 |
| --- | --- | --- | --- |
| 传统剧本编辑器 | Final Draft、Celtx、WriterDuet、Arc Studio | 行业格式化、导入导出、协作、修订、分场景管理、制片拆解。WriterDuet 和 Arc Studio 支持 PDF、Final Draft、Word、Fountain 等多格式导入；Celtx 有剧本元素分类、导入、导出 Fountain、Breakdown、Shot List、Read Through。 | 它们擅长“写剧本”和“管剧本”，但通常假设用户已经在写剧本。Final Draft 帮助文档明确表示不能自动把小说重排成剧本。结构化 YAML 和章节回溯不是主能力。 |
| AI 剧本/共创工具 | Dramatron、Screenburn、NolanAI/FinalBit、ThinkBookAI | Dramatron 采用层级生成，从 logline 生成人物、情节点、场景地点和对白；Screenburn 公开页面声称支持小说导入、自动场景拆解和人物抽取；NolanAI/FinalBit、ThinkBookAI 更偏 AI 编剧和影视前期套件。 | 证明 AI 编剧已是明确方向。缺口在于：多数工具偏封闭编辑器、通用共创或生产前期，较少把“多章节小说 -> 可校验 YAML -> 可追踪章节来源”作为中心交付物。 |
| AI 小说写作工具 | Sudowrite、Novelcrafter | Sudowrite 有 Story Bible、Outline、章节生成；Novelcrafter 的 Codex 用于维护人物、地点、物件、lore、子情节等故事资料。 | 对长篇上下文管理很有参考价值。缺口是它们主要服务小说创作和扩写，不是把已有小说压缩改编成剧本结构。 |
| 视觉化/下游生产工具 | NovelVids、WebtoonForge、AI storyboard/video 工具 | NovelVids 公开描述了从小说文本到短剧视频的流程，包括实体抽取、资产管理、分镜脚本、视频生成。WebtoonForge 将 Fountain/FDX/PDF 剧本转换为 webtoon 分镜脚本，并输出面向画师的面板描述。 | 说明“结构化中间层”很重要。我们的 MVP 应先把小说稳定转换成剧本 YAML，后续可再导出 Fountain、FDX、分镜或短剧视频数据。 |
| 通用大模型聊天 | ChatGPT、Claude、Gemini 等 | 可以按提示改写片段，也可生成剧本格式文本。 | 低门槛但缺少工程约束：没有稳定 Schema、章节覆盖校验、人物表、场景 ID、来源引用和批量修复流程。 |

## 重点竞品观察

### Final Draft

Final Draft 帮助文档显示，它可以导入 PDF、TXT、RTF 等文件，并把导入内容重新格式化为 feature screenplay。但另一个官方问答明确说明，Final Draft 不能自动把小说重排成剧本，用户仍需按剧本惯例重写动作、人物、对白等元素。

启发：传统剧本软件的核心是格式化和专业交付，不是智能改编。因此本项目不应把最终 PDF/FDX 作为第一目标，而应先提供“改编中间层”。

### Celtx / WriterDuet / Arc Studio

Celtx 文档把剧本每行分为不同元素，并提供导入、导出 Fountain、分解道具服装、Shot List、朗读等能力。WriterDuet 强调实时协作、版本历史和多格式导入导出。Arc Studio 支持导入 Final Draft、Word、PDF、text/Fountain 文件。

启发：如果后续要接入专业编剧流程，Fountain/FDX 导出会很重要。但 MVP 的 YAML 需要比 Fountain 多保存来源章节、人物库、场景意图、删减说明和质量报告。

### Fountain

Fountain 是开放的纯文本剧本标记语法。其规则强调：场景标题通常以 INT/EXT 开头，人物名大写，对白紧跟人物名，括号表示 parenthetical，转场通常以 `TO:` 结尾。

启发：YAML 的 `script` 元素应覆盖这些基础剧本元素：scene heading、action、character/dialogue、parenthetical、transition。未来可从 YAML 稳定导出 Fountain。

### Dramatron

Google DeepMind 的 Dramatron 是一个开源共创系统，从一句 logline 逐步生成标题、人物、情节点、地点描述和对白。项目说明也强调它不是自动化独立编剧系统，而是给人类作者提供素材；同时指出可能出现抄袭片段、偏见、冒犯内容、公式化输出等风险。

启发：长篇生成应采用“先结构、后场景、再对白”的层级流程，并保留人工复核点。不要承诺生成可直接投拍的成稿。

### R²: Reader-Rewriter 论文

2025 年 arXiv 论文 `R²: A LLM Based Novel-to-Screenplay Generation Framework with Causal Plot Graphs` 直接讨论小说自动改编剧本。摘要指出两个关键挑战：LLM 幻觉导致情节抽取和剧本生成不一致，以及需要有效提取带因果关系的情节线。论文方案使用 Reader/Rewriter 模块、滑动窗口、因果情节图和幻觉感知修正。

启发：MVP 不应“整本塞给模型一次性输出”。更稳妥的流程是章节级抽取、全局情节图、场景大纲、逐场生成和一致性修复。

### Screenburn

Screenburn 公开页面声称提供 AI-powered tools、团队协作、导出 PDF/Final Draft/Fountain，并支持 “Import novels and transform them into screenplays”，含自动场景拆解和人物抽取。

启发：这是最贴近本需求的公开竞品之一。差异化方向应放在透明 Schema、可回溯源章节、面向作者二次编辑、可接入外部工作流，而不是只做一个封闭在线编辑器。

### Sudowrite / Novelcrafter

Sudowrite 的文档强调 Story Bible、Outline、Characters、Worldbuilding 等上下文对章节生成的影响。Novelcrafter 的 Codex 是故事资料库，用于存储人物、地点、物件、lore、子情节，并在 AI 调用时提供上下文。

启发：本项目需要内置类似 Story Bible/Codex 的抽取层。小说改编剧本时，角色表、地点表、物件表和时间线应先被规范化，再进入场景生成。

## 产品机会

本项目可以定位为“小说改编剧本的结构化中间层工具”，而不是传统剧本编辑器的替代品。

建议的差异化能力：

1. 章节感知：明确要求输入至少 3 个章节，并在输出中保留每场戏引用了哪些章节。
2. 结构化优先：输出 YAML，而不是只输出排版文本，便于作者、程序和后续 AI 共同编辑。
3. 来源可追踪：每个场景、关键对白、动作段落可挂 `source_refs`，减少作者核对成本。
4. 人物和地点统一表：先抽取 canonical character/location，再在场景中引用 ID，降低错名和设定漂移。
5. 改编说明透明：记录删减内容、合并场景、改写假设、需要人工确认的问题。
6. 可验证：输出后可用 Schema 校验 ID 引用、章节覆盖、枚举值、缺失字段和不一致对白人物。
7. 可导出：后续从 YAML 派生 Fountain、FDX、Markdown、分镜表或短剧分集表。

## MVP 建议范围

### 输入

- `.txt` 或 `.md` 小说文本。
- 自动识别章节标题，或允许用户手动指定章节分隔符。
- 最少 3 个章节；不足时返回明确错误。
- 支持中文优先，字段枚举保持英文，正文内容保持原语言。

### 输出

- 一个 `screenplay.yaml` 文件。
- 包含 metadata、source chapters、adaptation settings、characters、locations、structure、scenes、quality_report。
- 每个 scene 至少包含 scene heading、summary、characters_present、beats、script elements、source_refs。

### 流程

1. 章节解析：检测章节边界、标题、顺序、字数、文本哈希。
2. 章节理解：抽取人物、地点、事件、冲突、重要物件、时间线。
3. 故事资料库：合并同名人物、别名、地点和关键设定。
4. 情节图：建立事件顺序和因果关系，标记可删、可合并、必须保留的情节。
5. 场景大纲：把小说内容压缩为可拍摄场景，先不写完整对白。
6. 剧本生成：逐场生成 action/dialogue/transition 等结构化元素。
7. 校验修复：检查 Schema、ID 引用、章节覆盖、人物一致性、未解释删减。
8. 导出：MVP 输出 YAML；后续可导出 Fountain/FDX。

### 暂不做

- 不承诺自动生成最终可投拍剧本。
- 不做完整 PDF/FDX 排版编辑器。
- 不做视频、分镜图片或声音生成。
- 不做版权授权判断，只提供数据处理与改编辅助。

## 主要风险与缓解

| 风险 | 表现 | 缓解策略 |
| --- | --- | --- |
| 幻觉 | AI 编造原小说没有的人物或事件 | 所有关键内容要求 `source_refs`；生成后做“无引用内容”报警。 |
| 遗漏 | 某些章节没有被覆盖 | `quality_report.coverage` 列出每章覆盖率和未使用素材。 |
| 人物漂移 | 同一人物多种名字、性格变形 | 建立 `characters` canonical registry，场景和对白只引用 ID。 |
| 小说感太重 | 大量心理描写无法拍摄 | 生成时将内心活动转为动作、沉默、对白潜台词或备注。 |
| 输出不可编辑 | 纯文本难以局部修改和复用 | 用 YAML 保存场景、元素、人物、地点和来源引用。 |
| 隐私 | 上传未发表稿件到第三方模型 | 后续产品需支持本地存储说明、可配置模型、脱敏日志、默认不保存原文到远端。 |
| 成本和时延 | 多章节长文本调用模型贵且慢 | 分阶段缓存：章节抽取、人物表、情节图、逐场生成可独立重跑。 |

## 待确认产品决策

1. 第一版目标剧种：电影剧本、电视剧单集、短剧分集，还是通用 screenplay？
2. 是否需要中文行业格式习惯，例如“内/外、日/夜”，还是用 INT/EXT 枚举加中文显示字段？
3. 用户是否需要在生成前选择改编策略：忠实还原、强压缩、短剧爽点增强、人物线优先？
4. 是否保留小说原文短引用？建议默认只存 source range 和文本哈希，避免 YAML 文件过大和版权风险。
5. 是否允许用户在中间步骤编辑人物表和场景大纲后再生成剧本？建议允许，这是控制质量的关键。

## 资料来源

- Final Draft: What file formats can I import into Final Draft? https://kb.finaldraft.com/hc/en-us/articles/15575252515988-What-file-formats-can-I-import-into-Final-Draft
- Final Draft: Can Final Draft convert my novel into a screenplay? https://kb.finaldraft.com/hc/en-us/articles/28016325807124-Can-Final-Draft-convert-my-novel-into-a-screenplay
- Celtx: The Film & TV Script Editor https://support.celtx.com/hc/en-us/articles/360009310173-The-Film-TV-Script-Editor
- WriterDuet: Professional Screenwriting Software https://www.writerduet.com/home
- WriterDuet: Export a Document https://www.writerduet.com/article/261-export-a-document
- Arc Studio: How Do I Import Different File Formats? https://help.arcstudiopro.com/how-tos/document-script-management/how-do-i-import-different-file-formats
- Fountain Syntax https://fountain.io/syntax
- Google DeepMind Dramatron GitHub https://github.com/google-deepmind/dramatron
- Google DeepMind publication page: Co-Writing Screenplays and Theatre Scripts with Language Models https://deepmind.google/research/publications/13609/
- R² paper: A LLM Based Novel-to-Screenplay Generation Framework with Causal Plot Graphs https://arxiv.org/abs/2503.15655
- Screenburn https://screenburn.app/
- NolanAI/FinalBit: What is Project? https://help.finalbitai.com/en/articles/9960440-what-is-project
- Sudowrite Outline documentation https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/outline/3owKyHXUm1bCdp41b2Npjk
- Novelcrafter Codex documentation https://docs.novelcrafter.com/en/articles/8675743-the-codex
- NovelVids https://novelvids.com/
- WebtoonForge https://www.webtoonforge.com/
- ThinkBookAI https://thinkbook.ai/
