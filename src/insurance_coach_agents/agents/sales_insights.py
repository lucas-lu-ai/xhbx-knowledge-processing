"""销售策略 / 话术洞察智能体。"""

from __future__ import annotations

import json

from agentscope.message import SystemMsg, UserMsg
from agentscope.model import OpenAIChatModel

from ..models import CaseSalesInsights, RawSection, SectionSalesEvidence
from .factory import STRUCTURED_TOOL_CHOICE, render_section_material
from .prompts import (
    CASE_SALES_INSIGHT_SYSTEM_PROMPT,
    SECTION_SALES_EVIDENCE_SYSTEM_PROMPT,
)


_MISSING = object()


def _fill_blank_identity(content: dict, field: str, fallback: str) -> None:
    """只补齐缺失或空白身份字段，其他异常类型交给 Pydantic 校验。"""
    value = content.get(field, _MISSING)
    if value is _MISSING or value is None or (isinstance(value, str) and not value.strip()):
        content[field] = fallback


def render_case_sales_evidence(
    case_name: str, evidences: list[SectionSalesEvidence]
) -> str:
    """把同一案例下的节级销售证据渲染为模型可读文本。"""
    blocks = [f"案例：{case_name}", "以下是该案例下各章节的销售证据："]
    for evidence in evidences:
        blocks.append(
            "===== 章节："
            f"{evidence.section_name} =====\n"
            f"{json.dumps(evidence.model_dump(), ensure_ascii=False, indent=2)}"
        )
    return "\n\n".join(blocks)


class SectionSalesEvidenceAgent:
    """从单节素材采集销售策略/话术证据。"""

    def __init__(self, model: OpenAIChatModel) -> None:
        self._model = model

    async def extract(self, section: RawSection) -> SectionSalesEvidence:
        material = render_section_material(section)
        messages = [
            SystemMsg(name="system", content=SECTION_SALES_EVIDENCE_SYSTEM_PROMPT),
            UserMsg(name="user", content=material),
        ]
        response = await self._model.generate_structured_output(
            messages,
            structured_model=SectionSalesEvidence,
            tool_choice=STRUCTURED_TOOL_CHOICE,
        )
        content = dict(response.content)
        _fill_blank_identity(content, "case_name", section.case_name)
        _fill_blank_identity(content, "section_name", section.section_name)
        return SectionSalesEvidence(**content)


class CaseSalesInsightAgent:
    """整合同一案例的节级证据，生成案例级销售洞察。"""

    def __init__(self, model: OpenAIChatModel) -> None:
        self._model = model

    async def extract(
        self, case_name: str, evidences: list[SectionSalesEvidence]
    ) -> CaseSalesInsights:
        material = render_case_sales_evidence(case_name, evidences)
        messages = [
            SystemMsg(name="system", content=CASE_SALES_INSIGHT_SYSTEM_PROMPT),
            UserMsg(name="user", content=material),
        ]
        response = await self._model.generate_structured_output(
            messages,
            structured_model=CaseSalesInsights,
            tool_choice=STRUCTURED_TOOL_CHOICE,
        )
        content = dict(response.content)
        _fill_blank_identity(content, "case_name", case_name)
        return CaseSalesInsights(**content)
