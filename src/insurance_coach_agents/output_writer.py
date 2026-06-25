"""产物落盘：把研判 + 提取结果写为 Markdown（含 frontmatter）与 meta.json。

Markdown 的 YAML frontmatter 与同名 meta.json 元数据保持一致，供下游向量化与溯源。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .config import OUTPUT_DIR
from .models import Assessment, ExtractedDoc, RawSection

_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')


def _safe_name(name: str) -> str:
    """把案例 / 节名清洗为安全的文件夹 / 文件名。"""
    return _UNSAFE_CHARS.sub("_", name).strip()


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


def write_section_output(
    section: RawSection,
    assessment: Assessment,
    doc: ExtractedDoc,
    output_dir: Path = OUTPUT_DIR,
) -> WriteResult:
    """把单个节的产物写入 ``output/<案例>/<节>.md`` 与 ``<节>.meta.json``。"""
    case_dir = output_dir / _safe_name(section.case_name)
    case_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_name(section.section_name)
    markdown_path = case_dir / f"{stem}.md"
    meta_path = case_dir / f"{stem}.meta.json"

    meta = _build_metadata(section, assessment, doc)
    frontmatter = _render_frontmatter(meta)
    markdown_path.write_text(
        f"{frontmatter}\n\n{doc.body_markdown}\n", encoding="utf-8"
    )
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return WriteResult(markdown_path=markdown_path, meta_path=meta_path)
