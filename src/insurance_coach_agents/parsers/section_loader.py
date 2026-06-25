"""聚合一个「节」目录的多文件为 ``RawSection``，并提供节目录发现。

分派规则：按扩展名映射到对应 parser；音视频媒体记入 ``skipped_media``；
其余无关文件（如 .DS_Store）忽略。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ..config import CASES_DIR, EXTENSION_TO_TYPE, MEDIA_EXTENSIONS
from ..models import FileType, ParsedFile, RawSection
from .docx_parser import parse_docx
from .pdf_parser import parse_pdf
from .pptx_parser import parse_pptx
from .txt_parser import parse_txt

# FileType → 解析函数。
_PARSERS = {
    FileType.DOCX: parse_docx,
    FileType.PPTX: parse_pptx,
    FileType.PDF: parse_pdf,
    FileType.TXT: parse_txt,
}


def _normalized_suffix(path: Path) -> str:
    """返回小写扩展名（含点），如 ``.txt``。"""
    return path.suffix.lower()


def parse_file(path: Path) -> ParsedFile | None:
    """按扩展名分派到对应 parser；非受支持类型返回 None。"""
    file_type = EXTENSION_TO_TYPE.get(_normalized_suffix(path))
    return _PARSERS[file_type](path) if file_type is not None else None


def _relative_to_cases(path: Path) -> str:
    """返回相对绩优案例根的路径；不在其下时返回绝对路径字符串。"""
    try:
        return str(path.resolve().relative_to(CASES_DIR.resolve()))
    except ValueError:
        return str(path)


def load_section(section_dir: Path, case_name: str | None = None) -> RawSection:
    """加载单个节目录为 ``RawSection``。

    Args:
        section_dir: 节目录路径（其下直接含 docx/pptx/pdf/txt 等文件）。
        case_name: 案例名；默认取节目录的父目录名。
    """
    if not section_dir.is_dir():
        raise NotADirectoryError(f"节目录不存在或不是目录: {section_dir}")

    resolved_case = case_name or section_dir.parent.name

    parsed: list[ParsedFile] = []
    skipped: list[str] = []

    for entry in sorted(section_dir.iterdir()):
        if not entry.is_file():
            continue
        suffix = _normalized_suffix(entry)
        file_type = EXTENSION_TO_TYPE.get(suffix)
        if file_type is not None:
            parsed.append(_PARSERS[file_type](entry))
        elif suffix in MEDIA_EXTENSIONS:
            skipped.append(entry.name)
        # 其余文件（.DS_Store 等）静默忽略

    return RawSection(
        case_name=resolved_case,
        section_name=section_dir.name,
        section_dir=_relative_to_cases(section_dir),
        files=tuple(parsed),
        skipped_media=tuple(skipped),
    )


def iter_section_dirs(cases_dir: Path = CASES_DIR) -> Iterator[Path]:
    """发现所有「节」目录：含至少一个受支持素材文件的目录。

    按目录名排序，递归遍历，便于后续整库批处理与稳定的产物顺序。
    """
    supported = set(EXTENSION_TO_TYPE)
    for path in sorted(cases_dir.rglob("*")):
        if not path.is_dir():
            continue
        has_supported = any(
            child.is_file() and _normalized_suffix(child) in supported
            for child in path.iterdir()
        )
        if has_supported:
            yield path
