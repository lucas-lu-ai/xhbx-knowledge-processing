# 保险教练知识沉淀智能体 · 架构说明

> 项目代号：`xhbx` ｜ 包名：`insurance_coach_agents` ｜ 框架：AgentScope 2.0.2 ｜ 运行时：Python ≥ 3.12

## 1. 背景与定位

为保险公司客户搭建的 **AI 教练系统**由四个下游业务智能体组成：

| 下游智能体 | 职责 | 对知识库的诉求 |
|---|---|---|
| 问答专业智能体 | 回答保险展业/产品/话术类问题 | 准确、可溯源的知识片段 |
| 推荐专业智能体 | 按用户知识薄弱点推荐课程 | 带主题/技能标签的内容 |
| AI 组卷智能体 | 按技能掌握情况生成考题 | 结构化、可考点化的知识 |
| 剧本生成智能体 | 生成话术陪练剧本 | 真实面谈流程、话术原文、异议处理 |

**本项目（知识沉淀智能体）是上述四者的共同上游**：把客户提供的原始绩优案例素材，
加工成"干净、结构化、带元数据、可向量化"的 Markdown 知识单元。

> **本期边界**：只产出 `md` + 元数据/溯源 sidecar，**不做 embedding、不写向量库**——向量化与入库由下游统一处理。
> 案例级销售洞察同样只产出本地 sidecar：`<节>.sales_evidence.json`、
> `case.sales_insights.json` 与 `case.sales_playbook.md`，不直接进入向量库。

## 2. 数据资产

原始素材位于 `数据/绩优案例/`，组织为「**案例 → 节 → 素材文件**」层级，
实测共 **15 个案例、58 个「节」**。每个节是一个标准素材包：

| 文件类型 | 性质 | 处理策略 |
|---|---|---|
| `.docx` | **已人工整理的结构化讲义**（含「课程主题/核心主旨」+ 标题层级 + 表格） | ⭐ 主干来源 |
| `.pptx` | 课件（框架图、要点骨架） | 补充框架与话术骨架 |
| `.pdf` | 可能出现的讲义/资料（当前数据未见，流程预留支持） | 与 docx 同级解析 |
| `.txt` | 音频原始转写（口语化、含冗余） | 补充 docx 未覆盖的口语细节 |
| `.mp3/.mp4/.mov/.m4a` | 音视频媒体 | **跳过**（已有 txt 转写，本期不做 ASR） |

**核心判断**：docx 已是高质量人工讲义，因此任务本质不是"从噪音中艰难抽取"，
而是 **以 docx 为骨架 → pptx/txt/视觉信息交叉补全 → 价值研判（给理由）→ 标准化 md + 元数据/溯源标注**。

## 3. 技术底座（AgentScope 2.0.2）

AgentScope 2.0 是 Claude-Agent-SDK 风格的**全异步、配置驱动**架构（含 `credential` /
`toolkit` / `formatter` / `message` 等概念），与网络上常见的 1.x 文档不兼容。以下签名均经本地实测确认。

### 3.1 模型层（第三方 OpenAI 兼容平台）

客户使用第三方平台（`https://api.mixroute.ai/v1`），**采用 OpenAI 风格的类**而非 DashScope 类：

```python
from agentscope.credential import OpenAICredential
from agentscope.model import OpenAIChatModel
from agentscope.formatter import OpenAIChatFormatter

cred = OpenAICredential(api_key=..., base_url="https://api.mixroute.ai/v1")
model = OpenAIChatModel(credential=cred, model="qwen3.7-max",
                        formatter=OpenAIChatFormatter(), stream=False)
```

- **研判**用 `model.generate_structured_output(messages, structured_model=Assessment)` 强制结构化输出。
- **提取**用 `await model(messages)` 取 `ChatResponse`，再过滤 thinking 块取正文。
- qwen 为 thinking 模式，结构化输出底层的 forced `tool_choice` 被平台拒绝，
  AgentScope 自动回退 `auto` 并成功（仅一条无害 warning）。

> 设计取舍：Assessor/Extractor 是**单轮 LLM 调用**，直接用 model 层而非 `Agent`(ReAct) 类，更省 token、更可控。

### 3.1.1 视觉模型（独立于文本模型）

课件配图识别走**多模态消息**：用 `DataBlock(type="data", source=Base64Source(media_type="image/png", data=...))`
承载图片，`OpenAIChatFormatter` 会自动转成 OpenAI 的 `image_url`（`data:image/png;base64,...`）格式。

> **实测结论**：`qwen3.7-max`（及 mixroute 上的整个 qwen 系列）**不支持图像输入**，传图会报
> `400 Unexpected item type in content`。因此视觉识别走**独立的视觉模型**（默认 `gpt-4o`，
> 已实测在本平台可用），文本研判/提取仍用 `qwen3.7-max`；二者共用同一 `api_key` 与 `base_url`。

- **网络健壮性**：模型层设 `max_retries=5, retry_delay=2`（超时不能经 `client_kwargs` 传入，
  该版本会把它透传给每次 `create()` 而报 `TypeError`）。
- 单图识别失败**降级不中断**整条流水线，并打 `logging.warning`（避免"模型不支持视觉"被静默吞成"全是装饰图"）。

### 3.2 环境变量（来自 `.env`）

| 变量 | 用途 | 示例 |
|---|---|---|
| `QWEN_API_KEY` | 第三方平台密钥 | （不入库） |
| `QWEN_BASE_URL` | OpenAI 兼容端点 | `https://api.mixroute.ai/v1` |
| `QWEN_MODEL_NAME` | 文本研判/提取模型 | `qwen3.7-max` |
| `QWEN_VISION_MODEL_NAME` | 视觉识别模型（可选，缺省 `gpt-4o`） | `gpt-4o` |

## 4. 系统架构

一条 **"以知识单元为粒度"的流水线**：确定性的分组 + 解析在前，LLM 推理在后，原子落盘殿后。

```
 数据/绩优案例/ 下的素材文件
            │
   ┌────────▼──────────┐  分组策略层（grouping.py）
   │  SourceGroup 列表   │  directory（目录=单元，默认）/ single-file（单文件=单元，兜底）
   └────────┬──────────┘
            ▼  load_group
   ┌───────────────────┐  确定性解析层（parsers/，不进 LLM）
   │  RawSection 对象    │  docx标题层级+表格 / pptx按页 / pdf逐页 / txt清洗；媒体跳过
   └────────┬──────────┘
            ▼
   ① 视觉增强（可选，enrich + ImageDescriber，走 gpt-4o）
      pptx/pdf抽图 → sha256去重 + 尺寸预过滤 → 视觉识别（装饰图/碎片丢弃）
      → 信息图转写绑定回对应页的 RawSection 素材；按 sha256 缓存
            ▼
   ② AssessorAgent   研判：能否入库？理由 + 主题标签 + 四维价值评级 + 评分（结构化输出）
            ▼
   ③ ExtractorAgent  提取：以docx为骨架融合pptx/txt/同页视觉信息 → 标准 md；cleanup 清洗元注释/列表符/围栏
            ▼
   ④ 质检（可选 --review，ReviewerAgent）：对最终稿审计规范性/信息保真/无旁白 → ReviewResult
            ▼
   output_writer（原子写入：先 .tmp 再 rename）
   → output/<案例>/<节>.md  +  <节>.meta.json  +  <节>.provenance.json  +  可选 <节>.review.md
            ▼
   pipeline 汇总 → output/manifest.json（每节状态/评分/理由，供抽检）
```

主流水线之外还有一条 **案例级销售洞察支线**，由 `sales-insights` 命令触发。它复用解析、
视觉增强和模型构造能力，但处理粒度从“单节知识单元”上升到“完整案例”：

```
同一案例下的 SourceGroup 列表
            │  按自然顺序排序（第2节 < 第10节）
            ▼
逐节 load_group / 可选视觉增强
            ▼
SectionSalesEvidenceAgent
  单节销售证据：客户信号 / 销售动作 / 原始话术 / 异议 / 候选策略
            ▼
写出 <节>.sales_evidence.json
            ▼
CaseSalesInsightAgent
  整案归纳：客户旅程 / 销售策略 / 场景话术 / 异议处理
            ▼
sales_output_writer
  → case.sales_insights.json
  → case.sales_playbook.md
```

### 4.1 设计原则

- **分组与解析与推理分离**：分组（怎么归并文件）与解析（读文件）都是确定性的，
  独立于 LLM 层；换分组策略不影响下游。
- **解析放工具层**：确定性、可单测、省 token；LLM 只做研判与整理。
- **研判独立成 Agent**：客户要求"给出理由"，产出可审计的 `manifest.json`。
- **以知识单元为流水线粒度**：天然可并发、失败单元隔离、增量友好（跳过已产出）。
- **销售洞察分两级**：节级只采集证据，案例级才抽象策略与话术，避免用单节内容过度泛化。
- **原子落盘**：中断不会留下空/半截文件。
- **不可变数据流**：`SourceGroup → RawSection → Assessment / ExtractedDoc`，不就地修改。
- **合规与溯源优先**：案例级话术必须有合规提示；若节级证据有来源引用，案例级每个洞察条目
  必须保留有效 `evidence_refs`，空引用对象不算可追溯来源。

### 4.2 各环节职责

| 环节 | 输入 | 输出 | 是否用 LLM |
|---|---|---|---|
| 分组层（grouping） | 素材根目录 | `SourceGroup` 列表 | 否 |
| 解析层（parsers） | 一组文件 | `RawSection` | 否 |
| ① 视觉增强（enrich + ImageDescriber，可选） | `RawSection` + 节内 pptx/pdf 配图 | 绑定了同页配图转写的 `RawSection`（装饰图/碎片自动丢弃） | 是（视觉模型） |
| ② AssessorAgent | `RawSection` | `Assessment`（入库与否、理由、标签、四维评级、评分） | 是 |
| ③ ExtractorAgent | `RawSection` | `ExtractedDoc`（标准 md 正文，经 cleanup） | 是 |
| ④ ReviewerAgent（可选 `--review`） | `ExtractedDoc` + `RawSection` | `ReviewResult`（规范性/保真/无旁白 + issues + score），汇总进 manifest | 是 |
| output_writer | 上述结果 | `<节>.md` + `<节>.meta.json` + `<节>.provenance.json` + 可选 `<节>.review.md`（原子写） | 否 |
| pipeline | 全部结果 | `manifest.json` | 否 |
| SectionSalesEvidenceAgent（`sales-insights`） | 单节 `RawSection` | `SectionSalesEvidence`：客户信号、销售动作、原始话术、异议、候选策略 | 是 |
| CaseSalesInsightAgent（`sales-insights`） | 同一案例下全部 `SectionSalesEvidence` | `CaseSalesInsights`：客户旅程、销售策略、场景话术、异议处理 | 是 |
| sales_output_writer | 销售证据与案例洞察 | `<节>.sales_evidence.json` + `case.sales_insights.json` + `case.sales_playbook.md` | 否 |

### 4.3 案例级销售洞察 Agent

`sales-insights` 命令使用两个新智能体，并保持“证据采集”和“策略归纳”分离：

1. `SectionSalesEvidenceAgent`
   - 输入：单节 `RawSection`，可包含视觉增强后的课件/PDF 配图转写。
   - 输出：`SectionSalesEvidence`。
   - 职责：只采集销售证据，包括客户信号、销售动作、原始话术、客户异议和候选策略。
   - 边界：不把单节内容包装成完整方法论；候选策略必须标记依据和置信度。

2. `CaseSalesInsightAgent`
   - 输入：同一案例下按自然顺序排列的全部 `SectionSalesEvidence`。
   - 输出：`CaseSalesInsights`。
   - 职责：从完整案例视角提炼客户旅程、贯穿策略、场景话术和异议处理。
   - 边界：不能生成无证据支撑的策略；`coach_wording` 必须忠于 `source_quote` 的语义。

`sales_pipeline.run_case_sales_insights()` 负责把这两个 agent 串起来，并做三类保护：

- **身份归一化**：节级证据写出前强制使用真实 `section.case_name` / `section.section_name`；
  案例级洞察写出前强制使用用户请求的 `case_name`，避免模型返回错误名称导致产物写到错误目录。
- **有效证据过滤**：若某节返回的 `SectionSalesEvidence` 五类列表全为空，不写出该节销售证据，
  也不参与案例级归纳；若整个案例都没有销售证据，返回失败。
- **来源与合规校验**：若节级证据含有效 `source_refs`，则案例级每个 customer journey / strategy /
  script / objection handling 条目都必须有至少一个有效 `evidence_refs`；`CaseSalesScript` 的
  `compliance_notes` 为空时自动补充保守合规提示。

## 5. 目录结构

```
xhbx/
├── docs/ARCHITECTURE.md          # 本文档
├── README.md                     # 使用说明
├── 数据/绩优案例/                 # 原始素材（gitignore）
├── output/                       # 产物（gitignore）
├── .env / .env.example           # 第三方平台凭证
├── pyproject.toml                # 依赖与 CLI 入口（insurance-coach-md）
├── src/insurance_coach_agents/
│   ├── cli.py                    # 入口：stats / show / build / run / sales-insights
│   ├── config.py                 # 路径、文件类型映射、模型环境配置
│   ├── models.py                 # RawSection/Assessment/ExtractedDoc/ReviewResult/销售洞察契约
│   ├── parsers/
│   │   ├── docx_parser.py  pptx_parser.py  pdf_parser.py  txt_parser.py
│   │   ├── image_extract.py      # pptx/pdf 抽图 + sha256 去重 + 尺寸预过滤
│   │   ├── section_loader.py     # 单节加载 + parse_file 分派
│   │   └── grouping.py           # 目录/单文件分组策略 + load_group
│   ├── agents/
│   │   ├── factory.py            # 构造文本/视觉 OpenAIChatModel + 响应/素材辅助
│   │   ├── assessor.py           # 研判
│   │   ├── extractor.py          # 提取
│   │   ├── vision.py             # ImageDescriber：配图视觉识别 + 装饰/碎片过滤 + 缓存
│   │   ├── enrich.py             # 视觉增强：配图转写按页绑定回 RawSection
│   │   ├── reviewer.py           # ReviewerAgent：整理稿质检（规范性/保真/无旁白）
│   │   ├── sales_insights.py     # 销售洞察：节级证据采集 + 案例级策略/话术归纳
│   │   ├── cleanup.py            # 产出清洗（元注释/列表符/残留符）
│   │   └── prompts.py            # 中文 system prompt（含视觉）
│   ├── provenance.py             # 块级溯源：源素材锚点 + Markdown 块匹配
│   ├── output_writer.py          # 原子落盘 md + meta/provenance/review json
│   ├── sales_output_writer.py    # 原子落盘销售证据/案例销售洞察 json + playbook
│   ├── sales_pipeline.py         # 案例级 sales-insights 编排
│   └── pipeline.py               # 批处理编排 + manifest
└── tests/                        # 解析/智能体/清洗/编排单测（fake 模型，不烧 API）
```

## 6. 产物格式

Markdown = YAML frontmatter（`case/section/title/topics/serves/value_score/worth_storing/sources`）
+ 标准化正文；开启视觉时，信息图转写先绑定回 pptx/pdf 对应页素材，再由 ExtractorAgent 与原文语义一起整理。
同名 `.meta.json` 存单元级结构化元数据（含研判 `reason`、`section_dir`）；
同名 `.provenance.json` 存块级溯源（最终 Markdown 块 → 源文件页码/标题/段落）；
同名 `.sales_evidence.json` 存节级销售证据（客户信号、销售动作、原始话术、异议、候选策略）；
案例级 `case.sales_insights.json` 存整案销售策略、场景话术和异议处理结构化数据；
案例级 `case.sales_playbook.md` 是面向人工审阅的销售洞察手册；
全局 `manifest.json` 汇总每节 `status/value_score/topics/reason`，供人工抽检；
开启 `--review` 时附 `review_passed/review_score/review_issues` 与汇总 `review_failed`。
视觉识别结果按图片 sha256 缓存于 `output/.image_cache/`（空文件=装饰图/无价值，可重跑复用）。

### 6.1 `meta.json` 与 `provenance.json` 的分工

`meta.json` 是**知识单元级**元数据，服务筛选、检索过滤和 manifest 汇总：

- `case` / `section` / `title`：案例、章节与整理稿标题。
- `topics` / `serves` / `value_score` / `worth_storing` / `reason`：AssessorAgent 的研判结果。
- `sources`：参与该单元整理的文件类型列表，如 `["docx", "pptx", "txt"]`。
- `section_dir`：原始节目录标识，用于回到素材包。

`provenance.json` 是**Markdown 块级**溯源，服务 RAG chunk 入库、答案引用和人工核查。它不写入
Markdown 正文，避免污染可向量化文本；下游可按 `markdown_start_line` / `markdown_end_line`
把 Markdown 正文切块，并读取对应 `source_refs` 做引用。

### 6.2 `provenance.json` 写入时机

`provenance.json` 由 `output_writer.write_section_output()` 在落盘阶段同步写入：

1. `pipeline` 得到最终 `RawSection`、`Assessment`、`ExtractedDoc`，以及可选 `ReviewResult`。
2. `output_writer` 先根据 `Assessment` 和 `ExtractedDoc` 渲染 Markdown frontmatter。
3. `output_writer` 调用 `build_provenance(section, doc, body_start_line=...)`。
4. `build_provenance()` 只使用确定性数据：增强后的 `RawSection` 与最终 `doc.body_markdown`。
5. `output_writer` 分别原子写入 `.md`、`.meta.json`、`.provenance.json`，有质检时再写 `.review.md`。

`body_start_line` 是最终 `.md` 文件中正文第一行的行号。计算方式为：

```python
body_start_line = len(frontmatter.splitlines()) + 2
```

原因是最终 Markdown 文件格式为：

```markdown
---
frontmatter...
---

# 正文标题
```

也就是 frontmatter 结束后有一个空行，因此正文第一行 = frontmatter 行数 + 2。这样
`provenance.json` 的 `markdown_start_line` / `markdown_end_line` 可以直接定位最终 `.md` 文件。

### 6.3 `provenance.json` 顶层结构

示例：

```json
{
  "version": 1,
  "case": "案例X",
  "section": "第1节",
  "title": "异议处理",
  "sources": [
    {
      "source_id": "pptx:deck.pptx",
      "type": "pptx",
      "filename": "deck.pptx",
      "path": "案例X/第1节/deck.pptx"
    }
  ],
  "blocks": [
    {
      "block_id": "b002",
      "heading_path": ["异议处理", "关键话术"],
      "markdown_start_line": 12,
      "markdown_end_line": 16,
      "text_hash": "sha256...",
      "source_refs": [
        {
          "source_id": "pptx:deck.pptx",
          "anchor_id": "pptx:deck.pptx#page-2",
          "locator": {
            "page": 2,
            "source_start_line": 4,
            "source_end_line": 6
          },
          "match_score": 0.8125
        }
      ]
    }
  ]
}
```

字段含义：

| 字段 | 类型 | 含义 |
|---|---|---|
| `version` | number | provenance schema 版本；当前为 `1`，后续字段变更时递增。 |
| `case` | string | 案例名，来自 `RawSection.case_name`。 |
| `section` | string | 节名，来自 `RawSection.section_name`。 |
| `title` | string | 最终 Markdown 知识单元标题，来自 `ExtractedDoc.title`。 |
| `sources` | array | 本知识单元参与整理的非空源文件列表。 |
| `blocks` | array | 最终 Markdown 正文按标题切分后的块列表。 |

### 6.4 `sources[]` 字段

`sources` 来自 `RawSection.files` 中所有非空 `ParsedFile`。每个元素含义：

| 字段 | 类型 | 含义 |
|---|---|---|
| `source_id` | string | 源文件稳定 ID，格式为 `<file_type>:<filename>`，如 `docx:讲义.docx`、`pptx:课件.pptx`。 |
| `type` | string | 文件类型：`docx` / `pptx` / `pdf` / `txt`。 |
| `filename` | string | 原始文件名。 |
| `path` | string | 源文件在素材包中的路径，格式为 `<section_dir>/<filename>`；Web 上传任务中 `section_dir` 可能是任务目录路径。 |

### 6.5 `blocks[]` 字段

`blocks` 来自最终 `doc.body_markdown`。切分规则是：每个 Markdown 标题行（`#` 到 `######`）
开启一个块，块内容持续到下一个标题前。没有标题时，整个正文作为 `b001`。

每个元素含义：

| 字段 | 类型 | 含义 |
|---|---|---|
| `block_id` | string | 块 ID，按正文出现顺序生成，如 `b001`、`b002`。 |
| `heading_path` | string[] | 当前块的标题路径，如 `["异议处理", "关键话术"]`。 |
| `markdown_start_line` | number | 当前块在最终 `.md` 文件中的起始行号，包含 frontmatter 后的真实行号。 |
| `markdown_end_line` | number | 当前块在最终 `.md` 文件中的结束行号。 |
| `text_hash` | string | 当前块文本的 SHA-256，用于下游校验块内容是否被改动。 |
| `source_refs` | array | 与该 Markdown 块最相关的源素材锚点，最多 3 条。 |

### 6.6 `source_refs[]` 字段

`source_refs` 是确定性匹配结果，不是模型生成的引用。当前算法在 `provenance.py` 中完成：

1. 将源素材切成可定位锚点（source anchors）。
2. 将最终 Markdown 切成标题块（markdown blocks）。
3. 对每个 Markdown 块和每个源素材锚点做文本归一化。
4. 使用字符 bigram 重叠计算 `match_score`。
5. 每个 Markdown 块最多保留分数最高的 3 个源锚点。

每个元素含义：

| 字段 | 类型 | 含义 |
|---|---|---|
| `source_id` | string | 指向 `sources[].source_id`。 |
| `anchor_id` | string | 源素材锚点 ID，格式随锚点类型变化，如 `pptx:deck.pptx#page-2`。 |
| `locator` | object | 源素材内的定位信息，字段随文件类型/锚点类型变化。 |
| `match_score` | number | 0~1 的文本重叠分数，越高表示该源锚点与 Markdown 块越相似；不是置信概率。 |

`locator` 的常见形态：

```json
{ "page": 2, "source_start_line": 4, "source_end_line": 6 }
```

用于 pptx/pdf 按页解析结果。`page` 是页码；`source_start_line` / `source_end_line`
是该页块在解析后 `ParsedFile.text` 中的行号。

```json
{ "heading_path": ["课程主题", "异议处理"], "source_start_line": 1, "source_end_line": 8 }
```

用于 docx 等带 Markdown 标题的文本。`heading_path` 是源素材解析文本中的标题路径。

```json
{ "block_index": 3, "source_start_line": 12, "source_end_line": 16 }
```

用于没有页标题/Markdown 标题的文本兜底锚点，如部分 txt 或异常解析结果。

### 6.7 源素材锚点生成规则

`build_provenance()` 对不同源文件使用不同锚点策略：

| 文件类型 | 优先锚点 | 兜底锚点 | 说明 |
|---|---|---|---|
| `pptx` | `## 第 N 页` 页块 | 空行分隔的段落块 | pptx parser 本身按页输出，视觉增强也把配图转写绑定到对应页。 |
| `pdf` | `## 第 N 页` 页块 | 空行分隔的段落块 | pdf parser 逐页提取文本；扫描件无文本时不会进入非空 sources。 |
| `docx` | Markdown 标题块 | 空行分隔的段落块 | docx parser 保留 Word 标题层级与表格。 |
| `txt` | Markdown 标题块（若存在） | 空行分隔的段落块 | txt 多为口语转写，通常走段落块兜底。 |

### 6.8 准确性边界

`provenance.json` 是**块级、保守匹配**，不是逐字逐句引用：

- ExtractorAgent 会融合、压缩、改写多个来源，事后无法可靠恢复每一句的唯一出处。
- `source_refs` 表示“该 Markdown 块最可能参考了这些源锚点”，适合 RAG chunk 引用、人工抽查和召回调试。
- `match_score` 只基于文本重叠，不表示事实正确概率；质检仍由 ReviewerAgent 负责。
- 若某块是高度概括或模型改写幅度很大，`source_refs` 可能为空或分数较低；这比伪造精确引用更安全。
- 若需要强溯源，可在下一阶段把 ExtractorAgent 改为结构化输出块列表，并要求模型为每个块显式选择 source anchors。

### 6.9 销售洞察产物

`sales-insights` 会新增三类 sidecar：

```text
output/
├── <案例>/<节>.sales_evidence.json
├── <案例>/case.sales_insights.json
└── <案例>/case.sales_playbook.md
```

`<节>.sales_evidence.json` 是节级证据，不做完整方法论定论。核心字段：

| 字段 | 含义 |
|---|---|
| `customer_signals` | 客户状态、需求信号、异议苗头、决策障碍。 |
| `sales_actions` | 销售人员动作，如场景提问、风险唤醒、需求追问、异议接纳、促成。 |
| `script_quotes` | 素材中的原始话术，尽量保留原话。 |
| `objections` | 客户明确异议及素材中的应对证据。 |
| `strategy_candidates` | 本节可能体现的候选策略，包含依据、置信度和 `inferred` 标记。 |

`case.sales_insights.json` 是案例级洞察。核心字段：

| 字段 | 含义 |
|---|---|
| `customer_journey` | 客户在完整案例中的阶段变化、销售目标和关键动作。 |
| `strategies` | 贯穿案例的销售策略、步骤、建议做法和避免做法。 |
| `scripts` | 场景化话术，区分 `source_quote`（原始话术）和 `coach_wording`（教练推荐话术）。 |
| `objection_handling` | 异议诊断、推荐回应、关联策略和关联话术。 |

`case.sales_playbook.md` 由同一份 `CaseSalesInsights` 渲染，方便业务人员审阅。它会展示
客户旅程、销售策略、场景话术、异议处理、合规提醒和来源依据。若 `scripts[].compliance_notes`
为空，模型契约会自动补充：

```text
未识别到特定合规风险，仍需以公司合规要求和正式条款为准。
```

销售洞察的 `evidence_refs` 是模型生成的轻量来源引用，不等同于 `provenance.json` 的确定性块级匹配。
当前字段包括 `section_name`、`source_id`、`filename`、`quote`。为了避免伪溯源，空对象 `{}` 或全空字段
不会被视为有效来源。

## 7. 实现里程碑

| 里程碑 | 内容 | 状态 |
|---|---|---|
| **M1** | 解析层 + 数据契约 + CLI（stats/show），真实数据跑通"节 → RawSection" | ✅ |
| **M2** | 接入 OpenAI 风格模型（mixroute/qwen）+ Assessor + Extractor + 落盘 + CLI build | ✅ |
| **M3** | 全库批处理（并发/增量/错误隔离）+ 分组策略 + manifest + 原子写入 + 产出清洗 | ✅ |
| **M4a** | 视觉增强：pptx 配图 → 文字（独立视觉模型 gpt-4o）+ 装饰/碎片过滤 + sha256 缓存 + 降级 | ✅ |
| **M4b** | Reviewer 质检（规范性/信息保真/无旁白，`--review`）+ PDF 图片抽取 | ✅ |
| **M5** | 块级溯源：生成 `<节>.provenance.json`，记录 Markdown 块到源文件页码/标题/段落的引用 | ✅ |
| **M6** | 案例级销售洞察：`SectionSalesEvidenceAgent` + `CaseSalesInsightAgent` + `sales-insights` CLI | ✅ |
