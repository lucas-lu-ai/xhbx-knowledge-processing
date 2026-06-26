"""ReviserAgent：根据质检问题返修提取稿。"""

from __future__ import annotations

from agentscope.message import SystemMsg, UserMsg
from agentscope.model import OpenAIChatModel

from ..models import ExtractedDoc, RawSection, ReviewResult
from .cleanup import clean_markdown_body
from .extractor import _extract_title
from .factory import render_section_material, response_text
from .prompts import REVISER_SYSTEM_PROMPT


class ReviserAgent:
    """知识返修智能体。"""

    def __init__(self, model: OpenAIChatModel) -> None:
        self._model = model

    async def revise(
        self, section: RawSection, doc: ExtractedDoc, review: ReviewResult
    ) -> ExtractedDoc:
        """根据质检问题返修一篇整理稿，返回完整 Markdown 正文。"""
        material = render_section_material(section)
        issues = "\n".join(f"- {issue}" for issue in review.issues) or "- 未列出问题"
        user = (
            f"【原始素材】\n{material}\n\n"
            f"【当前整理稿】\n{doc.body_markdown}\n\n"
            f"【质检问题列表】\n{issues}"
        )
        messages = [
            SystemMsg(name="system", content=REVISER_SYSTEM_PROMPT),
            UserMsg(name="user", content=user),
        ]
        response = await self._model(messages)
        body = clean_markdown_body(response_text(response))
        title = _extract_title(body, fallback=doc.title or section.section_name)
        return ExtractedDoc(title=title, body_markdown=body)
