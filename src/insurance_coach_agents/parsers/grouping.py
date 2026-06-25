"""分组策略层：把一堆素材文件归并为「知识单元」。

当前数据有层级（案例/节/文件），用 ``group_by_directory``（一个目录 = 一个单元）。
未来文件可能被拍平、互不相关，用 ``group_by_single_file``（一个文件 = 一个单元，最稳兜底）。

无论哪种策略，都产出 ``SourceGroup`` 列表；``load_group`` 再把一组文件解析为
``RawSection``，下游研判 / 提取 / 落盘完全不感知分组方式。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import CASES_DIR, EXTENSION_TO_TYPE, MEDIA_EXTENSIONS
from ..models import ParsedFile, RawSection
from .section_loader import parse_file


@dataclass(frozen=True)
class SourceGroup:
    """一个待处理的知识单元：一组同属一个单元的素材文件。"""

    case_name: str
    unit_name: str
    identifier: str
    file_paths: tuple[Path, ...]
    skipped_media: tuple[str, ...] = ()


def _suffix(path: Path) -> str:
    return path.suffix.lower()


def _relative_id(path: Path) -> str:
    """相对绩优案例根的路径标识；不在其下时返回绝对路径。"""
    try:
        return str(path.resolve().relative_to(CASES_DIR.resolve()))
    except ValueError:
        return str(path)


def group_by_directory(cases_dir: Path = CASES_DIR) -> list[SourceGroup]:
    """目录分组：每个含受支持文件的目录 = 一个知识单元。"""
    groups: list[SourceGroup] = []
    for path in sorted(cases_dir.rglob("*")):
        if not path.is_dir():
            continue
        files: list[Path] = []
        media: list[str] = []
        for child in sorted(path.iterdir()):
            if not child.is_file():
                continue
            suffix = _suffix(child)
            if suffix in EXTENSION_TO_TYPE:
                files.append(child)
            elif suffix in MEDIA_EXTENSIONS:
                media.append(child.name)
        if files:
            groups.append(
                SourceGroup(
                    case_name=path.parent.name,
                    unit_name=path.name,
                    identifier=_relative_id(path),
                    file_paths=tuple(files),
                    skipped_media=tuple(media),
                )
            )
    return groups


def group_by_single_file(root: Path = CASES_DIR) -> list[SourceGroup]:
    """单文件分组：每个受支持文件 = 一个独立知识单元（拍平数据的兜底）。"""
    groups: list[SourceGroup] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and _suffix(path) in EXTENSION_TO_TYPE:
            groups.append(
                SourceGroup(
                    case_name=path.parent.name,
                    unit_name=path.stem,
                    identifier=_relative_id(path),
                    file_paths=(path,),
                )
            )
    return groups


def load_group(group: SourceGroup) -> RawSection:
    """把一个 ``SourceGroup`` 的文件解析为 ``RawSection``。"""
    parsed: list[ParsedFile] = []
    for path in group.file_paths:
        result = parse_file(path)
        if result is not None:
            parsed.append(result)
    return RawSection(
        case_name=group.case_name,
        section_name=group.unit_name,
        section_dir=group.identifier,
        files=tuple(parsed),
        skipped_media=group.skipped_media,
    )
