"""销售策略/话术提取的数据契约测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from insurance_coach_agents.models import (
    CaseSalesInsights,
    CaseSalesScript,
    CustomerJourneyStep,
    SalesEvidenceRef,
    SectionSalesEvidence,
    StrategyCandidate,
)


def test_section_sales_evidence_accepts_structured_lists():
    evidence = SectionSalesEvidence(
        case_name="案例A",
        section_name="第1节",
        customer_signals=[
            {
                "signal": "客户保障意识弱",
                "evidence": "客户说暂时不需要保险",
                "source_refs": [{"section_name": "第1节", "quote": "暂时不需要"}],
            }
        ],
        sales_actions=[
            {
                "action": "用家庭责任引导风险意识",
                "stage_hint": "售前",
                "evidence": "销售人员继续追问家庭责任",
                "source_refs": [],
            }
        ],
        script_quotes=[
            {
                "quote": "您现在最担心家庭哪方面风险？",
                "speaker": "sales",
                "stage_hint": "售前",
                "scenario_hint": "风险唤醒",
                "source_refs": [],
            }
        ],
        objections=[],
        strategy_candidates=[
            {
                "name": "风险唤醒",
                "reason": "围绕家庭责任和风险缺口展开",
                "confidence": "mid",
                "inferred": True,
                "source_refs": [],
            }
        ],
    )

    assert evidence.case_name == "案例A"
    assert evidence.customer_signals[0].signal == "客户保障意识弱"
    assert evidence.script_quotes[0].speaker == "sales"
    assert isinstance(evidence.strategy_candidates[0], StrategyCandidate)


def test_section_sales_evidence_coerces_json_string_lists():
    evidence = SectionSalesEvidence(
        case_name="案例A",
        section_name="第1节",
        customer_signals='[{"signal":"预算有限","evidence":"客户担心保费","source_refs":[]}]',
        sales_actions="[]",
        script_quotes="[]",
        objections="[]",
        strategy_candidates="[]",
    )

    assert evidence.customer_signals[0].signal == "预算有限"
    assert evidence.sales_actions == []


def test_section_sales_evidence_wraps_raw_dict_as_single_nested_item():
    evidence = SectionSalesEvidence(
        case_name="案例A",
        section_name="第1节",
        customer_signals={
            "signal": "客户已有预算顾虑",
            "evidence": "客户直接询问保费压力",
            "source_refs": [],
        },
    )

    assert len(evidence.customer_signals) == 1
    assert evidence.customer_signals[0].signal == "客户已有预算顾虑"


def test_section_sales_evidence_rejects_malformed_string_lists():
    with pytest.raises(ValidationError):
        SectionSalesEvidence(
            case_name="案例A",
            section_name="第1节",
            customer_signals="not valid json",
        )


def test_sales_evidence_ref_rejects_unexpected_provenance_fields():
    with pytest.raises(ValidationError):
        SalesEvidenceRef(
            section_name="第1节",
            quote="暂时不需要",
            anchor_id="paragraph-1",
        )


def test_case_sales_insights_accepts_journey_strategy_scripts_and_objections():
    insights = CaseSalesInsights(
        case_name="案例A",
        case_summary="完整案例围绕风险唤醒和需求面谈展开。",
        customer_journey=[
            {
                "stage": "售前",
                "customer_state": "保障意识弱",
                "sales_goal": "引发风险关注",
                "key_actions": ["场景提问", "家庭责任引导"],
                "evidence_refs": [],
            }
        ],
        strategies=[
            {
                "name": "风险唤醒式需求面谈",
                "aliases": ["风险唤醒"],
                "definition": "通过生活场景和家庭责任引导客户意识到保障缺口。",
                "applicable_stages": ["售前", "需求面谈"],
                "steps": ["场景切入", "风险追问", "缺口确认"],
                "do": ["先接纳客户现状"],
                "dont": ["不要承诺收益或理赔结果"],
                "confidence": "high",
                "inferred": True,
                "evidence_refs": [],
            }
        ],
        scripts=[
            {
                "script_id": "script_001",
                "stage": "售前",
                "scenario": "客户保险意识弱",
                "customer_trigger": "客户认为现在不需要保险",
                "goal": "吸引客户进入需求沟通",
                "source_quote": "原始话术",
                "coach_wording": "教练推荐话术",
                "strategy_names": ["风险唤醒式需求面谈"],
                "follow_up_questions": ["您现在最担心家庭哪方面风险？"],
                "compliance_notes": ["不得承诺收益、理赔结果或夸大保障范围"],
                "evidence_refs": [],
            }
        ],
        objection_handling=[
            {
                "objection": "我现在不需要保险",
                "diagnosis": "客户未感知风险",
                "recommended_response": "先接纳，再用家庭责任引导。",
                "related_strategy_names": ["风险唤醒式需求面谈"],
                "related_script_ids": ["script_001"],
                "evidence_refs": [],
            }
        ],
    )

    assert isinstance(insights.customer_journey[0], CustomerJourneyStep)
    assert isinstance(insights.scripts[0], CaseSalesScript)
    assert insights.scripts[0].script_id == "script_001"


def test_case_sales_script_defaults_empty_compliance_notes_to_conservative_note():
    script = CaseSalesScript(
        script_id="script_001",
        stage="售前",
        scenario="客户保险意识弱",
        customer_trigger="客户认为现在不需要保险",
        goal="吸引客户进入需求沟通",
        source_quote="原始话术",
        coach_wording="教练推荐话术",
        strategy_names=["风险唤醒式需求面谈"],
        follow_up_questions=["您现在最担心家庭哪方面风险？"],
        compliance_notes=[],
        evidence_refs=[],
    )

    assert script.compliance_notes == [
        "未识别到特定合规风险，仍需以公司合规要求和正式条款为准。"
    ]
