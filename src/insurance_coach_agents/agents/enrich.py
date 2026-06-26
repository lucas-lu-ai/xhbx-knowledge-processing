"""视觉增强：把课件配图识别结果绑定回对应页的原始素材。

图片通常与同页文字共同表达完整语义。这里先把信息图转写插回 pptx/pdf 的
对应页文本，再交给研判、提取、质检链路，避免最终 Markdown 里出现脱离上下文
的文末图片章节。装饰图与识别失败的图自动略过，不进素材。
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from ..models import FileType, ParsedFile, RawSection
from ..parsers.image_extract import extract_images
from .vision import ImageDescriber

_PAGE_HEADING_RE = re.compile(r"^## 第\s*(\d+)\s*页\s*$", re.MULTILINE)
_IMAGE_SUBHEADING = "### 本页配图内容"
# 支持抽图的源文件类型（pptx 课件、pdf 资料）。
_SUPPORTED_SUFFIXES = (".pptx", ".pdf")
_SUPPORTED_FILE_TYPES = {FileType.PPTX, FileType.PDF}


def _image_section(descriptions: Sequence[str]) -> str:
    """把同页一张或多张配图的转写整理为该页内的 Markdown 片段。"""
    cleaned = [item.strip() for item in descriptions if item.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return f"{_IMAGE_SUBHEADING}\n{cleaned[0]}"

    parts = [_IMAGE_SUBHEADING]
    for index, description in enumerate(cleaned, start=1):
        parts.append(f"#### 配图 {index}\n{description}")
    return "\n\n".join(parts)


def _split_page_blocks(text: str) -> tuple[str, list[tuple[int, str]]]:
    """按 ``## 第 N 页`` 拆分 pptx/pdf 解析文本。"""
    matches = list(_PAGE_HEADING_RE.finditer(text))
    if not matches:
        return text.strip(), []

    prefix = text[: matches[0].start()].strip()
    blocks: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((int(match.group(1)), text[match.start() : end].strip()))
    return prefix, blocks


def _fallback_image_block(descriptions_by_page: dict[int, list[str]]) -> str:
    """找不到页标题时保留页码来源，作为该来源文件末尾的兜底片段。"""
    entries: list[str] = []
    for page_index in sorted(descriptions_by_page):
        section = _image_section(descriptions_by_page[page_index])
        if section:
            entries.append(f"（第 {page_index} 页配图）\n{section}")
    return "## 配图内容\n\n" + "\n\n".join(entries) if entries else ""


def _bind_page_descriptions(
    text: str, descriptions_by_page: dict[int, list[str]]
) -> str:
    """把视觉转写插入对应页文本；缺页时补出页块。"""
    if not descriptions_by_page:
        return text

    prefix, blocks = _split_page_blocks(text)
    if not blocks:
        if not prefix:
            return "\n\n".join(
                f"## 第 {page_index} 页\n\n{section}"
                for page_index in sorted(descriptions_by_page)
                if (section := _image_section(descriptions_by_page[page_index]))
            )
        fallback = _fallback_image_block(descriptions_by_page)
        return f"{prefix}\n\n{fallback}" if fallback else prefix

    blocks_by_page = {page_index: block for page_index, block in blocks}
    all_pages = sorted(set(blocks_by_page) | set(descriptions_by_page))
    merged: list[str] = [prefix] if prefix else []
    for page_index in all_pages:
        block = blocks_by_page.get(page_index, f"## 第 {page_index} 页")
        image_content = _image_section(descriptions_by_page.get(page_index, ()))
        if image_content:
            block = block.rstrip() + "\n\n" + image_content
        merged.append(block)
    return "\n\n".join(merged)


async def _describe_sources_by_page(
    source_paths: Sequence[Path], describer: ImageDescriber
) -> dict[str, dict[int, list[str]]]:
    """按文件名与页码聚合有效配图转写。"""
    source_files = [
        p for p in source_paths if p.suffix.lower() in _SUPPORTED_SUFFIXES
    ]
    descriptions_by_file: dict[str, dict[int, list[str]]] = {}
    for path in source_files:
        descriptions_by_page: dict[int, list[str]] = defaultdict(list)
        for image in extract_images(path):
            description = await describer.describe(image)
            if not description:  # 装饰图 / 碎片 / 识别失败 → 不进素材
                continue
            descriptions_by_page[image.page_index].append(description.strip())
        if descriptions_by_page:
            descriptions_by_file[path.name] = dict(descriptions_by_page)
    return descriptions_by_file


async def enrich_section_with_vision(
    section: RawSection, source_paths: Sequence[Path], describer: ImageDescriber
) -> RawSection:
    """识别一组源文件配图，返回把图片信息绑定到对应页后的 ``RawSection``。

    按文件顺序、页序串行识别，保证产出的页码顺序稳定、来源清晰；
    无信息图时返回原 ``section``；缓存命中时几乎无开销。
    """
    descriptions_by_file = await _describe_sources_by_page(source_paths, describer)
    if not descriptions_by_file:
        return section

    changed = False
    files: list[ParsedFile] = []
    for parsed in section.files:
        descriptions_by_page = descriptions_by_file.get(parsed.filename)
        if parsed.file_type in _SUPPORTED_FILE_TYPES and descriptions_by_page:
            files.append(
                ParsedFile(
                    file_type=parsed.file_type,
                    filename=parsed.filename,
                    text=_bind_page_descriptions(parsed.text, descriptions_by_page),
                    warnings=parsed.warnings,
                )
            )
            changed = True
        else:
            files.append(parsed)

    if not changed:
        return section

    return RawSection(
        case_name=section.case_name,
        section_name=section.section_name,
        section_dir=section.section_dir,
        files=tuple(files),
        skipped_media=section.skipped_media,
    )
