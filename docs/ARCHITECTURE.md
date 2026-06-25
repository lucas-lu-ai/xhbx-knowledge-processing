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

> **本期边界**：只产出 `md` + 元数据 sidecar，**不做 embedding、不写向量库**——向量化与入库由下游统一处理。

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
而是 **以 docx 为骨架 → pptx/txt 交叉补全 → 价值研判（给理由）→ 标准化 md + 元数据标注**。

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
   ① AssessorAgent   研判：能否入库？理由 + 主题标签 + 四维价值评级 + 评分（结构化输出）
            ▼
   ② ExtractorAgent  提取：以docx为骨架融合pptx/txt → 标准 md；cleanup 清洗元注释/列表符/围栏
            ▼
   ③ 视觉增强（可选，enrich + ImageDescriber，走 gpt-4o）
      pptx/pdf抽图 → sha256去重 + 尺寸预过滤 → 视觉识别（装饰图/碎片丢弃）
      → 信息图转写为 md，追加到正文末尾「## 课件图片信息（视觉识别）」；按 sha256 缓存
            ▼
   ④ 质检（可选 --review，ReviewerAgent）：对最终稿审计规范性/信息保真/无旁白 → ReviewResult
            ▼
   output_writer（原子写入：先 .tmp 再 rename）
   → output/<案例>/<节>.md  +  <节>.meta.json
            ▼
   pipeline 汇总 → output/manifest.json（每节状态/评分/理由，供抽检）
```

### 4.1 设计原则

- **分组与解析与推理分离**：分组（怎么归并文件）与解析（读文件）都是确定性的，
  独立于 LLM 层；换分组策略不影响下游。
- **解析放工具层**：确定性、可单测、省 token；LLM 只做研判与整理。
- **研判独立成 Agent**：客户要求"给出理由"，产出可审计的 `manifest.json`。
- **以知识单元为流水线粒度**：天然可并发、失败单元隔离、增量友好（跳过已产出）。
- **原子落盘**：中断不会留下空/半截文件。
- **不可变数据流**：`SourceGroup → RawSection → Assessment / ExtractedDoc`，不就地修改。

### 4.2 各环节职责

| 环节 | 输入 | 输出 | 是否用 LLM |
|---|---|---|---|
| 分组层（grouping） | 素材根目录 | `SourceGroup` 列表 | 否 |
| 解析层（parsers） | 一组文件 | `RawSection` | 否 |
| ① AssessorAgent | `RawSection` | `Assessment`（入库与否、理由、标签、四维评级、评分） | 是 |
| ② ExtractorAgent | `RawSection` | `ExtractedDoc`（标准 md 正文，经 cleanup） | 是 |
| ③ 视觉增强（enrich + ImageDescriber） | 节内 pptx/pdf 配图 | 追加到正文的视觉章节（装饰图/碎片自动丢弃） | 是（视觉模型） |
| ④ ReviewerAgent（可选 `--review`） | `ExtractedDoc` + `RawSection` | `ReviewResult`（规范性/保真/无旁白 + issues + score），汇总进 manifest | 是 |
| output_writer | 上述结果 | `<节>.md` + `<节>.meta.json`（原子写） | 否 |
| pipeline | 全部结果 | `manifest.json` | 否 |

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
│   ├── cli.py                    # 入口：stats / show / build / run
│   ├── config.py                 # 路径、文件类型映射、模型环境配置
│   ├── models.py                 # ParsedFile/RawSection/Assessment/ServesRating/ExtractedDoc/ReviewResult
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
│   │   ├── enrich.py             # 视觉章节组装（方案 A：汇总到正文末尾）
│   │   ├── reviewer.py           # ReviewerAgent：整理稿质检（规范性/保真/无旁白）
│   │   ├── cleanup.py            # 产出清洗（元注释/列表符/残留符）
│   │   └── prompts.py            # 中文 system prompt（含视觉）
│   ├── output_writer.py          # 原子落盘 md + meta.json
│   └── pipeline.py               # 批处理编排 + manifest
└── tests/                        # 解析/智能体/清洗/编排单测（fake 模型，不烧 API）
```

## 6. 产物格式

Markdown = YAML frontmatter（`case/section/title/topics/serves/value_score/worth_storing/sources`）
+ 标准化正文；开启视觉时，正文末尾追加 `## 课件图片信息（视觉识别）` 章节，逐条标注「第 N 页配图」。
同名 `.meta.json` 存结构化元数据（含研判 `reason`、`section_dir` 溯源）；
全局 `manifest.json` 汇总每节 `status/value_score/topics/reason`，供人工抽检；
开启 `--review` 时附 `review_passed/review_score/review_issues` 与汇总 `review_failed`。
视觉识别结果按图片 sha256 缓存于 `output/.image_cache/`（空文件=装饰图/无价值，可重跑复用）。

## 7. 实现里程碑

| 里程碑 | 内容 | 状态 |
|---|---|---|
| **M1** | 解析层 + 数据契约 + CLI（stats/show），真实数据跑通"节 → RawSection" | ✅ |
| **M2** | 接入 OpenAI 风格模型（mixroute/qwen）+ Assessor + Extractor + 落盘 + CLI build | ✅ |
| **M3** | 全库批处理（并发/增量/错误隔离）+ 分组策略 + manifest + 原子写入 + 产出清洗 | ✅ |
| **M4a** | 视觉增强：pptx 配图 → 文字（独立视觉模型 gpt-4o）+ 装饰/碎片过滤 + sha256 缓存 + 降级 | ✅ |
| **M4b** | Reviewer 质检（规范性/信息保真/无旁白，`--review`）+ PDF 图片抽取 | ✅ |
