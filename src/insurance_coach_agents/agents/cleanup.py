"""产出文本清洗：剥离模型副产物，统一格式。

针对抽查发现的三类问题：
1. 正文混入模型"元注释"（对自身加工过程的说明）；
2. ``reason`` 字段末尾残留 ``\"\"\"`` / ``` 等围栏符；
3. 列表符不统一（``*   `` 应为 ``- ``）。

均为纯函数，便于单测。
"""

from __future__ import annotations

import re

# 模型自述加工过程的关键词——这些词不会出现在正当的保险知识正文里，
# 一旦整行包含即视为元注释予以删除。
_META_KEYWORDS = (
    "转写稿",
    "讲义框架",
    "原始素材",
    "未做扩展",
    "未做虚构",
    "未作虚构",
    "并未虚构",
    "不做虚构",
    "为避免虚构",
    "基于讲义",
    "结合转写",
    "以下内容基于",
    "以下内容根据",
    "本整理",
    "本文档基于",
    "加工过程",
)

_LIST_MARKER_RE = re.compile(r"^(\s*)\*\s+", re.MULTILINE)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_CODE_FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """去掉模型偶尔多包的整体代码围栏。"""
    match = _CODE_FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text.strip()


def _is_meta_line(line: str) -> bool:
    """判断某行是否为模型自述加工过程的元注释。"""
    stripped = line.strip().strip("（）()【】[]")
    return any(keyword in stripped for keyword in _META_KEYWORDS)


def clean_markdown_body(text: str) -> str:
    """清洗提取出的 Markdown 正文。

    顺序：剥离整体代码围栏 → 删除元注释整行 → 统一列表符 → 归并多余空行。
    """
    body = _strip_code_fence(text)
    kept = [line for line in body.splitlines() if not _is_meta_line(line)]
    body = "\n".join(kept)
    body = _LIST_MARKER_RE.sub(r"\1- ", body)
    body = _MULTI_BLANK_RE.sub("\n\n", body)
    return body.strip()


def clean_reason(text: str) -> str:
    """剥离 reason 字段首尾残留的 ``\"\"\"`` / ``` 围栏符。"""
    result = text.strip()
    for fence in ('"""', "```"):
        if result.startswith(fence):
            result = result[len(fence):]
        if result.endswith(fence):
            result = result[: -len(fence)]
    return result.strip()
