"""sales-insights CLI 辅助逻辑测试。"""

from __future__ import annotations

from pathlib import Path

from insurance_coach_agents.cli import _select_case_names, main
from insurance_coach_agents.parsers.grouping import SourceGroup


def _group(case_name: str, unit_name: str) -> SourceGroup:
    return SourceGroup(
        case_name=case_name,
        unit_name=unit_name,
        identifier=f"{case_name}/{unit_name}",
        file_paths=(Path(f"{case_name}/{unit_name}/讲义.txt"),),
    )


def test_select_case_names_returns_explicit_case_when_present():
    groups = [_group("案例A", "第1节"), _group("案例B", "第1节")]

    assert _select_case_names(groups, case_name="案例B", all_cases=False) == ["案例B"]


def test_select_case_names_returns_all_cases_sorted():
    groups = [_group("案例B", "第1节"), _group("案例A", "第1节")]

    assert _select_case_names(groups, case_name=None, all_cases=True) == [
        "案例A",
        "案例B",
    ]


def test_select_case_names_raises_when_all_cases_has_explicit_case():
    groups = [_group("案例A", "第1节"), _group("案例B", "第1节")]

    try:
        _select_case_names(groups, case_name="案例A", all_cases=True)
    except ValueError as exc:
        assert "--all 不能同时指定案例名称" in str(exc)
    else:
        raise AssertionError("--all with explicit case should raise ValueError")


def test_select_case_names_raises_when_all_cases_has_no_available_cases():
    try:
        _select_case_names([], case_name=None, all_cases=True)
    except ValueError as exc:
        assert "未发现任何案例素材" in str(exc)
    else:
        raise AssertionError("--all with no cases should raise ValueError")


def test_select_case_names_raises_for_missing_case():
    groups = [_group("案例A", "第1节")]

    try:
        _select_case_names(groups, case_name="案例X", all_cases=False)
    except ValueError as exc:
        assert "未找到案例" in str(exc)
    else:
        raise AssertionError("missing case should raise ValueError")


def test_sales_insights_help_shows_command_description(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv", ["insurance-coach-md", "sales-insights", "--help"]
    )

    try:
        main()
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("help should exit")

    assert "按完整案例提取销售策略、销售话术和异议处理洞察" in capsys.readouterr().out
