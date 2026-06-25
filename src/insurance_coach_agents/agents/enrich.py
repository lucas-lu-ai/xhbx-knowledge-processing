"""视觉增强：把课件配图识别结果汇总为知识单元末尾的统一章节（方案 A）。

设计取舍——图片转写内容统一汇总到正文末尾的「课件图片信息（视觉识别）」章节，
每条标注来源页码，便于溯源、实现简单、不打断主干叙述。装饰图与识别失败的图
自动略过，不进正文。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..parsers.image_extract import extract_pptx_images
from .vision import ImageDescriber

_IMAGE_SECTION_HEADER = "## 课件图片信息（视觉识别）"


def _label(slide_index: int, stem: str, multi_source: bool) -> str:
    """配图来源标注：单课件只标页码，多课件额外标文件名以区分。"""
    if multi_source:
        return f"（《{stem}》第 {slide_index} 页配图）"
    return f"（第 {slide_index} 页配图）"


async def enrich_section_with_vision(
    pptx_paths: Sequence[Path], describer: ImageDescriber
) -> str:
    """识别一组 pptx 的配图，返回方案 A 的视觉章节 Markdown（无信息图则为空串）。

    按 pptx 顺序、页序串行识别，保证产出的页码顺序稳定、来源清晰；
    缓存命中时几乎无开销。
    """
    pptx_files = [p for p in pptx_paths if p.suffix.lower() == ".pptx"]
    if not pptx_files:
        return ""

    multi_source = len(pptx_files) > 1
    entries: list[str] = []
    for path in pptx_files:
        for image in extract_pptx_images(path):
            description = await describer.describe(image)
            if not description:  # 装饰图 / 识别失败 → 不进正文
                continue
            label = _label(image.slide_index, path.stem, multi_source)
            entries.append(f"{label}\n{description.strip()}")

    if not entries:
        return ""
    return _IMAGE_SECTION_HEADER + "\n\n" + "\n\n".join(entries)
