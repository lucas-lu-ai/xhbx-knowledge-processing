# xhbx — 保险教练知识沉淀智能体

AgentScope 驱动的保险绩优案例知识沉淀系统：读取课件/讲义/转写稿（docx / pptx / pdf / txt），
研判内容是否值得沉淀进向量库并给出理由，将关键内容提取为标准化 Markdown 并附带元数据；
可选地用视觉模型把课件配图中的信息图按页绑定到原文素材后再生成正文。

产物用于下游 AI 教练系统的四个智能体：问答、课程推荐、AI 组卷、剧本陪练。

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
```

> 视觉识别支持 pptx 与 pdf 内嵌图片；质检（`--review`）会审计整理稿的 Markdown 规范性、
> 信息保真（无杜撰/无遗漏）与有无加工旁白，结果写入同目录 `<节>.review.md`，
> 并汇总到 `manifest.json`。返修（`--auto-fix`）必须配合 `--review` 使用：初检发现问题时
> 会调用返修智能体，并在复检通过后才采用返修稿覆盖 `<节>.md`。

## 产物

```
output/
├── <案例>/<节>.md            # YAML frontmatter + 标准化正文（可融合配图信息）
├── <案例>/<节>.meta.json     # 单元级元数据（研判理由、四维价值评级等）
├── <案例>/<节>.provenance.json  # 块级溯源（Markdown 块 → 源文件页码/标题/段落）
├── <案例>/<节>.review.md     # 可选：质检报告（--review 时生成）
├── manifest.json             # 全库汇总：每节 status/value_score/topics/reason/review_*
└── .image_cache/             # 配图识别缓存（按 sha256，空文件=装饰图）
```

开启视觉时，系统先将 pptx/pdf 内的信息图转写绑定到对应页素材的 `本页配图内容`，
再交给研判、提取与质检链路；装饰图（logo/纹理/分割线/标语）与无价值碎片自动丢弃，
不入正文。

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
