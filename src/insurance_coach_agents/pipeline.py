"""全库批处理编排：分组 → 研判 → 提取 → 落盘 → 汇总 manifest。

异步并发（信号量限流）；单节失败隔离不中断全库；支持增量（跳过已产出）。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from agentscope.model import OpenAIChatModel

from .agents import AssessorAgent, ExtractorAgent
from .config import OUTPUT_DIR
from .output_writer import expected_markdown_path, write_section_output
from .parsers.grouping import SourceGroup, load_group

DEFAULT_CONCURRENCY = 4


@dataclass(frozen=True)
class SectionResult:
    """单节处理结果，用于汇总 manifest。"""

    case_name: str
    section_name: str
    identifier: str
    status: str  # "ok" | "skipped" | "failed"
    worth_storing: bool | None = None
    value_score: float | None = None
    topics: tuple[str, ...] = ()
    reason: str = ""
    markdown_path: str | None = None
    error: str | None = None


async def _process_group(
    group: SourceGroup,
    assessor: AssessorAgent,
    extractor: ExtractorAgent,
    semaphore: asyncio.Semaphore,
    force: bool,
    output_dir: Path,
) -> SectionResult:
    base = dict(
        case_name=group.case_name,
        section_name=group.unit_name,
        identifier=group.identifier,
    )
    md_path = expected_markdown_path(group.case_name, group.unit_name, output_dir)
    if not force and md_path.exists():
        return SectionResult(**base, status="skipped", markdown_path=str(md_path))

    async with semaphore:
        try:
            section = load_group(group)
            if not section.primary_text:
                return SectionResult(
                    **base, status="failed", error="无可解析的文本内容"
                )
            assessment = await assessor.assess(section)
            doc = await extractor.extract(section)
            result = write_section_output(section, assessment, doc, output_dir)
            return SectionResult(
                **base,
                status="ok",
                worth_storing=assessment.worth_storing,
                value_score=assessment.value_score,
                topics=tuple(assessment.topics),
                reason=assessment.reason,
                markdown_path=str(result.markdown_path),
            )
        except Exception as exc:  # noqa: BLE001 - 单节失败隔离
            return SectionResult(**base, status="failed", error=repr(exc))


def _build_manifest(results: list[SectionResult]) -> dict:
    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r.status == "ok"),
        "skipped": sum(1 for r in results if r.status == "skipped"),
        "failed": sum(1 for r in results if r.status == "failed"),
        "worth_storing": sum(1 for r in results if r.worth_storing),
    }
    return {"summary": summary, "sections": [asdict(r) for r in results]}


def write_manifest(results: list[SectionResult], output_dir: Path = OUTPUT_DIR) -> Path:
    """把全库处理结果汇总写入 ``output/manifest.json``。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "manifest.json"
    path.write_text(
        json.dumps(_build_manifest(results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


async def run_pipeline(
    groups: list[SourceGroup],
    model: OpenAIChatModel,
    concurrency: int = DEFAULT_CONCURRENCY,
    force: bool = False,
    output_dir: Path = OUTPUT_DIR,
) -> list[SectionResult]:
    """对一批知识单元并发执行研判 + 提取 + 落盘，并写出 manifest。"""
    assessor = AssessorAgent(model)
    extractor = ExtractorAgent(model)
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        _process_group(group, assessor, extractor, semaphore, force, output_dir)
        for group in groups
    ]
    results = await asyncio.gather(*tasks)
    write_manifest(results, output_dir)
    return results
