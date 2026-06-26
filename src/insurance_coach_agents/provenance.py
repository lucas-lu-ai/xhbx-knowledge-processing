"""Build block-level provenance for extracted Markdown.

The extractor rewrites and merges source material, so exact character-level
citations are not reliable without changing the model contract. This module
keeps provenance conservative: it indexes locatable source anchors, splits the
final Markdown into heading blocks, and links each block to the best matching
source anchors by text overlap.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .models import ExtractedDoc, FileType, ParsedFile, RawSection

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_PAGE_HEADING_RE = re.compile(r"^## 第\s*(\d+)\s*页\s*$", re.MULTILINE)
_MAX_REFS_PER_BLOCK = 3


@dataclass(frozen=True)
class _SourceAnchor:
    anchor_id: str
    source_id: str
    type: str
    filename: str
    locator: dict[str, Any]
    text: str


@dataclass(frozen=True)
class _MarkdownBlock:
    block_id: str
    heading_path: list[str]
    start_line: int
    end_line: int
    text: str


def _source_id(parsed: ParsedFile) -> str:
    return f"{parsed.file_type.value}:{parsed.filename}"


def _source_path(section: RawSection, filename: str) -> str:
    return f"{section.section_dir.rstrip('/')}/{filename}" if section.section_dir else filename


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _heading_path_for_line(lines: list[str], end_index: int) -> list[str]:
    stack: list[str | None] = []
    for line in lines[: end_index + 1]:
        match = _HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        if len(stack) < level:
            stack.extend([None] * (level - len(stack)))
        stack = stack[:level]
        stack[level - 1] = title
    return [item for item in stack if item]


def _page_anchors(parsed: ParsedFile) -> list[_SourceAnchor]:
    matches = list(_PAGE_HEADING_RE.finditer(parsed.text))
    if not matches:
        return []

    anchors: list[_SourceAnchor] = []
    source_id = _source_id(parsed)
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(parsed.text)
        page = int(match.group(1))
        chunk = parsed.text[match.start() : end].strip()
        anchors.append(
            _SourceAnchor(
                anchor_id=f"{source_id}#page-{page}",
                source_id=source_id,
                type=parsed.file_type.value,
                filename=parsed.filename,
                locator={
                    "page": page,
                    "source_start_line": _line_number(parsed.text, match.start()),
                    "source_end_line": _line_number(parsed.text, end),
                },
                text=chunk,
            )
        )
    return anchors


def _heading_anchors(parsed: ParsedFile) -> list[_SourceAnchor]:
    lines = parsed.text.splitlines()
    heading_indices = [
        index for index, line in enumerate(lines) if _HEADING_RE.match(line)
    ]
    if not heading_indices:
        return []

    anchors: list[_SourceAnchor] = []
    source_id = _source_id(parsed)
    for anchor_index, start_index in enumerate(heading_indices, start=1):
        next_index = (
            heading_indices[anchor_index]
            if anchor_index < len(heading_indices)
            else len(lines)
        )
        chunk = "\n".join(lines[start_index:next_index]).strip()
        anchors.append(
            _SourceAnchor(
                anchor_id=f"{source_id}#heading-{anchor_index}",
                source_id=source_id,
                type=parsed.file_type.value,
                filename=parsed.filename,
                locator={
                    "heading_path": _heading_path_for_line(lines, start_index),
                    "source_start_line": start_index + 1,
                    "source_end_line": next_index,
                },
                text=chunk,
            )
        )
    return anchors


def _paragraph_anchors(parsed: ParsedFile) -> list[_SourceAnchor]:
    anchors: list[_SourceAnchor] = []
    source_id = _source_id(parsed)
    line_number = 1
    block_index = 1
    for raw_block in re.split(r"\n\s*\n", parsed.text.strip()):
        block = raw_block.strip()
        if not block:
            line_number += raw_block.count("\n") + 1
            continue
        line_count = block.count("\n") + 1
        anchors.append(
            _SourceAnchor(
                anchor_id=f"{source_id}#block-{block_index}",
                source_id=source_id,
                type=parsed.file_type.value,
                filename=parsed.filename,
                locator={
                    "block_index": block_index,
                    "source_start_line": line_number,
                    "source_end_line": line_number + line_count - 1,
                },
                text=block,
            )
        )
        line_number += line_count + 1
        block_index += 1
    return anchors


def _source_anchors(section: RawSection) -> list[_SourceAnchor]:
    anchors: list[_SourceAnchor] = []
    for parsed in section.files:
        if parsed.is_empty:
            continue
        if parsed.file_type in (FileType.PPTX, FileType.PDF):
            page_anchors = _page_anchors(parsed)
            anchors.extend(page_anchors or _paragraph_anchors(parsed))
        else:
            anchors.extend(_heading_anchors(parsed) or _paragraph_anchors(parsed))
    return anchors


def _markdown_blocks(markdown: str, body_start_line: int) -> list[_MarkdownBlock]:
    lines = markdown.splitlines()
    heading_indices = [
        index for index, line in enumerate(lines) if _HEADING_RE.match(line)
    ]
    if not heading_indices:
        text = markdown.strip()
        return [
            _MarkdownBlock(
                block_id="b001",
                heading_path=[],
                start_line=body_start_line,
                end_line=body_start_line + max(len(lines), 1) - 1,
                text=text,
            )
        ] if text else []

    blocks: list[_MarkdownBlock] = []
    for block_number, start_index in enumerate(heading_indices, start=1):
        next_index = (
            heading_indices[block_number]
            if block_number < len(heading_indices)
            else len(lines)
        )
        chunk = "\n".join(lines[start_index:next_index]).strip()
        blocks.append(
            _MarkdownBlock(
                block_id=f"b{block_number:03d}",
                heading_path=_heading_path_for_line(lines, start_index),
                start_line=body_start_line + start_index,
                end_line=body_start_line + next_index - 1,
                text=chunk,
            )
        )
    return blocks


def _normalized_grams(text: str) -> set[str]:
    normalized = "".join(ch.lower() for ch in text if ch.isalnum())
    if not normalized:
        return set()
    if len(normalized) == 1:
        return {normalized}
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def _match_source_refs(
    block: _MarkdownBlock, anchors: list[_SourceAnchor]
) -> list[dict[str, Any]]:
    block_grams = _normalized_grams(block.text)
    if not block_grams:
        return []

    scored: list[tuple[float, _SourceAnchor]] = []
    for anchor in anchors:
        anchor_grams = _normalized_grams(anchor.text)
        if not anchor_grams:
            continue
        overlap = block_grams & anchor_grams
        if not overlap:
            continue
        score = len(overlap) / len(block_grams)
        scored.append((score, anchor))

    scored.sort(key=lambda item: item[0], reverse=True)
    refs: list[dict[str, Any]] = []
    for score, anchor in scored[:_MAX_REFS_PER_BLOCK]:
        refs.append(
            {
                "source_id": anchor.source_id,
                "anchor_id": anchor.anchor_id,
                "locator": anchor.locator,
                "match_score": round(score, 4),
            }
        )
    return refs


def build_provenance(
    section: RawSection, doc: ExtractedDoc, body_start_line: int
) -> dict[str, Any]:
    """Build JSON-serializable provenance for one extracted Markdown document."""
    sources = [
        {
            "source_id": _source_id(parsed),
            "type": parsed.file_type.value,
            "filename": parsed.filename,
            "path": _source_path(section, parsed.filename),
        }
        for parsed in section.files
        if not parsed.is_empty
    ]
    anchors = _source_anchors(section)
    blocks = []
    for block in _markdown_blocks(doc.body_markdown, body_start_line):
        blocks.append(
            {
                "block_id": block.block_id,
                "heading_path": block.heading_path,
                "markdown_start_line": block.start_line,
                "markdown_end_line": block.end_line,
                "text_hash": hashlib.sha256(block.text.encode("utf-8")).hexdigest(),
                "source_refs": _match_source_refs(block, anchors),
            }
        )

    return {
        "version": 1,
        "case": section.case_name,
        "section": section.section_name,
        "title": doc.title,
        "sources": sources,
        "blocks": blocks,
    }
