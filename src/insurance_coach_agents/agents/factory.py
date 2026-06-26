"""模型构造与响应工具。

集中负责用第三方 OpenAI 兼容平台（mixroute.ai）的凭证构造 ``OpenAIChatModel``，
并提供从 ``ChatResponse`` 中提取纯文本（过滤 thinking 块）的辅助函数。
"""

from __future__ import annotations

from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.model import ChatResponse, OpenAIChatModel
from agentscope.tool import ToolChoice

from ..config import ModelSettings, load_model_settings
from ..models import FileType, RawSection
from .structured_model import RobustOpenAIChatModel

# 网络健壮性：视觉识别会发起大量逐图请求，第三方平台偶发 APIConnectionError，
# 故放大重试次数与退避间隔。注意：超时不可通过 client_kwargs 传入——该 AgentScope
# 版本会把 client_kwargs 透传给每次 completions.create()，create() 不接受 timeout
# 会抛 TypeError，故此处只调重试参数。
_MAX_RETRIES = 5
_RETRY_DELAY = 2.0

# 结构化输出的 tool_choice：本平台的文本模型（qwen / deepseek 等）均为 thinking 模式，
# 不支持强制 tool_choice。AgentScope 默认会强制模型调用工具，触发 400 后再自动降级到
# auto 重试——等于每次结构化调用都白发一次注定失败的请求。直接用 auto 跳过首发失败，
# 既消除告警又省一次往返；模型仍由注入的 system-reminder 提示词引导调用工具。
STRUCTURED_TOOL_CHOICE = ToolChoice(mode="auto")

_TYPE_LABEL = {
    FileType.DOCX: "docx 讲义（人工整理，主干）",
    FileType.PPTX: "pptx 课件（框架要点）",
    FileType.PDF: "pdf 资料",
    FileType.TXT: "txt 音频转写稿（口语化）",
}


def _build_model(model_name: str, settings: ModelSettings) -> OpenAIChatModel:
    """用指定模型名构造指向第三方平台的 ``OpenAIChatModel``。

    使用 OpenAI 风格的凭证与 base_url（而非 DashScope 类），以适配 mixroute.ai。
    ``stream=False`` 以便一次性拿到完整响应，简化下游处理。
    """
    credential = OpenAICredential(
        api_key=settings.api_key, base_url=settings.base_url
    )
    # 用 RobustOpenAIChatModel：对 thinking 模型的结构化输出做容错（固定 auto +
    # 解包单键嵌套 + 校验重试）。普通文本/视觉调用行为与父类一致。
    return RobustOpenAIChatModel(
        credential=credential,
        model=model_name,
        formatter=OpenAIChatFormatter(),
        stream=False,
        max_retries=_MAX_RETRIES,
        retry_delay=_RETRY_DELAY,
    )


def build_chat_model(settings: ModelSettings | None = None) -> OpenAIChatModel:
    """构造文本研判/抽取用的模型（``model_name``，如 qwen3.7-max）。"""
    settings = settings or load_model_settings()
    return _build_model(settings.model_name, settings)


def build_vision_model(settings: ModelSettings | None = None) -> OpenAIChatModel:
    """构造课件配图识别用的视觉模型（``vision_model_name``，如 gpt-4o）。

    qwen 系列不支持图像输入，故视觉识别走独立的多模态模型。
    """
    settings = settings or load_model_settings()
    return _build_model(settings.vision_model_name, settings)


def response_text(response: ChatResponse) -> str:
    """从 ``ChatResponse`` 提取最终文本，过滤 thinking 块。

    qwen 为 thinking 模式，``content`` 同时含 ThinkingBlock 与 TextBlock，
    此处只拼接 text 类型块的内容。
    """
    parts: list[str] = []
    for block in response.get("content", []) or []:
        # block 可能是 pydantic 块对象或 dict，统一按属性/键取值。
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if block_type == "text":
            text = getattr(block, "text", None) or (
                block.get("text") if isinstance(block, dict) else None
            )
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def render_section_material(section: RawSection) -> str:
    """把一个节的多来源素材渲染为带来源标注的文本，供 LLM 研判 / 提取。

    每个来源块标注文件类型与文件名，便于模型按可靠度（docx > pptx > txt）取舍。
    """
    blocks = [f"案例：{section.case_name}\n章节：{section.section_name}"]
    for parsed in section.files:
        if parsed.is_empty:
            continue
        label = _TYPE_LABEL.get(parsed.file_type, parsed.file_type.value)
        blocks.append(
            f"===== 来源：{label} ｜ 文件：{parsed.filename} =====\n{parsed.text}"
        )
    return "\n\n".join(blocks)
