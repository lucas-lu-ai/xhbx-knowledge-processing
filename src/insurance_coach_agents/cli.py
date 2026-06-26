"""命令行入口。

子命令：
- ``stats``：扫描全库，打印节数、文件类型分布、跳过媒体统计。
- ``show <相对节路径>``：解析单个节并打印结构与主干文本预览。
- ``build <相对节路径>``：对单个节运行研判 + 提取并落盘为 md + meta/provenance.json。
- ``run``：全库批处理（分组 → 研判 → 提取 → 落盘 + manifest），支持并发与增量。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import Counter
from pathlib import Path

from .agents import (
    AssessorAgent,
    ExtractorAgent,
    ImageDescriber,
    ReviserAgent,
    ReviewerAgent,
    build_chat_model,
    build_vision_model,
    enrich_section_with_vision,
)
from .config import CASES_DIR, OUTPUT_DIR
from .logging_config import configure_logging
from .output_writer import write_section_output
from .parsers.grouping import group_by_directory, group_by_single_file
from .parsers.section_loader import iter_section_dirs, load_section
from .pipeline import IMAGE_CACHE_DIRNAME, run_pipeline

LOGGER = logging.getLogger(__name__)


def _cmd_stats(_: argparse.Namespace) -> int:
    section_dirs = list(iter_section_dirs())
    if not section_dirs:
        LOGGER.error("未在 %s 下发现任何节目录。", CASES_DIR)
        return 1

    type_counter: Counter[str] = Counter()
    skipped_total = 0
    cases: Counter[str] = Counter()

    for section_dir in section_dirs:
        section = load_section(section_dir)
        cases[section.case_name] += 1
        skipped_total += len(section.skipped_media)
        for parsed in section.files:
            type_counter[parsed.file_type.value] += 1

    LOGGER.info("案例数: %s | 节数: %s", len(cases), len(section_dirs))
    LOGGER.info("已解析文件类型分布: %s", dict(type_counter))
    LOGGER.info("跳过媒体文件总数: %s", skipped_total)
    LOGGER.info("\n各案例节数:")
    for case_name, count in cases.most_common():
        LOGGER.info("  %2s  %s", count, case_name)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    section_dir = (CASES_DIR / args.section).resolve()
    section = load_section(section_dir)

    LOGGER.info("案例: %s", section.case_name)
    LOGGER.info("节  : %s", section.section_name)
    LOGGER.info(
        "已解析文件: %s | 跳过媒体: %s",
        len(section.files),
        list(section.skipped_media),
    )
    for parsed in section.files:
        warn = f" ⚠ {parsed.warnings}" if parsed.warnings else ""
        LOGGER.info(
            "  - [%s] %s (%s 字)%s",
            parsed.file_type.value,
            parsed.filename,
            parsed.char_count,
            warn,
        )

    preview = (section.primary_text or "")[: args.preview]
    LOGGER.info("\n=== 主干文本预览（前 %s 字）===\n%s", args.preview, preview)
    return 0


async def _build_section(
    section_rel: str, vision: bool, review: bool, auto_fix: bool
) -> int:
    section_dir = (CASES_DIR / section_rel).resolve()
    section = load_section(section_dir)
    model = build_chat_model()
    assessor = AssessorAgent(model)
    extractor = ExtractorAgent(model)

    if vision:
        LOGGER.info("视觉识别课件/PDF配图中...")
        vision_model = build_vision_model()
        describer = ImageDescriber(
            vision_model, cache_dir=OUTPUT_DIR / IMAGE_CACHE_DIRNAME
        )
        source_paths = sorted(section_dir.glob("*.pptx")) + sorted(
            section_dir.glob("*.pdf")
        )
        original_section = section
        section = await enrich_section_with_vision(section, source_paths, describer)
        if section != original_section:
            LOGGER.info("  已将配图信息绑定到对应页素材")
        else:
            LOGGER.info("  无可入库的配图信息")

    LOGGER.info("研判中: %s / %s", section.case_name, section.section_name)
    assessment = await assessor.assess(section)
    LOGGER.info(
        "  worth_storing=%s value_score=%s topics=%s",
        assessment.worth_storing,
        assessment.value_score,
        assessment.topics,
    )
    LOGGER.info("  理由: %s...", assessment.reason[:120])

    LOGGER.info("提取中...")
    doc = await extractor.extract(section)

    verdict = None
    if review:
        LOGGER.info("质检中...")
        reviewer = ReviewerAgent(model)
        verdict = await reviewer.review(section, doc)
        LOGGER.info(
            "  质检 passed=%s score=%s heading_ok=%s fidelity_ok=%s no_meta_leak=%s",
            verdict.passed,
            verdict.score,
            verdict.heading_ok,
            verdict.fidelity_ok,
            verdict.no_meta_leak,
        )
        for issue in verdict.issues:
            LOGGER.info("  · %s", issue)
        if auto_fix and (not verdict.passed or verdict.issues):
            LOGGER.info("返修中...")
            reviser = ReviserAgent(model)
            revised_doc = await reviser.revise(section, doc, verdict)
            revised_verdict = await reviewer.review(section, revised_doc)
            LOGGER.info(
                "  复检 passed=%s score=%s heading_ok=%s fidelity_ok=%s no_meta_leak=%s",
                revised_verdict.passed,
                revised_verdict.score,
                revised_verdict.heading_ok,
                revised_verdict.fidelity_ok,
                revised_verdict.no_meta_leak,
            )
            for issue in revised_verdict.issues:
                LOGGER.info("  · %s", issue)
            if revised_verdict.passed:
                doc = revised_doc
                verdict = revised_verdict
                LOGGER.info("  返修通过，采用返修稿")
            else:
                LOGGER.info("  返修后仍未通过，保留初版整理稿")

    result = write_section_output(section, assessment, doc, review=verdict)
    written = [result.markdown_path, result.meta_path]
    if result.review_path:
        written.append(result.review_path)
    LOGGER.info("已写出:\n  %s", "\n  ".join(str(path) for path in written))
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    return asyncio.run(
        _build_section(
            args.section,
            vision=not args.no_vision,
            review=args.review,
            auto_fix=args.auto_fix,
        )
    )


async def _run_all(args: argparse.Namespace) -> int:
    grouper = (
        group_by_single_file if args.grouping == "single-file" else group_by_directory
    )
    groups = grouper()
    if args.limit:
        groups = groups[: args.limit]
    if not groups:
        LOGGER.error("未在 %s 下发现任何素材。", CASES_DIR)
        return 1

    vision = not args.no_vision
    review = args.review
    LOGGER.info(
        "待处理知识单元: %s | 分组=%s | 并发=%s | force=%s | 视觉=%s | 质检=%s | 返修=%s",
        len(groups),
        args.grouping,
        args.concurrency,
        args.force,
        vision,
        review,
        args.auto_fix,
    )
    model = build_chat_model()
    vision_model = build_vision_model() if vision else None
    results = await run_pipeline(
        groups,
        model,
        concurrency=args.concurrency,
        force=args.force,
        vision=vision,
        vision_model=vision_model,
        review=review,
        auto_fix=args.auto_fix,
    )

    ok = sum(1 for r in results if r.status == "ok")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = [r for r in results if r.status == "failed"]
    worth = sum(1 for r in results if r.worth_storing)
    LOGGER.info(
        "完成: ok=%s skipped=%s failed=%s | 值得入库=%s/%s",
        ok,
        skipped,
        len(failed),
        worth,
        ok,
    )
    if review:
        review_failed = [r for r in results if r.review_passed is False]
        LOGGER.info("质检未通过: %s/%s", len(review_failed), ok)
        for r in review_failed:
            LOGGER.info(
                "  ⚠ %s/%s: %s",
                r.case_name,
                r.section_name,
                list(r.review_issues),
            )
    for r in failed:
        LOGGER.error("  ✗ %s/%s: %s", r.case_name, r.section_name, r.error)
    LOGGER.info("manifest: %s", OUTPUT_DIR / "manifest.json")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    return asyncio.run(_run_all(args))


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(
        prog="insurance-coach-md",
        description="保险绩优案例知识沉淀智能体（解析 → 研判 → 提取 → 视觉 → 质检）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_stats = sub.add_parser("stats", help="统计全库解析情况")
    p_stats.set_defaults(func=_cmd_stats)

    p_show = sub.add_parser("show", help="解析并预览单个节")
    p_show.add_argument("section", help="相对绩优案例根的节目录路径")
    p_show.add_argument("--preview", type=int, default=400, help="主干文本预览字数")
    p_show.set_defaults(func=_cmd_show)

    p_build = sub.add_parser("build", help="研判 + 提取单个节并落盘")
    p_build.add_argument("section", help="相对绩优案例根的节目录路径")
    p_build.add_argument(
        "--no-vision", action="store_true", help="跳过课件配图的视觉识别"
    )
    p_build.add_argument(
        "--review", action="store_true", help="对整理稿做质检（规范性/信息保真）"
    )
    p_build.add_argument(
        "--auto-fix",
        action="store_true",
        help="质检发现问题后调用返修智能体，复检通过才采用返修稿",
    )
    p_build.set_defaults(func=_cmd_build)

    p_run = sub.add_parser("run", help="全库批处理（研判 + 提取 + manifest）")
    p_run.add_argument(
        "--grouping",
        choices=["directory", "single-file"],
        default="directory",
        help="分组策略：directory=目录分组（默认），single-file=单文件成单元",
    )
    p_run.add_argument("--concurrency", type=int, default=4, help="并发数")
    p_run.add_argument("--force", action="store_true", help="忽略增量，强制重跑")
    p_run.add_argument("--limit", type=int, default=0, help="只处理前 N 个单元（调试用）")
    p_run.add_argument(
        "--no-vision", action="store_true", help="跳过课件配图的视觉识别"
    )
    p_run.add_argument(
        "--review", action="store_true", help="对每节整理稿做质检并汇总到 manifest"
    )
    p_run.add_argument(
        "--auto-fix",
        action="store_true",
        help="质检发现问题后调用返修智能体，复检通过才采用返修稿",
    )
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args()
    if getattr(args, "auto_fix", False) and not getattr(args, "review", False):
        parser.error("--auto-fix 需要同时指定 --review")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
