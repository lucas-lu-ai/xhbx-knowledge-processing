"""案例级销售洞察 pipeline 测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from insurance_coach_agents.parsers.grouping import group_by_directory
from insurance_coach_agents.sales_pipeline import run_case_sales_insights


class _FakeStructured:
    def __init__(self, content: dict) -> None:
        self.content = content


class _FakeSalesModel:
    def __init__(
        self,
        *,
        empty_evidence: bool = False,
        wrong_identity: bool = False,
        with_source_refs: bool = False,
        missing_case_evidence_refs: bool = False,
        blank_case_evidence_refs: bool = False,
    ) -> None:
        self.calls: list[str] = []
        self.section_calls: list[str] = []
        self.case_calls: list[str] = []
        self.empty_evidence = empty_evidence
        self.wrong_identity = wrong_identity
        self.with_source_refs = with_source_refs
        self.missing_case_evidence_refs = missing_case_evidence_refs
        self.blank_case_evidence_refs = blank_case_evidence_refs

    async def generate_structured_output(
        self, messages, structured_model, tool_choice=None
    ):
        user_content = str(getattr(messages[-1], "content", ""))
        self.calls.append(user_content)
        if structured_model.__name__ == "SectionSalesEvidence":
            self.section_calls.append(user_content)
            section_name = "第1节"
            for candidate in ("第10节", "第2节", "第1节"):
                if candidate in user_content:
                    section_name = candidate
                    break
            if self.empty_evidence:
                return _FakeStructured(
                    {
                        "case_name": "案例A",
                        "section_name": section_name,
                        "customer_signals": [],
                        "sales_actions": [],
                        "script_quotes": [],
                        "objections": [],
                        "strategy_candidates": [],
                    }
                )
            source_refs = (
                [
                    {
                        "section_name": section_name,
                        "filename": "讲义.txt",
                        "quote": f"{section_name}证据",
                    }
                ]
                if self.with_source_refs
                else []
            )
            return _FakeStructured(
                {
                    "case_name": "错误案例" if self.wrong_identity else "案例A",
                    "section_name": "错误节" if self.wrong_identity else section_name,
                    "customer_signals": [],
                    "sales_actions": [
                        {
                            "action": f"{section_name}销售动作",
                            "stage_hint": "售前",
                            "evidence": f"{section_name}证据",
                            "source_refs": source_refs,
                        }
                    ],
                    "script_quotes": [
                        {
                            "quote": f"{section_name}原始话术",
                            "speaker": "sales",
                            "stage_hint": "售前",
                            "scenario_hint": "测试场景",
                            "source_refs": source_refs,
                        }
                    ],
                    "objections": [],
                    "strategy_candidates": [],
                }
            )
        self.case_calls.append(user_content)
        if self.missing_case_evidence_refs:
            case_evidence_refs = []
        elif self.blank_case_evidence_refs:
            case_evidence_refs = [{}]
        elif self.with_source_refs:
            case_evidence_refs = [
                {
                    "section_name": "第1节",
                    "filename": "讲义.txt",
                    "quote": "第1节证据",
                }
            ]
        else:
            case_evidence_refs = []
        return _FakeStructured(
            {
                "case_name": "错误案例" if self.wrong_identity else "案例A",
                "case_summary": "整案销售洞察。",
                "customer_journey": [
                    {
                        "stage": "售前",
                        "customer_state": "保障意识弱",
                        "sales_goal": "建立风险意识",
                        "key_actions": ["第1节销售动作", "第2节销售动作"],
                        "evidence_refs": case_evidence_refs,
                    }
                ],
                "strategies": [
                    {
                        "name": "风险唤醒",
                        "aliases": [],
                        "definition": "用风险问题建立保障意识。",
                        "applicable_stages": ["售前"],
                        "steps": ["提问", "追问"],
                        "do": ["先接纳"],
                        "dont": ["不承诺收益"],
                        "confidence": "high",
                        "inferred": True,
                        "evidence_refs": case_evidence_refs,
                    }
                ],
                "scripts": [
                    {
                        "script_id": "script_001",
                        "stage": "售前",
                        "scenario": "测试场景",
                        "customer_trigger": "客户不想聊保险",
                        "goal": "打开话题",
                        "source_quote": "第1节原始话术",
                        "coach_wording": "教练推荐话术",
                        "strategy_names": ["风险唤醒"],
                        "follow_up_questions": [],
                        "compliance_notes": ["不承诺收益"],
                        "evidence_refs": case_evidence_refs,
                    }
                ],
                "objection_handling": [],
            }
        )


def _make_case(root: Path) -> list:
    first = root / "案例A" / "第1节"
    second = root / "案例A" / "第2节"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "讲义.txt").write_text("第1节：客户不想聊保险。", encoding="utf-8")
    (second / "讲义.txt").write_text("第2节：继续追问家庭责任。", encoding="utf-8")
    return group_by_directory(root)


def _make_mixed_cases(root: Path) -> list:
    a_first = root / "案例A" / "第1节"
    a_second = root / "案例A" / "第2节"
    b_first = root / "案例B" / "第1节"
    a_first.mkdir(parents=True)
    a_second.mkdir(parents=True)
    b_first.mkdir(parents=True)
    (a_first / "讲义.txt").write_text("第1节：客户不想聊保险。", encoding="utf-8")
    (a_second / "讲义.txt").write_text("第2节：继续追问家庭责任。", encoding="utf-8")
    (b_first / "讲义.txt").write_text("案例B第1节：其他案例。", encoding="utf-8")
    groups = group_by_directory(root)
    by_key = {(group.case_name, group.unit_name): group for group in groups}
    return [
        by_key[("案例B", "第1节")],
        by_key[("案例A", "第2节")],
        by_key[("案例A", "第1节")],
    ]


def _make_natural_sort_case(root: Path) -> list:
    first = root / "案例A" / "第1节"
    second = root / "案例A" / "第2节"
    tenth = root / "案例A" / "第10节"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    tenth.mkdir(parents=True)
    (first / "讲义.txt").write_text("第1节：客户不想聊保险。", encoding="utf-8")
    (second / "讲义.txt").write_text("第2节：继续追问家庭责任。", encoding="utf-8")
    (tenth / "讲义.txt").write_text("第10节：复盘促成话术。", encoding="utf-8")
    groups = group_by_directory(root)
    by_key = {(group.case_name, group.unit_name): group for group in groups}
    return [
        by_key[("案例A", "第10节")],
        by_key[("案例A", "第2节")],
        by_key[("案例A", "第1节")],
    ]


def test_run_case_sales_insights_writes_evidence_and_case_outputs(tmp_path):
    groups = _make_case(tmp_path / "cases")
    output = tmp_path / "output"
    model = _FakeSalesModel()

    result = asyncio.run(
        run_case_sales_insights(
            "案例A",
            groups,
            model,
            output_dir=output,
            vision=False,
        )
    )

    assert result.status == "ok"
    assert len(result.evidence_paths) == 2
    assert result.insights_path == str(output / "案例A" / "case.sales_insights.json")
    assert result.playbook_path == str(output / "案例A" / "case.sales_playbook.md")
    assert (output / "案例A" / "第1节.sales_evidence.json").exists()
    assert (output / "案例A" / "第2节.sales_evidence.json").exists()
    assert (output / "案例A" / "case.sales_playbook.md").exists()
    data = json.loads((output / "案例A" / "case.sales_insights.json").read_text())
    assert data["case_summary"] == "整案销售洞察。"
    assert data["strategies"][0]["name"] == "风险唤醒"
    assert "第1节" in model.calls[0]
    assert "第2节" in model.calls[1]
    assert "第1节销售动作" in model.calls[-1]
    assert "第2节销售动作" in model.calls[-1]


def test_run_case_sales_insights_routes_outputs_by_source_identity(tmp_path):
    groups = _make_case(tmp_path / "cases")
    output = tmp_path / "output"
    model = _FakeSalesModel(wrong_identity=True)

    result = asyncio.run(
        run_case_sales_insights(
            "案例A",
            groups,
            model,
            output_dir=output,
            vision=False,
        )
    )

    assert result.status == "ok"
    assert result.insights_path == str(output / "案例A" / "case.sales_insights.json")
    assert result.evidence_paths == (
        str(output / "案例A" / "第1节.sales_evidence.json"),
        str(output / "案例A" / "第2节.sales_evidence.json"),
    )
    assert not (output / "错误案例").exists()
    first = json.loads(
        (output / "案例A" / "第1节.sales_evidence.json").read_text(encoding="utf-8")
    )
    insights = json.loads(
        (output / "案例A" / "case.sales_insights.json").read_text(encoding="utf-8")
    )
    assert first["case_name"] == "案例A"
    assert first["section_name"] == "第1节"
    assert insights["case_name"] == "案例A"


def test_run_case_sales_insights_fails_when_source_refs_do_not_propagate(tmp_path):
    groups = _make_case(tmp_path / "cases")
    output = tmp_path / "output"
    model = _FakeSalesModel(
        with_source_refs=True,
        missing_case_evidence_refs=True,
    )

    result = asyncio.run(
        run_case_sales_insights(
            "案例A",
            groups,
            model,
            output_dir=output,
            vision=False,
        )
    )

    assert result.status == "failed"
    assert len(result.evidence_paths) == 2
    assert "evidence_refs" in result.error
    assert (output / "案例A" / "第1节.sales_evidence.json").exists()
    assert not (output / "案例A" / "case.sales_insights.json").exists()
    assert not (output / "案例A" / "case.sales_playbook.md").exists()


def test_run_case_sales_insights_rejects_blank_case_evidence_refs(tmp_path):
    groups = _make_case(tmp_path / "cases")
    output = tmp_path / "output"
    model = _FakeSalesModel(
        with_source_refs=True,
        blank_case_evidence_refs=True,
    )

    result = asyncio.run(
        run_case_sales_insights(
            "案例A",
            groups,
            model,
            output_dir=output,
            vision=False,
        )
    )

    assert result.status == "failed"
    assert len(result.evidence_paths) == 2
    assert "evidence_refs" in result.error
    assert (output / "案例A" / "第1节.sales_evidence.json").exists()
    assert not (output / "案例A" / "case.sales_insights.json").exists()
    assert not (output / "案例A" / "case.sales_playbook.md").exists()


def test_run_case_sales_insights_succeeds_when_source_refs_propagate(tmp_path):
    groups = _make_case(tmp_path / "cases")
    output = tmp_path / "output"
    model = _FakeSalesModel(with_source_refs=True)

    result = asyncio.run(
        run_case_sales_insights(
            "案例A",
            groups,
            model,
            output_dir=output,
            vision=False,
        )
    )

    assert result.status == "ok"
    data = json.loads((output / "案例A" / "case.sales_insights.json").read_text())
    assert data["customer_journey"][0]["evidence_refs"][0]["quote"] == "第1节证据"
    assert data["strategies"][0]["evidence_refs"][0]["section_name"] == "第1节"


def test_run_case_sales_insights_fails_when_all_section_evidence_is_empty(tmp_path):
    groups = _make_case(tmp_path / "cases")
    output = tmp_path / "output"
    model = _FakeSalesModel(empty_evidence=True)

    result = asyncio.run(
        run_case_sales_insights(
            "案例A",
            groups,
            model,
            output_dir=output,
            vision=False,
        )
    )

    assert result.status == "failed"
    assert result.evidence_paths == ()
    assert "案例无可解析销售证据" in result.error
    assert not (output / "案例A" / "第1节.sales_evidence.json").exists()
    assert not (output / "案例A" / "第2节.sales_evidence.json").exists()
    assert not (output / "案例A" / "case.sales_insights.json").exists()
    assert model.case_calls == []


def test_run_case_sales_insights_filters_case_and_sorts_sections(tmp_path):
    groups = _make_mixed_cases(tmp_path / "cases")
    model = _FakeSalesModel()

    result = asyncio.run(
        run_case_sales_insights(
            "案例A",
            groups,
            model,
            output_dir=tmp_path / "output",
            vision=False,
        )
    )

    assert result.status == "ok"
    assert len(model.section_calls) == 2
    assert "第1节" in model.section_calls[0]
    assert "第2节" in model.section_calls[1]
    assert "案例B" not in "\n".join(model.section_calls)


def test_run_case_sales_insights_sorts_sections_by_embedded_numbers(tmp_path):
    groups = _make_natural_sort_case(tmp_path / "cases")
    model = _FakeSalesModel()

    result = asyncio.run(
        run_case_sales_insights(
            "案例A",
            groups,
            model,
            output_dir=tmp_path / "output",
            vision=False,
        )
    )

    assert result.status == "ok"
    assert len(model.section_calls) == 3
    assert "第1节" in model.section_calls[0]
    assert "第2节" in model.section_calls[1]
    assert "第10节" in model.section_calls[2]


def test_run_case_sales_insights_fails_when_case_has_no_groups(tmp_path):
    result = asyncio.run(
        run_case_sales_insights(
            "不存在案例",
            [],
            _FakeSalesModel(),
            output_dir=tmp_path / "output",
            vision=False,
        )
    )

    assert result.status == "failed"
    assert "未找到案例" in result.error


def test_run_case_sales_insights_fails_when_agent_constructor_raises(
    tmp_path, monkeypatch
):
    groups = _make_case(tmp_path / "cases")

    def _raise_constructor(_model):
        raise RuntimeError("constructor failed")

    monkeypatch.setattr(
        "insurance_coach_agents.sales_pipeline.SectionSalesEvidenceAgent",
        _raise_constructor,
    )

    result = asyncio.run(
        run_case_sales_insights(
            "案例A",
            groups,
            _FakeSalesModel(),
            output_dir=tmp_path / "output",
            vision=False,
        )
    )

    assert result.status == "failed"
    assert result.evidence_paths == ()
    assert "constructor failed" in result.error
