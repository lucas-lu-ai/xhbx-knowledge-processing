"""解析 pdf 资料，逐页提取文本。

当前绩优案例数据未见 pdf，本解析器为流程预留支持（架构文档已声明）。
逐页用 pypdf 提取纯文本；扫描件（无文本层）会得到空结果并给出 warning。
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from ..models import FileType, ParsedFile


def parse_pdf(path: Path) -> ParsedFile:
    """解析 pdf 文件为 ``ParsedFile``。"""
    filename = path.name
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001
        return ParsedFile(
            file_type=FileType.PDF,
            filename=filename,
            text="",
            warnings=(f"pdf 解析失败: {exc}",),
        )

    blocks: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:  # noqa: BLE001 - 单页失败不应中断整篇
            text = ""
        if text:
            blocks.append(f"## 第 {index} 页\n{text}")

    warnings = (
        () if blocks else ("pdf 无可提取文本（可能为扫描件，需 OCR）",)
    )
    return ParsedFile(
        file_type=FileType.PDF,
        filename=filename,
        text="\n\n".join(blocks),
        warnings=warnings,
    )
