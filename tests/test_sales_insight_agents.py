"""销售洞察 agent 测试，使用 fake model，不调用真实 API。"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from insurance_coach_agents.agents import (
    CaseSalesInsightAgent,
    SectionSalesEvidenceAgent,
)
from insurance_coach_agents.agents.prompts import CASE_SALES_INSIGHT_SYSTEM_PROMPT
from insurance_coach_agents.models import (
    CaseSalesInsights,
    FileType,
    ParsedFile,
    RawSection,
    SectionSalesEvidence,
)


class _FakeStructured:
    def __init__(self, content: dict) -> None:
        self.content = content


class _FakeSalesModel:
    def __init__(
        self,
        section_content: dict | None = None,
        case_content: dict | None = None,
    ) -> None:
        self._section_content = section_content
        self._case_content = case_content
        self.user_materials: list[str] = []

    async def generate_structured_output(
        self, messages, structured_model, tool_choice=None
    ):
        self.user_materials.append(str(getattr(messages[-1], "content", "")))
        if structured_model.__name__ == "SectionSalesEvidence":
            return _FakeStructured(self._section_content or _section_evidence_content())
        return _FakeStructured(self._case_content or _case_insights_content())


def _section_evidence_content(**updates) -> dict:
    content = {
        "case_name": "案例A",
        "section_name": "第1节",
        "customer_signals": [
            {
                "signal": "客户保障意识弱",
                "evidence": "客户说暂时不需要保险",
                "source_refs": [
                    {
                        "section_name": "第1节",
                        "filename": "讲义.txt",
                        "quote": "暂时不需要保险",
                    }
                ],
            }
        ],
        "sales_actions": [],
        "script_quotes": [
            {
                "quote": "您现在最担心家庭哪方面风险？",
                "speaker": "sales",
                "stage_hint": "售前",
                "scenario_hint": "风险唤醒",
                "source_refs": [],
            }
        ],
        "objections": [],
        "strategy_candidates": [
            {
                "name": "风险唤醒",
                "reason": "围绕家庭责任展开追问",
                "confidence": "high",
                "inferred": True,
                "source_refs": [],
            }
        ],
    }
    content.update(updates)
    return content


def _case_insights_content(**updates) -> dict:
    content = {
        "case_name": "案例A",
        "case_summary": "案例围绕风险唤醒展开。",
        "customer_journey": [
            {
                "stage": "售前",
                "customer_state": "保障意识弱",
                "sales_goal": "引发风险关注",
                "key_actions": ["场景提问"],
                "evidence_refs": [],
            }
        ],
        "strategies": [
            {
                "name": "风险唤醒式需求面谈",
                "aliases": ["风险唤醒"],
                "definition": "通过家庭责任引导客户看到保障缺口。",
                "applicable_stages": ["售前"],
                "steps": ["场景切入", "风险追问"],
                "do": ["先接纳客户现状"],
                "dont": ["不要承诺收益"],
                "confidence": "high",
                "inferred": True,
                "evidence_refs": [],
            }
        ],
        "scripts": [
            {
                "script_id": "script_001",
                "stage": "售前",
                "scenario": "客户保险意识弱",
                "customer_trigger": "客户认为现在不需要保险",
                "goal": "吸引客户进入需求沟通",
                "source_quote": "您现在最担心家庭哪方面风险？",
                "coach_wording": "可以先从家庭责任切入，询问客户最担心的风险。",
                "strategy_names": ["风险唤醒式需求面谈"],
                "follow_up_questions": ["如果风险发生，会先影响谁？"],
                "compliance_notes": ["不得承诺收益或理赔结果"],
                "evidence_refs": [],
            }
        ],
        "objection_handling": [],
    }
    content.update(updates)
    return content


def _section() -> RawSection:
    return RawSection(
        case_name="案例A",
        section_name="第1节",
        section_dir="案例A/第1节",
        files=(
            ParsedFile(
                file_type=FileType.TXT,
                filename="讲义.txt",
                text="客户：暂时不需要保险。销售：您现在最担心家庭哪方面风险？",
            ),
        ),
    )


def test_section_sales_evidence_agent_returns_structured_evidence():
    model = _FakeSalesModel()
    evidence = asyncio.run(SectionSalesEvidenceAgent(model).extract(_section()))

    assert isinstance(evidence, SectionSalesEvidence)
    assert evidence.case_name == "案例A"
    assert evidence.customer_signals[0].signal == "客户保障意识弱"
    assert evidence.script_quotes[0].quote.startswith("您现在")
    assert "案例：案例A" in model.user_materials[0]
    assert "讲义.txt" in model.user_materials[0]


def test_case_sales_insight_agent_receives_all_section_evidence():
    model = _FakeSalesModel()
    evidence = SectionSalesEvidenceAgent(model)
    first = asyncio.run(evidence.extract(_section()))
    second = first.model_copy(update={"section_name": "第2节"})

    insights = asyncio.run(
        CaseSalesInsightAgent(model).extract("案例A", [first, second])
    )

    assert isinstance(insights, CaseSalesInsights)
    assert insights.case_name == "案例A"
    assert insights.strategies[0].name == "风险唤醒式需求面谈"
    assert insights.scripts[0].script_id == "script_001"
    assert "第1节" in model.user_materials[-1]
    assert "第2节" in model.user_materials[-1]


def test_section_sales_evidence_agent_fills_blank_or_missing_identity_fields():
    section_content = _section_evidence_content(case_name=" ", section_name=None)
    section_content.pop("section_name")
    model = _FakeSalesModel(section_content=section_content)

    evidence = asyncio.run(SectionSalesEvidenceAgent(model).extract(_section()))

    assert evidence.case_name == "案例A"
    assert evidence.section_name == "第1节"


def test_case_sales_insight_agent_fills_blank_case_name():
    first = SectionSalesEvidence(**_section_evidence_content())
    model = _FakeSalesModel(case_content=_case_insights_content(case_name=""))

    insights = asyncio.run(CaseSalesInsightAgent(model).extract("案例A", [first]))

    assert insights.case_name == "案例A"


def test_sales_insight_agents_reject_malformed_identity_fields():
    model = _FakeSalesModel(section_content=_section_evidence_content(case_name=["bad"]))

    with pytest.raises(ValidationError):
        asyncio.run(SectionSalesEvidenceAgent(model).extract(_section()))


def test_case_sales_insight_prompt_requires_evidence_refs_traceability():
    prompt = CASE_SALES_INSIGHT_SYSTEM_PROMPT

    assert "evidence_refs" in prompt
    assert "source_refs" in prompt
    for field_name in (
        "customer_journey",
        "strategies",
        "scripts",
        "objection_handling",
    ):
        assert field_name in prompt
