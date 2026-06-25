"""解析 docx 讲义为 Markdown 文本，保留标题层级与表格。

绩优案例的 docx 使用标准 Word 标题样式（Heading 1-4）并含表格，
本解析器按文档原始顺序遍历段落与表格，转为带 ``#`` 标题和 Markdown 表格的文本。
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from ..models import FileType, ParsedFile

# 匹配英文 "Heading 2" 或中文 "标题 2" 样式名，捕获层级数字。
_HEADING_RE = re.compile(r"(?:heading|标题)\s*(\d+)", re.IGNORECASE)


def _heading_level(style_name: str | None) -> int | None:
    """从段落样式名提取标题层级；非标题返回 None。"""
    if not style_name:
        return None
    match = _HEADING_RE.search(style_name)
    return int(match.group(1)) if match else None


def _iter_block_items(document: Document):
    """按文档原始顺序产出段落与表格（python-docx 无内置有序迭代）。"""
    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _table_to_markdown(table: Table) -> str:
    """把表格转为 Markdown 表格。空表返回空串。"""
    rows = [
        [cell.text.strip().replace("\n", " ") for cell in row.cells]
        for row in table.rows
    ]
    if not rows:
        return ""

    header = rows[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def parse_docx(path: Path) -> ParsedFile:
    """解析 docx 文件为 ``ParsedFile``。

    解析失败时返回带 warning 的空文本结果，不抛出，避免中断整个节的处理。
    """
    filename = path.name
    try:
        document = Document(str(path))
    except Exception as exc:  # noqa: BLE001 - 边界处统一兜底，记录原因
        return ParsedFile(
            file_type=FileType.DOCX,
            filename=filename,
            text="",
            warnings=(f"docx 解析失败: {exc}",),
        )

    blocks: list[str] = []
    for item in _iter_block_items(document):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if not text:
                continue
            level = _heading_level(item.style.name if item.style else None)
            blocks.append(f"{'#' * level} {text}" if level else text)
        else:  # Table
            md = _table_to_markdown(item)
            if md:
                blocks.append(md)

    warnings: tuple[str, ...] = ()
    if not blocks:
        warnings = ("docx 内容为空",)

    return ParsedFile(
        file_type=FileType.DOCX,
        filename=filename,
        text="\n\n".join(blocks),
        warnings=warnings,
    )
