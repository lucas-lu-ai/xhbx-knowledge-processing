"""ExtractorAgent：把素材整理为标准化 Markdown 知识单元。

单轮调用，输出纯 Markdown 正文；标题从正文首个一级标题提取。
"""

from __future__ import annotations

import re

from agentscope.message import SystemMsg, UserMsg
from agentscope.model import OpenAIChatModel

from ..models import ExtractedDoc, RawSection
from .cleanup import clean_markdown_body
from .factory import render_section_material, response_text
from .prompts import EXTRACTOR_SYSTEM_PROMPT

_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _extract_title(markdown: str, fallback: str) -> str:
    """取正文首个一级标题作为标题，缺失则回退到节名。"""
    match = _H1_RE.search(markdown)
    return match.group(1).strip() if match else fallback


class ExtractorAgent:
    """知识整理智能体。"""

    def __init__(self, model: OpenAIChatModel) -> None:
        self._model = model

    async def extract(self, section: RawSection) -> ExtractedDoc:
        """把一个节整理为标准化 Markdown 知识单元。"""
        material = render_section_material(section)
        messages = [
            SystemMsg(name="system", content=EXTRACTOR_SYSTEM_PROMPT),
            UserMsg(name="user", content=material),
        ]
        response = await self._model(messages)
        body = clean_markdown_body(response_text(response))
        title = _extract_title(body, fallback=section.section_name)
        return ExtractedDoc(title=title, body_markdown=body)
