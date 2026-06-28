"""销售策略 / 话术洞察产物写入。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import OUTPUT_DIR
from .models import CaseSalesInsights, SalesEvidenceRef, SectionSalesEvidence
from .output_writer import _atomic_write_text, _safe_name


@dataclass(frozen=True)
class CaseSalesWriteResult:
    """案例级销售洞察写入结果。"""

    insights_path: Path
    playbook_path: Path


def write_section_sales_evidence(
    evidence: SectionSalesEvidence, output_dir: Path = OUTPUT_DIR
) -> Path:
    """写出单节销售证据 JSON sidecar。"""
    case_dir = output_dir / _safe_name(evidence.case_name)
    case_dir.mkdir(parents=True, exist_ok=True)
    path = case_dir / f"{_safe_name(evidence.section_name)}.sales_evidence.json"
    _atomic_write_text(
        path,
        json.dumps(evidence.model_dump(), ensure_ascii=False, indent=2),
    )
    return path


def _render_list(items: list[str]) -> str:
    if not items:
        return "- 无"
    return "\n".join(f"- {item}" for item in items)


def _render_evidence_refs(refs: list[SalesEvidenceRef]) -> list[str]:
    if not refs:
        return []
    lines = ["- 来源依据:"]
    for ref in refs:
        location_parts = [
            part
            for part in (ref.section_name, ref.filename or ref.source_id)
            if part
        ]
        location = " / ".join(location_parts) or "未标注来源"
        quote = f"：{ref.quote}" if ref.quote else ""
        lines.append(f"  - {location}{quote}")
    return lines


def _render_case_playbook(insights: CaseSalesInsights) -> str:
    lines = [
        f"# {insights.case_name} - 销售洞察手册",
        "",
        "## 案例概览",
        insights.case_summary,
        "",
        "## 客户旅程",
    ]
    if insights.customer_journey:
        for step in insights.customer_journey:
            lines.extend(
                [
                    f"### {step.stage}",
                    f"- 客户状态: {step.customer_state}",
                    f"- 销售目标: {step.sales_goal}",
                    "- 关键动作:",
                    _render_list(step.key_actions),
                ]
            )
            lines.extend(_render_evidence_refs(step.evidence_refs))
            lines.append("")
    else:
        lines.extend(["无", ""])

    lines.append("## 销售策略")
    if insights.strategies:
        for strategy in insights.strategies:
            lines.extend(
                [
                    f"### {strategy.name}",
                    f"- 定义: {strategy.definition}",
                    f"- 适用阶段: {'、'.join(strategy.applicable_stages) or '未标注'}",
                    f"- 置信度: {strategy.confidence}",
                    f"- 模型归纳: {'是' if strategy.inferred else '否'}",
                    "- 步骤:",
                    _render_list(strategy.steps),
                    "- 建议做法:",
                    _render_list(strategy.do),
                    "- 避免做法:",
                    _render_list(strategy.dont),
                ]
            )
            lines.extend(_render_evidence_refs(strategy.evidence_refs))
            lines.append("")
    else:
        lines.extend(["无", ""])

    lines.append("## 场景话术")
    if insights.scripts:
        for script in insights.scripts:
            lines.extend(
                [
                    f"### {script.script_id} - {script.scenario}",
                    f"- 阶段: {script.stage}",
                    f"- 客户触发点: {script.customer_trigger}",
                    f"- 目标: {script.goal}",
                    f"- 原始话术: {script.source_quote}",
                    f"- 教练推荐话术: {script.coach_wording}",
                    f"- 关联策略: {'、'.join(script.strategy_names) or '未标注'}",
                    "- 追问建议:",
                    _render_list(script.follow_up_questions),
                    "- 合规提醒:",
                    _render_list(script.compliance_notes),
                ]
            )
            lines.extend(_render_evidence_refs(script.evidence_refs))
            lines.append("")
    else:
        lines.extend(["无", ""])

    lines.append("## 异议处理")
    if insights.objection_handling:
        for item in insights.objection_handling:
            lines.extend(
                [
                    f"### {item.objection}",
                    f"- 异议诊断: {item.diagnosis}",
                    f"- 推荐回应: {item.recommended_response}",
                    f"- 关联策略: {'、'.join(item.related_strategy_names) or '未标注'}",
                    f"- 关联话术: {'、'.join(item.related_script_ids) or '未标注'}",
                ]
            )
            lines.extend(_render_evidence_refs(item.evidence_refs))
            lines.append("")
    else:
        lines.extend(["无", ""])
    return "\n".join(lines).rstrip() + "\n"


def write_case_sales_insights(
    insights: CaseSalesInsights, output_dir: Path = OUTPUT_DIR
) -> CaseSalesWriteResult:
    """写出案例级销售洞察 JSON 和人工审阅 Markdown。"""
    case_dir = output_dir / _safe_name(insights.case_name)
    case_dir.mkdir(parents=True, exist_ok=True)
    insights_path = case_dir / "case.sales_insights.json"
    playbook_path = case_dir / "case.sales_playbook.md"
    _atomic_write_text(
        insights_path,
        json.dumps(insights.model_dump(), ensure_ascii=False, indent=2),
    )
    _atomic_write_text(playbook_path, _render_case_playbook(insights))
    return CaseSalesWriteResult(
        insights_path=insights_path,
        playbook_path=playbook_path,
    )
