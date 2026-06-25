"""ReviewerAgent：对提取稿做质检（规范性 + 信息保真）。

单轮调用，使用 ``generate_structured_output`` 强制输出 ``ReviewResult``。
把原始素材与整理稿一并交给模型对比审计，产出可审计的质检结论。
"""

from __future__ import annotations

from agentscope.message import SystemMsg, UserMsg
from agentscope.model import OpenAIChatModel

from ..models import ExtractedDoc, RawSection, ReviewResult
from .factory import render_section_material
from .prompts import REVIEWER_SYSTEM_PROMPT


class ReviewerAgent:
    """知识质检智能体。"""

    def __init__(self, model: OpenAIChatModel) -> None:
        self._model = model

    async def review(
        self, section: RawSection, doc: ExtractedDoc
    ) -> ReviewResult:
        """对一篇整理稿做质检，返回结构化质检结论。"""
        material = render_section_material(section)
        user = (
            f"【原始素材】\n{material}\n\n"
            f"【待质检的整理稿】\n{doc.body_markdown}"
        )
        messages = [
            SystemMsg(name="system", content=REVIEWER_SYSTEM_PROMPT),
            UserMsg(name="user", content=user),
        ]
        response = await self._model.generate_structured_output(
            messages, structured_model=ReviewResult
        )
        return ReviewResult(**dict(response.content))
