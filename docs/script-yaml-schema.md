# 剧本 YAML Schema v0.1 设计说明

本文定义小说转剧本工具第一版的 YAML 输出结构。它不是最终排版格式，而是一个面向作者编辑、程序校验和后续导出的结构化中间层。

## 设计目标

1. 可编辑：作者能直接读懂和修改 YAML。
2. 可校验：程序能检查必填字段、ID 引用、章节覆盖和枚举值。
3. 可回溯：场景、动作、对白能关联原小说章节。
4. 可扩展：后续可导出 Fountain、FDX、Markdown、分镜表或短剧分集表。
5. 可控幻觉：把 AI 的假设、删减和无来源内容显式记录出来。

## 顶层结构

```yaml
schema_version: "screenplay_yaml/v0.1"
metadata: {}
source: {}
adaptation: {}
story_world: {}
characters: []
locations: []
structure: {}
scenes: []
quality_report: {}
```

必填顶层字段：`schema_version`、`metadata`、`source`、`adaptation`、`characters`、`locations`、`scenes`、`quality_report`。

## metadata

```yaml
metadata:
  title: "剧本标题"
  author: "原作者或改编者"
  language: "zh-CN"
  created_at: "2026-06-06T10:00:00+08:00"
  generator:
    name: "novel-to-screenplay"
    version: "0.1.0"
  rights:
    source_copyright_owner: "作者姓名或机构"
    adaptation_notes: "仅作为作者辅助创作初稿"
```

设计原因：剧本文档需要独立于输入文件存在。`metadata` 保存标题、语言、生成器版本和版权备注，便于归档、导出和排查模型版本差异。

## source

```yaml
source:
  source_type: "novel"
  original_title: "小说标题"
  chapter_count: 3
  chapters:
    - id: "ch_001"
      order: 1
      title: "第一章"
      word_count: 3200
      text_hash: "sha256:..."
      summary: "本章剧情摘要"
    - id: "ch_002"
      order: 2
      title: "第二章"
      word_count: 2800
      text_hash: "sha256:..."
      summary: "本章剧情摘要"
    - id: "ch_003"
      order: 3
      title: "第三章"
      word_count: 3500
      text_hash: "sha256:..."
      summary: "本章剧情摘要"
```

约束：

- `source_type` 第一版固定为 `novel`。
- `chapters` 至少 3 项。
- `id` 使用稳定 ID，建议格式为 `ch_001`。
- `text_hash` 可选，但建议保存，用于确认生成结果对应哪一版原文。

设计原因：需求明确要求处理 3 个章节以上。把章节作为一等结构，可以让后续校验“哪些章节被改编、哪些被删减、哪些场景引用了哪些章节”。

## adaptation

```yaml
adaptation:
  target_format: "screenplay"
  target_runtime_min: 45
  episode:
    mode: "single"
    number: null
  strategy:
    fidelity: "balanced"
    pacing: "compressed"
    dialogue_style: "natural"
    narration_policy: "convert_to_action_or_dialogue"
  assumptions:
    - "将大量心理描写转为动作和沉默。"
  human_review_required: true
```

建议枚举：

- `target_format`: `screenplay`、`tv_episode`、`web_series_episode`、`microdrama_episode`、`stage_play`
- `fidelity`: `faithful`、`balanced`、`loose`
- `pacing`: `slow_burn`、`balanced`、`compressed`、`fast`
- `narration_policy`: `preserve_as_voiceover`、`convert_to_action_or_dialogue`、`omit_unfilmable`

设计原因：同一部小说可以改成电影、电视剧、短剧或舞台剧。改编策略会显著影响删减比例、场景长度和对白密度，因此必须显式记录。

## story_world

```yaml
story_world:
  logline: "一句话故事梗概"
  synopsis: "完整剧情摘要"
  themes:
    - "成长"
    - "复仇"
  setting:
    time_period: "现代"
    primary_places:
      - "江城"
  timeline_notes:
    - "前三章发生在同一天夜里。"
```

设计原因：剧本生成需要全局语境。`story_world` 是精简版故事圣经，避免逐场生成时丢失主题、时代和时间线。

## characters

```yaml
characters:
  - id: "char_lin_qing"
    name: "林青"
    aliases:
      - "阿青"
    role: "protagonist"
    age: "28"
    description: "外科医生，冷静克制。"
    motivation: "查清父亲死亡真相。"
    arc: "从逃避真相到主动揭露阴谋。"
    voice: "短句多，避免情绪外露。"
    first_appearance:
      chapter_id: "ch_001"
    source_refs:
      - chapter_id: "ch_001"
        note: "首次出场"
```

建议枚举：

- `role`: `protagonist`、`antagonist`、`supporting`、`minor`、`ensemble`、`unknown`

设计原因：长篇小说人物多、别名多。统一人物表可以防止同一人物在不同场景中被重复创建，也能让对白生成保持人物声音一致。

## locations

```yaml
locations:
  - id: "loc_hospital_rooftop"
    name: "医院天台"
    type: "exterior"
    visual_description: "夜色下的医院天台，霓虹反光，风很大。"
    recurring: true
    source_refs:
      - chapter_id: "ch_002"
        note: "关键对峙地点"
```

建议枚举：

- `type`: `interior`、`exterior`、`interior_exterior`、`virtual`、`unknown`

设计原因：地点是场景标题和视觉调度的基础。单独管理地点，便于导出 INT/EXT 场景标题，也便于后续生成分镜或制片拆解。

## structure

```yaml
structure:
  acts:
    - id: "act_1"
      title: "建立人物与危机"
      scene_ids:
        - "sc_001"
        - "sc_002"
  key_events:
    - id: "evt_001"
      summary: "林青收到匿名病历。"
      chapter_refs:
        - "ch_001"
      scene_ids:
        - "sc_001"
      causal_links:
        - "evt_002"
  omitted_material:
    - chapter_id: "ch_003"
      reason: "内心独白重复，已合并进 sc_004 的动作和潜台词。"
```

设计原因：小说改编必然涉及合并和删减。`structure` 用来解释宏观结构、关键事件和删减原因，帮助作者判断改编是否忠实。

## scenes

```yaml
scenes:
  - id: "sc_001"
    order: 1
    chapter_refs:
      - "ch_001"
    scene_heading:
      location_mode: "INT"
      location_id: "loc_hospital_archive"
      display: "医院档案室"
      time_of_day: "NIGHT"
    summary: "林青在档案室发现父亲病历缺页。"
    dramatic_function: "inciting_incident"
    estimated_screen_time_sec: 120
    characters_present:
      - "char_lin_qing"
    props:
      - "缺页病历"
    beats:
      - id: "beat_001"
        summary: "林青撬开档案柜。"
        source_refs:
          - chapter_id: "ch_001"
            note: "档案室段落"
      - id: "beat_002"
        summary: "她发现父亲病历被人抽走关键页。"
        source_refs:
          - chapter_id: "ch_001"
            note: "发现病历缺页"
    script:
      - type: "action"
        text: "档案室只亮着一盏顶灯。林青蹲在柜前，手套上沾着灰。"
        source_refs:
          - chapter_id: "ch_001"
            note: "环境与动作改写"
      - type: "dialogue"
        character_id: "char_lin_qing"
        character_name: "林青"
        parenthetical: "压低声音"
        text: "第七页去哪了？"
        subtext: "她意识到父亲的死不是医疗事故。"
        source_refs:
          - chapter_id: "ch_001"
            note: "由内心独白改写"
      - type: "transition"
        text: "CUT TO:"
    continuity:
      previous_scene_id: null
      next_scene_id: "sc_002"
      open_questions:
        - "偷走病历的人是否已在前三章出现？"
    revision_status: "ai_draft"
```

### scene_heading

```yaml
scene_heading:
  location_mode: "INT"
  location_id: "loc_hospital_archive"
  display: "医院档案室"
  time_of_day: "NIGHT"
```

建议枚举：

- `location_mode`: `INT`、`EXT`、`INT_EXT`、`UNKNOWN`
- `time_of_day`: `DAY`、`NIGHT`、`MORNING`、`EVENING`、`CONTINUOUS`、`LATER`、`UNKNOWN`

设计原因：保留 INT/EXT 和 DAY/NIGHT 等行业常见字段，便于导出 Fountain/FDX；同时保留 `display`，支持中文场景名。

### script elements

`script` 是有序数组，按画面出现顺序排列。

```yaml
script:
  - type: "action"
    text: "可拍摄动作或画面描述。"
    source_refs: []

  - type: "dialogue"
    character_id: "char_lin_qing"
    character_name: "林青"
    parenthetical: "迟疑"
    text: "对白内容。"
    subtext: "潜台词，仅供作者编辑，不一定导出。"
    source_refs: []

  - type: "voiceover"
    character_id: "char_lin_qing"
    character_name: "林青"
    text: "旁白内容。"
    source_refs: []

  - type: "transition"
    text: "CUT TO:"
```

建议枚举：

- `type`: `action`、`dialogue`、`voiceover`、`parenthetical`、`transition`、`note`

约束：

- `dialogue` 和 `voiceover` 必须有 `character_id`，且该 ID 必须存在于 `characters`。
- `action.text`、`dialogue.text`、`voiceover.text`、`transition.text` 不能为空。
- `note` 只用于作者备注，默认不导出到正式剧本。

设计原因：剧本的核心是有序元素。用数组而不是大段文本，可以精确编辑、局部重生成、校验角色引用，并支持未来导出到其他格式。

## source_refs

```yaml
source_refs:
  - chapter_id: "ch_001"
    paragraph_start: 12
    paragraph_end: 16
    note: "由小说内心独白改写为对白"
```

约束：

- `chapter_id` 必须存在于 `source.chapters`。
- `paragraph_start` 和 `paragraph_end` 可选；如果实现阶段能稳定切段，应优先保存。
- 不建议默认保存大段原文引用，避免 YAML 过大和版权风险。

设计原因：来源引用是控制 AI 幻觉和提升作者信任的关键。作者可以快速回到小说原文核对改编依据。

## quality_report

```yaml
quality_report:
  validation_status: "warning"
  chapter_coverage:
    - chapter_id: "ch_001"
      used_in_scene_ids:
        - "sc_001"
        - "sc_002"
      coverage_note: "主要事件均已覆盖。"
    - chapter_id: "ch_002"
      used_in_scene_ids:
        - "sc_003"
      coverage_note: "删减了两段背景说明。"
    - chapter_id: "ch_003"
      used_in_scene_ids:
        - "sc_004"
      coverage_note: "内心独白合并处理。"
  warnings:
    - code: "LOW_SOURCE_TRACE"
      message: "sc_004 有 2 条对白缺少明确来源。"
      scene_id: "sc_004"
  unresolved_questions:
    - "反派真实身份在前三章是否应提前埋伏笔？"
```

建议枚举：

- `validation_status`: `pass`、`warning`、`fail`

设计原因：AI 生成物必须暴露不确定性。质量报告让作者先看风险点，而不是逐字通读后才发现章节遗漏或设定冲突。

## 全局校验规则

1. `source.chapters.length >= 3`。
2. 所有 `chapter_refs` 和 `source_refs.chapter_id` 必须存在。
3. 所有 `scene_ids` 必须存在于 `scenes`。
4. 所有 `characters_present`、`dialogue.character_id`、`voiceover.character_id` 必须存在于 `characters`。
5. 所有 `scene_heading.location_id` 必须存在于 `locations`，除非 `location_mode` 为 `UNKNOWN`。
6. 每个 scene 至少有一个 `chapter_refs`。
7. 每个 scene 至少有一个 `script` 元素。
8. `quality_report.chapter_coverage` 应覆盖每个输入章节。
9. AI 新增但无原文依据的内容必须进入 `warnings` 或 `assumptions`。
10. `schema_version` 必须固定，后续破坏性变更升级版本。

## 最小有效 YAML 示例

```yaml
schema_version: "screenplay_yaml/v0.1"
metadata:
  title: "无名剧本"
  author: "原作者"
  language: "zh-CN"
  created_at: "2026-06-06T10:00:00+08:00"
  generator:
    name: "novel-to-screenplay"
    version: "0.1.0"
source:
  source_type: "novel"
  original_title: "无名小说"
  chapter_count: 3
  chapters:
    - id: "ch_001"
      order: 1
      title: "第一章"
      summary: "主角发现危机。"
    - id: "ch_002"
      order: 2
      title: "第二章"
      summary: "主角追查线索。"
    - id: "ch_003"
      order: 3
      title: "第三章"
      summary: "主角遭遇阻碍。"
adaptation:
  target_format: "screenplay"
  strategy:
    fidelity: "balanced"
    pacing: "compressed"
    narration_policy: "convert_to_action_or_dialogue"
  assumptions: []
  human_review_required: true
story_world:
  logline: "主角追查一份失踪档案，逐步揭开旧案真相。"
  synopsis: "前三章被压缩为四场戏，保留主线危机和关键线索。"
characters:
  - id: "char_protagonist"
    name: "主角"
    role: "protagonist"
locations:
  - id: "loc_archive"
    name: "档案室"
    type: "interior"
structure:
  acts:
    - id: "act_1"
      title: "危机出现"
      scene_ids:
        - "sc_001"
  omitted_material: []
scenes:
  - id: "sc_001"
    order: 1
    chapter_refs:
      - "ch_001"
    scene_heading:
      location_mode: "INT"
      location_id: "loc_archive"
      display: "档案室"
      time_of_day: "NIGHT"
    summary: "主角发现档案缺页。"
    dramatic_function: "inciting_incident"
    characters_present:
      - "char_protagonist"
    beats:
      - id: "beat_001"
        summary: "主角打开档案柜。"
        source_refs:
          - chapter_id: "ch_001"
    script:
      - type: "action"
        text: "档案室灯光忽明忽暗。主角翻开卷宗，停住。"
        source_refs:
          - chapter_id: "ch_001"
      - type: "dialogue"
        character_id: "char_protagonist"
        character_name: "主角"
        text: "少了一页。"
        source_refs:
          - chapter_id: "ch_001"
    revision_status: "ai_draft"
quality_report:
  validation_status: "warning"
  chapter_coverage:
    - chapter_id: "ch_001"
      used_in_scene_ids:
        - "sc_001"
    - chapter_id: "ch_002"
      used_in_scene_ids: []
      coverage_note: "尚未生成对应场景。"
    - chapter_id: "ch_003"
      used_in_scene_ids: []
      coverage_note: "尚未生成对应场景。"
  warnings:
    - code: "LOW_COVERAGE"
      message: "第二章和第三章尚未覆盖。"
  unresolved_questions: []
```

## 为什么不用 FDX 或 Fountain 作为主 Schema

Fountain 很适合作为导出目标，因为它开放、纯文本、容易读写。但它主要描述排版元素，不适合保存章节来源、AI 假设、删减原因、质量报告、人物地点统一表。

FDX 是专业生态的重要格式，但它更偏最终剧本文件交换。第一版如果直接生成 FDX，会把大量改编决策埋进排版结构里，降低作者核对和程序校验的便利性。

因此第一版选择 YAML 作为中间层，后续再从 YAML 导出 Fountain/FDX。

## 版本演进建议

- v0.1：完成小说章节到结构化剧本初稿。
- v0.2：增加严格 JSON Schema 校验文件，YAML 解析后按 JSON Schema 验证。
- v0.3：增加 Fountain 导出字段映射。
- v0.4：增加分集、短剧节奏、分镜和制片拆解字段。
- v1.0：Schema 稳定，保证向后兼容迁移。
