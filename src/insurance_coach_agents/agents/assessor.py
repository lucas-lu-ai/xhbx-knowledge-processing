"""AssessorAgent：研判素材是否值得入库，并给出理由与价值评级。

单轮调用，使用 ``generate_structured_output`` 强制输出 ``Assessment`` 结构。
"""

from __future__ import annotations

from agentscope.message import SystemMsg, UserMsg
from agentscope.model import OpenAIChatModel

from ..models import Assessment, RawSection
from .cleanup import clean_reason
from .factory import STRUCTURED_TOOL_CHOICE, render_section_material
from .prompts import ASSESSOR_SYSTEM_PROMPT


class AssessorAgent:
    """知识研判智能体。"""

    def __init__(self, model: OpenAIChatModel) -> None:
        self._model = model

    async def assess(self, section: RawSection) -> Assessment:
        """对一个节做研判，返回结构化结论。"""
        material = render_section_material(section)
        messages = [
            SystemMsg(name="system", content=ASSESSOR_SYSTEM_PROMPT),
            UserMsg(name="user", content=material),
        ]
        response = await self._model.generate_structured_output(
            messages,
            structured_model=Assessment,
            tool_choice=STRUCTURED_TOOL_CHOICE,
        )
        content = dict(response.content)
        content["reason"] = clean_reason(str(content.get("reason", "")))
        return Assessment(**content)
