"""命令行入口。

子命令：
- ``stats``：扫描全库，打印节数、文件类型分布、跳过媒体统计。
- ``show <相对节路径>``：解析单个节并打印结构与主干文本预览。
- ``build <相对节路径>``：对单个节运行研判 + 提取并落盘为 md + meta.json。
- ``run``：全库批处理（分组 → 研判 → 提取 → 落盘 + manifest），支持并发与增量。
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from pathlib import Path

from .agents import AssessorAgent, ExtractorAgent, build_chat_model
from .config import CASES_DIR, OUTPUT_DIR
from .output_writer import write_section_output
from .parsers.grouping import group_by_directory, group_by_single_file
from .parsers.section_loader import iter_section_dirs, load_section
from .pipeline import run_pipeline


def _cmd_stats(_: argparse.Namespace) -> int:
    section_dirs = list(iter_section_dirs())
    if not section_dirs:
        print(f"未在 {CASES_DIR} 下发现任何节目录。")
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

    print(f"案例数: {len(cases)} | 节数: {len(section_dirs)}")
    print(f"已解析文件类型分布: {dict(type_counter)}")
    print(f"跳过媒体文件总数: {skipped_total}")
    print("\n各案例节数:")
    for case_name, count in cases.most_common():
        print(f"  {count:>2}  {case_name}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    section_dir = (CASES_DIR / args.section).resolve()
    section = load_section(section_dir)

    print(f"案例: {section.case_name}")
    print(f"节  : {section.section_name}")
    print(f"已解析文件: {len(section.files)} | 跳过媒体: {list(section.skipped_media)}")
    for parsed in section.files:
        warn = f" ⚠ {parsed.warnings}" if parsed.warnings else ""
        print(f"  - [{parsed.file_type.value}] {parsed.filename} ({parsed.char_count} 字){warn}")

    preview = (section.primary_text or "")[: args.preview]
    print(f"\n=== 主干文本预览（前 {args.preview} 字）===\n{preview}")
    return 0


async def _build_section(section_rel: str) -> int:
    section = load_section((CASES_DIR / section_rel).resolve())
    model = build_chat_model()
    assessor = AssessorAgent(model)
    extractor = ExtractorAgent(model)

    print(f"研判中: {section.case_name} / {section.section_name}")
    assessment = await assessor.assess(section)
    print(
        f"  worth_storing={assessment.worth_storing} "
        f"value_score={assessment.value_score} topics={assessment.topics}"
    )
    print(f"  理由: {assessment.reason[:120]}...")

    print("提取中...")
    doc = await extractor.extract(section)
    result = write_section_output(section, assessment, doc)
    print(f"已写出:\n  {result.markdown_path}\n  {result.meta_path}")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    return asyncio.run(_build_section(args.section))


async def _run_all(args: argparse.Namespace) -> int:
    grouper = (
        group_by_single_file if args.grouping == "single-file" else group_by_directory
    )
    groups = grouper()
    if args.limit:
        groups = groups[: args.limit]
    if not groups:
        print(f"未在 {CASES_DIR} 下发现任何素材。")
        return 1

    print(
        f"待处理知识单元: {len(groups)} | 分组={args.grouping} "
        f"| 并发={args.concurrency} | force={args.force}"
    )
    model = build_chat_model()
    results = await run_pipeline(
        groups, model, concurrency=args.concurrency, force=args.force
    )

    ok = sum(1 for r in results if r.status == "ok")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = [r for r in results if r.status == "failed"]
    worth = sum(1 for r in results if r.worth_storing)
    print(
        f"完成: ok={ok} skipped={skipped} failed={len(failed)} "
        f"| 值得入库={worth}/{ok}"
    )
    for r in failed:
        print(f"  ✗ {r.case_name}/{r.section_name}: {r.error}")
    print(f"manifest: {OUTPUT_DIR / 'manifest.json'}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    return asyncio.run(_run_all(args))


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="insurance-coach-md",
        description="保险绩优案例知识沉淀智能体（M1：解析层）",
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
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
