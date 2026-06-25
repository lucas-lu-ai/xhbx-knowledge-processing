# xhbx — 保险教练知识沉淀智能体

AgentScope 驱动的保险绩优案例知识沉淀系统：读取课件/讲义/转写稿（docx / pptx / pdf / txt），
研判内容是否值得沉淀进向量库并给出理由，将关键内容提取为标准化 Markdown 并附带元数据；
可选地用视觉模型把课件配图中的信息图转写进正文。

产物用于下游 AI 教练系统的四个智能体：问答、课程推荐、AI 组卷、剧本陪练。

> 本期边界：只产出 `md` + 元数据 sidecar，**不做 embedding、不写向量库**（由下游统一处理）。
> 架构细节见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

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

# 研判 + 提取单个节并落盘（含视觉；--no-vision 跳过配图识别）
uv run insurance-coach-md build "<案例>/<节>"
uv run insurance-coach-md build "<案例>/<节>" --no-vision

# 全库批处理（分组 → 研判 → 提取 →（可选）视觉 → 落盘 + manifest）
uv run insurance-coach-md run --concurrency 4
uv run insurance-coach-md run --limit 5            # 只跑前 5 个单元（调试）
uv run insurance-coach-md run --force              # 忽略增量，强制重跑
uv run insurance-coach-md run --no-vision          # 关闭视觉识别
uv run insurance-coach-md run --grouping single-file   # 单文件=单元（拍平数据兜底）
```

## 产物

```
output/
├── <案例>/<节>.md            # YAML frontmatter + 标准化正文（+ 可选视觉章节）
├── <案例>/<节>.meta.json     # 结构化元数据（研判理由、四维价值评级、溯源等）
├── manifest.json             # 全库汇总：每节 status/value_score/topics/reason
└── .image_cache/             # 配图识别缓存（按 sha256，空文件=装饰图）
```

开启视觉时，正文末尾追加 `## 课件图片信息（视觉识别）` 章节，逐条标注「第 N 页配图」；
装饰图（logo/纹理/分割线/标语）与无价值碎片自动丢弃，不入正文。

## 测试

```bash
uv run pytest -q
```

测试使用 fake 模型，不调用真实 API、不烧费用。
