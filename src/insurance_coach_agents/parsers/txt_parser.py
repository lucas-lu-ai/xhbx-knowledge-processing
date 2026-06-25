"""解析 txt 音频转写稿。

转写稿为逐行短句、缺标点、含口语冗余。此处只做保守清洗（去空行、归一空白），
不做激进改写，避免破坏原始口语信息——口语金句的提炼交由下游 LLM。
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import FileType, ParsedFile

_WS_RE = re.compile(r"[ \t　]+")


def parse_txt(path: Path) -> ParsedFile:
    """读取并保守清洗 txt 转写稿为 ``ParsedFile``。"""
    filename = path.name
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            raw = path.read_text(encoding="gbk")
        except Exception as exc:  # noqa: BLE001
            return ParsedFile(
                file_type=FileType.TXT,
                filename=filename,
                text="",
                warnings=(f"txt 解码失败: {exc}",),
            )
    except Exception as exc:  # noqa: BLE001
        return ParsedFile(
            file_type=FileType.TXT,
            filename=filename,
            text="",
            warnings=(f"txt 读取失败: {exc}",),
        )

    lines = [_WS_RE.sub(" ", line).strip() for line in raw.splitlines()]
    cleaned = "\n".join(line for line in lines if line)

    warnings = () if cleaned else ("txt 内容为空",)
    return ParsedFile(
        file_type=FileType.TXT, filename=filename, text=cleaned, warnings=warnings
    )
