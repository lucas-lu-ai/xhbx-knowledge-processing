"""销售洞察 sidecar 写入测试。"""

from __future__ import annotations

import json

from insurance_coach_agents.models import CaseSalesInsights, SectionSalesEvidence
from insurance_coach_agents.sales_output_writer import (
    write_case_sales_insights,
    write_section_sales_evidence,
)


def _evidence() -> SectionSalesEvidence:
    return SectionSalesEvidence(
        case_name="案例A",
        section_name="第1节",
        customer_signals=[],
        sales_actions=[],
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
        strategy_candidates=[],
    )


def _insights() -> CaseSalesInsights:
    return CaseSalesInsights(
        case_name="案例A",
        case_summary="案例围绕风险唤醒展开。",
        customer_journey=[
            {
                "stage": "售前",
                "customer_state": "保障意识弱",
                "sales_goal": "引发风险关注",
                "key_actions": ["场景提问"],
                "evidence_refs": [
                    {
                        "section_name": "第1节",
                        "filename": "讲义.txt",
                        "quote": "客户说暂时不需要保险",
                    }
                ],
            }
        ],
        strategies=[
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
                "evidence_refs": [
                    {
                        "section_name": "第1节",
                        "filename": "讲义.txt",
                        "quote": "家庭责任引导客户看到保障缺口",
                    }
                ],
            }
        ],
        scripts=[
            {
                "script_id": "script_001",
                "stage": "售前",
                "scenario": "客户保险意识弱",
                "customer_trigger": "客户认为现在不需要保险",
                "goal": "吸引客户进入需求沟通",
                "source_quote": "您现在最担心家庭哪方面风险？",
                "coach_wording": "可以先从家庭责任切入。",
                "strategy_names": ["风险唤醒式需求面谈"],
                "follow_up_questions": ["如果风险发生，会先影响谁？"],
                "compliance_notes": ["不得承诺收益或理赔结果"],
                "evidence_refs": [
                    {
                        "section_name": "第1节",
                        "filename": "讲义.txt",
                        "quote": "您现在最担心家庭哪方面风险？",
                    }
                ],
            }
        ],
        objection_handling=[
            {
                "objection": "我暂时没有预算",
                "diagnosis": "客户存在预算压力",
                "recommended_response": "先接纳预算顾虑，再澄清保障优先级。",
                "related_strategy_names": ["风险唤醒式需求面谈"],
                "related_script_ids": ["script_001"],
                "evidence_refs": [
                    {
                        "section_name": "第2节",
                        "filename": "讲义.txt",
                        "quote": "客户原话：我暂时没有预算",
                    }
                ],
            }
        ],
    )


def test_write_section_sales_evidence_creates_json_sidecar(tmp_path):
    path = write_section_sales_evidence(_evidence(), output_dir=tmp_path)

    assert path == tmp_path / "案例A" / "第1节.sales_evidence.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["case_name"] == "案例A"
    assert data["script_quotes"][0]["quote"].startswith("您现在")


def test_write_case_sales_insights_creates_json_and_playbook(tmp_path):
    result = write_case_sales_insights(_insights(), output_dir=tmp_path)

    assert result.insights_path == tmp_path / "案例A" / "case.sales_insights.json"
    assert result.playbook_path == tmp_path / "案例A" / "case.sales_playbook.md"
    data = json.loads(result.insights_path.read_text(encoding="utf-8"))
    assert data["strategies"][0]["name"] == "风险唤醒式需求面谈"
    playbook = result.playbook_path.read_text(encoding="utf-8")
    assert "# 案例A - 销售洞察手册" in playbook
    assert "## 销售策略" in playbook
    assert "不得承诺收益或理赔结果" in playbook
    assert "来源依据" in playbook
    assert "客户说暂时不需要保险" in playbook
    assert "客户原话：我暂时没有预算" in playbook
