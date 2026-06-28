"""案例级销售策略 / 话术洞察编排。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agentscope.model import OpenAIChatModel

from .agents import CaseSalesInsightAgent, ImageDescriber, SectionSalesEvidenceAgent
from .agents.enrich import enrich_section_with_vision
from .config import OUTPUT_DIR
from .models import CaseSalesInsights, SalesEvidenceRef, SectionSalesEvidence
from .parsers.grouping import SourceGroup, load_group
from .pipeline import IMAGE_CACHE_DIRNAME
from .sales_output_writer import (
    write_case_sales_insights,
    write_section_sales_evidence,
)


_NATURAL_SORT_NUMBER = re.compile(r"(\d+)")


@dataclass(frozen=True)
class CaseSalesInsightResult:
    """案例级销售洞察处理结果。"""

    case_name: str
    status: str
    evidence_paths: tuple[str, ...] = ()
    insights_path: str | None = None
    playbook_path: str | None = None
    error: str | None = None


def _natural_sort_key(value: str) -> tuple[tuple[int, str | int], ...]:
    """按文本中的阿拉伯数字自然排序，如 第2节 排在 第10节 前。"""
    key: list[tuple[int, str | int]] = []
    for part in _NATURAL_SORT_NUMBER.split(value):
        if not part:
            continue
        if part.isdigit():
            key.append((1, int(part)))
        else:
            key.append((0, part.casefold()))
    return tuple(key)


def _case_groups(case_name: str, groups: list[SourceGroup]) -> list[SourceGroup]:
    """从全部知识单元中过滤并稳定排序某个案例的节。"""
    return sorted(
        [group for group in groups if group.case_name == case_name],
        key=lambda group: _natural_sort_key(group.identifier),
    )


def _has_sales_evidence(evidence: SectionSalesEvidence) -> bool:
    """判断节级结果是否包含可用于案例归纳的销售证据。"""
    return bool(
        evidence.customer_signals
        or evidence.sales_actions
        or evidence.script_quotes
        or evidence.objections
        or evidence.strategy_candidates
    )


def _has_meaningful_evidence_ref(ref: SalesEvidenceRef) -> bool:
    """判断来源引用是否包含至少一个非空定位字段。"""
    return any(
        getattr(ref, field_name).strip()
        for field_name in ("section_name", "source_id", "filename", "quote")
    )


def _evidence_has_source_refs(evidences: list[SectionSalesEvidence]) -> bool:
    """判断任一节级证据条目是否带有来源引用。"""
    for evidence in evidences:
        items = (
            *evidence.customer_signals,
            *evidence.sales_actions,
            *evidence.script_quotes,
            *evidence.objections,
            *evidence.strategy_candidates,
        )
        if any(
            _has_meaningful_evidence_ref(ref)
            for item in items
            for ref in item.source_refs
        ):
            return True
    return False


def _case_insights_have_evidence_refs(insights: CaseSalesInsights) -> bool:
    """当输入有 source_refs 时，案例级每个条目都必须保留 evidence_refs。"""
    items = (
        *insights.customer_journey,
        *insights.strategies,
        *insights.scripts,
        *insights.objection_handling,
    )
    return all(
        any(_has_meaningful_evidence_ref(ref) for ref in item.evidence_refs)
        for item in items
    )


async def run_case_sales_insights(
    case_name: str,
    groups: list[SourceGroup],
    model: OpenAIChatModel,
    output_dir: Path = OUTPUT_DIR,
    vision: bool = True,
    vision_model: OpenAIChatModel | None = None,
) -> CaseSalesInsightResult:
    """对一个完整案例提取销售证据与案例级销售洞察。"""
    selected = _case_groups(case_name, groups)
    if not selected:
        return CaseSalesInsightResult(
            case_name=case_name,
            status="failed",
            error=f"未找到案例: {case_name}",
        )

    evidence_paths: list[str] = []
    evidences = []
    try:
        evidence_agent = SectionSalesEvidenceAgent(model)
        case_agent = CaseSalesInsightAgent(model)
        describer = (
            ImageDescriber(
                vision_model or model,
                cache_dir=output_dir / IMAGE_CACHE_DIRNAME,
            )
            if vision
            else None
        )

        for group in selected:
            section = load_group(group)
            if describer is not None:
                section = await enrich_section_with_vision(
                    section,
                    group.file_paths,
                    describer,
                )
            if not section.primary_text:
                continue
            evidence = await evidence_agent.extract(section)
            evidence = evidence.model_copy(
                update={
                    "case_name": section.case_name,
                    "section_name": section.section_name,
                }
            )
            if not _has_sales_evidence(evidence):
                continue
            evidences.append(evidence)
            evidence_paths.append(
                str(write_section_sales_evidence(evidence, output_dir=output_dir))
            )

        if not evidences:
            return CaseSalesInsightResult(
                case_name=case_name,
                status="failed",
                error=f"案例无可解析销售证据: {case_name}",
            )

        insights = await case_agent.extract(case_name, evidences)
        insights = insights.model_copy(update={"case_name": case_name})
        if _evidence_has_source_refs(evidences) and not _case_insights_have_evidence_refs(
            insights
        ):
            return CaseSalesInsightResult(
                case_name=case_name,
                status="failed",
                evidence_paths=tuple(evidence_paths),
                error=(
                    "案例级销售洞察缺少 evidence_refs：输入节级证据包含 "
                    "source_refs，customer_journey、strategies、scripts、"
                    "objection_handling 中每一项都必须保留来源依据。"
                ),
            )
        write_result = write_case_sales_insights(insights, output_dir=output_dir)
        return CaseSalesInsightResult(
            case_name=case_name,
            status="ok",
            evidence_paths=tuple(evidence_paths),
            insights_path=str(write_result.insights_path),
            playbook_path=str(write_result.playbook_path),
        )
    except Exception as exc:  # noqa: BLE001 - 案例级失败隔离
        return CaseSalesInsightResult(
            case_name=case_name,
            status="failed",
            evidence_paths=tuple(evidence_paths),
            error=repr(exc),
        )
