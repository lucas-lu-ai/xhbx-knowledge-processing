"""模型构造与响应工具。

集中负责用第三方 OpenAI 兼容平台（mixroute.ai）的凭证构造 ``OpenAIChatModel``，
并提供从 ``ChatResponse`` 中提取纯文本（过滤 thinking 块）的辅助函数。
"""

from __future__ import annotations

from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.model import ChatResponse, OpenAIChatModel

from ..config import ModelSettings, load_model_settings
from ..models import FileType, RawSection

_TYPE_LABEL = {
    FileType.DOCX: "docx 讲义（人工整理，主干）",
    FileType.PPTX: "pptx 课件（框架要点）",
    FileType.PDF: "pdf 资料",
    FileType.TXT: "txt 音频转写稿（口语化）",
}


def build_chat_model(settings: ModelSettings | None = None) -> OpenAIChatModel:
    """构造指向第三方平台的 ``OpenAIChatModel``。

    使用 OpenAI 风格的凭证与 base_url（而非 DashScope 类），以适配 mixroute.ai。
    ``stream=False`` 以便一次性拿到完整响应，简化下游处理。
    """
    settings = settings or load_model_settings()
    credential = OpenAICredential(
        api_key=settings.api_key, base_url=settings.base_url
    )
    return OpenAIChatModel(
        credential=credential,
        model=settings.model_name,
        formatter=OpenAIChatFormatter(),
        stream=False,
    )


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
