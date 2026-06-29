# xhbx — 保险教练知识沉淀智能体

AgentScope 驱动的保险绩优案例知识沉淀系统：读取课件/讲义/转写稿（docx / pptx / pdf / txt），
研判内容是否值得沉淀进向量库并给出理由，将关键内容提取为标准化 Markdown 并附带元数据；
可选地用视觉模型把课件配图中的信息图按页绑定到原文素材后再生成正文。

产物用于下游 AI 教练系统的四个智能体：问答、课程推荐、AI 组卷、剧本陪练。
新增的销售洞察链路会额外沉淀案例级销售策略、场景化话术和异议处理建议，
供 AI 教练在咨询、陪练和话术建议场景中调用。

> 本期边界：只产出 `md` + 元数据 sidecar，**不做 embedding、不写向量库**（由下游统一处理）。

## 环境要求

- Python ≥ 3.12
- [uv](https://github.com/astral-sh/uv) 包管理器

## 安装

```bash
uv sync
```

## 配置

复制 `.env.example` 为 `.env` 并填入第三方平台凭证：

```bash
cp .env.example .env
```

| 变量 | 用途 | 示例 |
|---|---|---|
| `QWEN_API_KEY` | 第三方平台密钥 | `sk-...` |
| `QWEN_BASE_URL` | OpenAI 兼容端点 | `https://api.mixroute.ai/v1` |
| `QWEN_MODEL_NAME` | 文本研判/提取模型 | `qwen3.7-max` |
| `QWEN_VISION_MODEL_NAME` | 视觉识别模型（可选，缺省 `gpt-4o`） | `gpt-4o` |

> ⚠️ qwen 系列**不支持图像输入**，视觉识别需用独立的多模态模型（如 `gpt-4o`），
> 与文本模型共用同一 `api_key`/`base_url`。`.env` 含真实密钥，**不会提交**（已 gitignore）。

原始素材放在 `数据/绩优案例/`，组织为「案例 → 节 → 素材文件」层级（同样 gitignore）。

## 用法

CLI 入口为 `insurance-coach-md`（经 `uv run` 调用）：

```bash
# 统计全库：案例数、节数、文件类型分布、跳过的媒体数
uv run insurance-coach-md stats

# 解析并预览单个节（不调用 LLM）
uv run insurance-coach-md show "<案例>/<节>" --preview 400

# 研判 + 提取单个节并落盘（含视觉；--no-vision 跳过配图识别，--review 加质检）
uv run insurance-coach-md build "<案例>/<节>"
uv run insurance-coach-md build "<案例>/<节>" --no-vision
uv run insurance-coach-md build "<案例>/<节>" --review
uv run insurance-coach-md build "<案例>/<节>" --review --auto-fix  # 质检有问题时返修并复检

# 全库批处理（分组 → 研判 → 提取 →（可选）视觉 →（可选）质检/返修 → 落盘 + manifest）
uv run insurance-coach-md run --concurrency 4
uv run insurance-coach-md run --limit 5            # 只跑前 5 个单元（调试）
uv run insurance-coach-md run --force              # 忽略增量，强制重跑
uv run insurance-coach-md run --no-vision          # 关闭视觉识别
uv run insurance-coach-md run --review             # 每节做质检并汇总到 manifest
uv run insurance-coach-md run --review --auto-fix  # 质检有问题时返修并复检
uv run insurance-coach-md run --grouping single-file   # 单文件=单元（拍平数据兜底）

# 案例级销售洞察：整合一个完整案例下所有节，提取销售策略、销售话术与异议处理
uv run insurance-coach-md sales-insights "<案例>"
uv run insurance-coach-md sales-insights "<案例>" --no-vision
uv run insurance-coach-md sales-insights --all
```

> 视觉识别支持 pptx 与 pdf 内嵌图片；质检（`--review`）会审计整理稿的 Markdown 规范性、
> 信息保真（无杜撰/无遗漏）与有无加工旁白，结果写入同目录 `<节>.review.md`，
> 并汇总到 `manifest.json`。返修（`--auto-fix`）必须配合 `--review` 使用：初检发现问题时
> 会调用返修智能体，并在复检通过后才采用返修稿覆盖 `<节>.md`。

## 销售洞察智能体

`sales-insights` 是一条案例级侧路流水线，不改变原有 Markdown 入库流程。
它会读取同一案例下的所有节，先逐节采集销售证据，再整合为完整案例的销售方法论和可复用话术。

| 智能体 | 处理粒度 | 职责 | 主要产物 |
|---|---|---|---|
| `SectionSalesEvidenceAgent` | 单节 | 从原始素材中保真采集客户信号、销售动作、原始话术、客户异议和候选销售策略；只做证据抽取，不对整案策略做最终定论。 | `<节>.sales_evidence.json` |
| `CaseSalesInsightAgent` | 完整案例 | 汇总所有节级销售证据，归纳案例级销售策略、客户旅程、场景化话术和异议处理建议。 | `case.sales_insights.json`、`case.sales_playbook.md` |

设计上区分“策略”和“话术”：

- 销售策略是抽象方法论，例如需求五步面谈、缺口营销、保单整理、5S 类销售法等；同一个策略可能出现在多个案例中，输出会带 `aliases`、适用阶段、步骤、正反做法、置信度和证据引用。
- 销售话术是具体场景下可复用的表达方式，例如售前吸引客户、需求面谈追问、方案解释、异议处理、促成下一步等；输出会保留原始话术、改写后的教练建议话术、适用场景、客户触发点、追问问题和合规提示。

AI 教练消费这些产物时，建议优先读取 `case.sales_insights.json` 做结构化检索：

- 用户问“这个客户应该怎么推进”时，按客户阶段和触发点匹配 `customer_journey`、`strategies` 和 `scripts`。
- 用户问“类似场景怎么说”时，按 `stage`、`scenario`、`customer_trigger` 找到话术，并结合 `follow_up_questions` 引导下一轮咨询。
- 用户问“客户有异议怎么办”时，按 `objection_handling` 返回诊断、推荐回应和相关话术。
- 对外回复时应引用 `evidence_refs` 对应的原始证据，并遵守 `compliance_notes`；若证据不足，应提示需要更多客户背景，而不是编造策略或承诺收益。

## 产物

```
output/
├── <案例>/<节>.md            # YAML frontmatter + 标准化正文（可融合配图信息）
├── <案例>/<节>.meta.json     # 单元级元数据（研判理由、四维价值评级等）
├── <案例>/<节>.provenance.json  # 块级溯源（Markdown 块 → 源文件页码/标题/段落）
├── <案例>/<节>.sales_evidence.json  # 单节销售证据：客户信号/销售动作/原始话术/异议
├── <案例>/case.sales_insights.json  # 案例级销售策略、话术、异议处理结构化数据
├── <案例>/case.sales_playbook.md    # 面向人工审阅的案例销售洞察手册
├── <案例>/<节>.review.md     # 可选：质检报告（--review 时生成）
├── manifest.json             # 全库汇总：每节 status/value_score/topics/reason/review_*
└── .image_cache/             # 配图识别缓存（按 sha256，空文件=装饰图）
```

开启视觉时，系统先将 pptx/pdf 内的信息图转写绑定到对应页素材的 `本页配图内容`，
再交给研判、提取与质检链路；装饰图（logo/纹理/分割线/标语）与无价值碎片自动丢弃，
不入正文。

`sales-insights` 会以完整案例为单位整合所有节的内容：先生成节级销售证据，
再提炼案例级销售策略、场景化话术和异议处理建议。该链路仍只写本地 sidecar 文件，
不做 embedding、不写向量库。

## Web 界面

启动本地 Web 工作台：

```bash
uv run insurance-coach-web
```

浏览器打开 `http://127.0.0.1:6543`。界面支持上传单个 `docx / pptx / pdf / txt`
文件，或上传包含这些素材的 `zip` 压缩包；处理过程会显示任务状态，完成后可下载
生成的 Markdown、元数据 JSON、块级溯源 JSON、质检报告等结果文件，也可一键下载全部结果 ZIP。

如需通过 ngrok 访问公网地址，请映射 Web 服务实际监听端口：

```bash
ngrok http 6543
```

Web 任务的上传文件与结果隔离保存在 `web_runs/<task_id>/`，不会写入 `数据/` 或默认
`output/` 目录。模型配置仍读取项目根目录 `.env`。

## 测试

```bash
uv run pytest -q
```

测试使用 fake 模型，不调用真实 API、不烧费用。
