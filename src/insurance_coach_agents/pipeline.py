"""全库批处理编排：分组 → 研判 → 提取 → 落盘 → 汇总 manifest。

异步并发（信号量限流）；单节失败隔离不中断全库；支持增量（跳过已产出）。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from agentscope.model import OpenAIChatModel

from .agents import (
    AssessorAgent,
    ExtractorAgent,
    ImageDescriber,
    enrich_section_with_vision,
)
from .config import OUTPUT_DIR
from .models import ExtractedDoc
from .output_writer import expected_markdown_path, write_section_output
from .parsers.grouping import SourceGroup, load_group

# 视觉识别缓存目录名（位于 output_dir 下，按图片 sha256 缓存识别结果）。
IMAGE_CACHE_DIRNAME = ".image_cache"

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
    describer: ImageDescriber | None,
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
            if describer is not None:
                vision_block = await enrich_section_with_vision(
                    group.file_paths, describer
                )
                if vision_block:
                    doc = ExtractedDoc(
                        title=doc.title,
                        body_markdown=doc.body_markdown.rstrip()
                        + "\n\n"
                        + vision_block,
                    )
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
    # 原子写：先 .tmp 再 rename，避免中断留下半截 manifest。
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(_build_manifest(results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


async def run_pipeline(
    groups: list[SourceGroup],
    model: OpenAIChatModel,
    concurrency: int = DEFAULT_CONCURRENCY,
    force: bool = False,
    output_dir: Path = OUTPUT_DIR,
    vision: bool = True,
    vision_model: OpenAIChatModel | None = None,
) -> list[SectionResult]:
    """对一批知识单元并发执行研判 + 提取 +（可选）视觉增强 + 落盘，并写出 manifest。

    ``vision=True`` 时对各单元的 pptx 配图做视觉识别，把信息图转写追加到正文末尾，
    识别结果按 sha256 缓存于 ``output_dir/.image_cache``。视觉识别走 ``vision_model``
    （qwen 不支持图像，须传入支持视觉的模型）；未显式传入时回退复用 ``model``。
    """
    assessor = AssessorAgent(model)
    extractor = ExtractorAgent(model)
    describer = (
        ImageDescriber(
            vision_model or model, cache_dir=output_dir / IMAGE_CACHE_DIRNAME
        )
        if vision
        else None
    )
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [
        _process_group(
            group, assessor, extractor, semaphore, force, output_dir, describer
        )
        for group in groups
    ]
    results = await asyncio.gather(*tasks)
    write_manifest(results, output_dir)
    return results
