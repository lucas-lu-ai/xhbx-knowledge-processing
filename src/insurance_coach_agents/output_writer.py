"""产物落盘：把研判 + 提取结果写为 Markdown、meta.json 与 provenance.json。

Markdown 的 YAML frontmatter 与同名 meta.json 保持单元级元数据一致；
provenance.json 保存块级来源引用，供下游向量化与人工核查。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .config import OUTPUT_DIR
from .models import Assessment, ExtractedDoc, RawSection, ReviewResult
from .provenance import build_provenance

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')


def _safe_name(name: str) -> str:
    """把案例 / 节名清洗为安全的文件夹 / 文件名。"""
    return _UNSAFE_CHARS.sub("_", name).strip()


def _atomic_write_text(path: Path, text: str) -> None:
    """原子写文本：先写 ``.tmp`` 再 rename，避免中断/并发留下空或半截文件。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def expected_markdown_path(
    case_name: str, section_name: str, output_dir: Path = OUTPUT_DIR
) -> Path:
    """返回某节预期的 Markdown 产物路径（用于增量跳过判断）。"""
    return output_dir / _safe_name(case_name) / f"{_safe_name(section_name)}.md"


def _yaml_scalar(value: str) -> str:
    """对可能含特殊字符的标量做双引号转义。"""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass(frozen=True)
class WriteResult:
    """一次落盘的结果路径。"""

    markdown_path: Path
    meta_path: Path
    provenance_path: Path
    review_path: Path | None = None


def _build_metadata(
    section: RawSection, assessment: Assessment, doc: ExtractedDoc
) -> dict:
    """组装与 frontmatter 一致的元数据字典。"""
    return {
        "case": section.case_name,
        "section": section.section_name,
        "title": doc.title,
        "topics": list(assessment.topics),
        "serves": assessment.serves.model_dump(),
        "value_score": assessment.value_score,
        "worth_storing": assessment.worth_storing,
        "reason": assessment.reason,
        "sources": [f.file_type.value for f in section.files if not f.is_empty],
        "section_dir": section.section_dir,
    }


def _render_frontmatter(meta: dict) -> str:
    """把元数据渲染为 YAML frontmatter 块。"""
    lines = ["---"]
    lines.append(f"case: {_yaml_scalar(meta['case'])}")
    lines.append(f"section: {_yaml_scalar(meta['section'])}")
    lines.append(f"title: {_yaml_scalar(meta['title'])}")
    topics = ", ".join(_yaml_scalar(t) for t in meta["topics"])
    lines.append(f"topics: [{topics}]")
    serves = ", ".join(f"{k}: {v}" for k, v in meta["serves"].items())
    lines.append(f"serves: {{ {serves} }}")
    lines.append(f"value_score: {meta['value_score']}")
    lines.append(f"worth_storing: {str(meta['worth_storing']).lower()}")
    sources = ", ".join(meta["sources"])
    lines.append(f"sources: [{sources}]")
    lines.append("---")
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def _pass_fail(value: bool) -> str:
    return "通过" if value else "未通过"


def _render_review_markdown(section: RawSection, review: ReviewResult) -> str:
    """把结构化质检结论渲染成人工可读的 Markdown 报告。"""
    issues = review.issues or ["无"]
    lines = [
        f"# {section.section_name} - 质检报告",
        "",
        "## 结论",
        f"- 是否通过: {_yes_no(review.passed)}",
        f"- 综合评分: {review.score:.2f}",
        "",
        "## 检查项",
        f"- Markdown 规范性: {_pass_fail(review.heading_ok)}",
        f"- 信息保真: {_pass_fail(review.fidelity_ok)}",
        f"- 无加工旁白: {_pass_fail(review.no_meta_leak)}",
        "",
        "## 问题列表",
    ]
    lines.extend(f"- {issue}" for issue in issues)
    return "\n".join(lines) + "\n"


def write_section_output(
    section: RawSection,
    assessment: Assessment,
    doc: ExtractedDoc,
    output_dir: Path = OUTPUT_DIR,
    review: ReviewResult | None = None,
) -> WriteResult:
    """把单个节的产物写入 Markdown、meta.json 与可选质检报告。"""
    case_dir = output_dir / _safe_name(section.case_name)
    case_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_name(section.section_name)
    markdown_path = case_dir / f"{stem}.md"
    meta_path = case_dir / f"{stem}.meta.json"
    provenance_path = case_dir / f"{stem}.provenance.json"
    review_path = case_dir / f"{stem}.review.md" if review else None

    meta = _build_metadata(section, assessment, doc)
    frontmatter = _render_frontmatter(meta)
    provenance = build_provenance(
        section, doc, body_start_line=len(frontmatter.splitlines()) + 2
    )
    _atomic_write_text(markdown_path, f"{frontmatter}\n\n{doc.body_markdown}\n")
    _atomic_write_text(
        meta_path, json.dumps(meta, ensure_ascii=False, indent=2)
    )
    _atomic_write_text(
        provenance_path,
        json.dumps(provenance, ensure_ascii=False, indent=2),
    )
    if review and review_path:
        _atomic_write_text(review_path, _render_review_markdown(section, review))
    return WriteResult(
        markdown_path=markdown_path,
        meta_path=meta_path,
        provenance_path=provenance_path,
        review_path=review_path,
    )
