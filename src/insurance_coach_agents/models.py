"""数据契约：流水线各阶段之间传递的不可变数据对象。

M1 仅实现解析层所需的 ``FileType`` / ``ParsedFile`` / ``RawSection``。
后续里程碑会在此扩展 ``Assessment`` / ``ExtractedDoc`` / ``CuratedDoc``。

所有数据类均为 ``frozen``（不可变），集合字段用 ``tuple`` 而非 ``list``，
以遵循项目的不可变数据流原则。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _coerce_str_list(value: object) -> object:
    """把 LLM 偶尔返回的「JSON 字符串形式的列表」规整回真正的 list。

    部分模型（如 qwen）的结构化输出会把 list 字段序列化成字符串
    （如 ``'["a", "b"]'`` 甚至单条文本），这里在 pydantic 校验前做兼容。
    """
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            return [stripped]
        return parsed if isinstance(parsed, list) else [stripped]
    return value


class FileType(str, Enum):
    """参与解析的素材文件类型。"""

    DOCX = "docx"
    PPTX = "pptx"
    PDF = "pdf"
    TXT = "txt"


@dataclass(frozen=True)
class ParsedFile:
    """单个素材文件的解析结果。

    ``text`` 为解析出的文本：docx/pdf 会尽量保留标题层级与表格（Markdown 化），
    txt 为清洗后的转写文本，pptx 为按页聚合的要点文本。
    """

    file_type: FileType
    filename: str
    text: str
    warnings: tuple[str, ...] = ()

    @property
    def char_count(self) -> int:
        """解析文本的字符数（派生值，不单独存储）。"""
        return len(self.text)

    @property
    def is_empty(self) -> bool:
        return self.char_count == 0


@dataclass(frozen=True)
class RawSection:
    """一个「节」的聚合解析结果——流水线的最小处理单元。

    一个节目录通常包含 docx（主干）/ pptx / pdf / txt 等多个文件，
    以及被跳过的音视频媒体。
    """

    case_name: str
    section_name: str
    section_dir: str
    files: tuple[ParsedFile, ...]
    skipped_media: tuple[str, ...] = ()

    def files_of(self, file_type: FileType) -> tuple[ParsedFile, ...]:
        """返回指定类型的全部已解析文件。"""
        return tuple(f for f in self.files if f.file_type is file_type)

    def first_text_of(self, file_type: FileType) -> str | None:
        """返回指定类型首个文件的文本，没有则返回 None。"""
        for f in self.files:
            if f.file_type is file_type and not f.is_empty:
                return f.text
        return None

    @property
    def primary_text(self) -> str | None:
        """主干文本：按 docx → pdf → pptx → txt 的优先级取首个非空文本。

        docx 是人工整理过的结构化讲义，质量最高，故优先级最高。
        """
        for file_type in (FileType.DOCX, FileType.PDF, FileType.PPTX, FileType.TXT):
            text = self.first_text_of(file_type)
            if text is not None:
                return text
        return None

    @property
    def total_chars(self) -> int:
        return sum(f.char_count for f in self.files)


# ---- LLM 产出契约（pydantic，用于结构化输出与 JSON 序列化）----

# 内容对某个下游智能体的价值等级。
ValueLevel = Literal["high", "mid", "low", "none"]


class ServesRating(BaseModel):
    """内容对四个下游智能体的价值评级。"""

    model_config = ConfigDict(frozen=True)

    qa: ValueLevel = Field(description="对【问答专业智能体】的价值")
    recommend: ValueLevel = Field(description="对【推荐专业智能体】的价值")
    exam: ValueLevel = Field(description="对【AI 组卷智能体】的价值")
    roleplay: ValueLevel = Field(description="对【剧本生成/陪练智能体】的价值")


class Assessment(BaseModel):
    """AssessorAgent 的研判结论。"""

    model_config = ConfigDict(frozen=True)

    worth_storing: bool = Field(description="这段内容是否值得沉淀进保险知识向量库")
    reason: str = Field(description="给出值得 / 不值得入库的具体理由，需结合内容本身")
    topics: list[str] = Field(
        default_factory=list,
        description="主题标签，如 主顾开拓 / 需求面谈 / 异议处理 / 产品讲解 / 客户经营 / 增员 等",
    )
    serves: ServesRating = Field(description="对四个下游智能体的价值评级")
    value_score: float = Field(
        ge=0.0, le=1.0, description="综合入库价值评分，0~1，越高越值得沉淀"
    )

    @field_validator("topics", mode="before")
    @classmethod
    def _coerce_topics(cls, v: object) -> object:
        return _coerce_str_list(v)


class ExtractedDoc(BaseModel):
    """ExtractorAgent 的提取产物：标准化 Markdown 正文（不含 frontmatter）。"""

    model_config = ConfigDict(frozen=True)

    title: str = Field(description="知识单元标题（取课程/章节主题）")
    body_markdown: str = Field(description="带一二级标题的标准化 Markdown 正文")


class ReviewResult(BaseModel):
    """ReviewerAgent 的质检结论：对提取稿的规范性与信息保真做审计。"""

    model_config = ConfigDict(frozen=True)

    passed: bool = Field(description="整体是否通过质检（无严重问题）")
    heading_ok: bool = Field(
        description="Markdown 标题层级是否规范（有唯一一级标题、层级不跳级、无代码围栏残留）"
    )
    fidelity_ok: bool = Field(
        description="正文是否忠于素材：无明显杜撰的事实/数字，关键话术与流程无严重遗漏"
    )
    no_meta_leak: bool = Field(
        description="是否没有元注释/加工旁白泄漏（如『基于讲义框架』『未做虚构』之类）"
    )
    issues: list[str] = Field(
        default_factory=list, description="发现的具体问题列表，逐条说明"
    )
    score: float = Field(
        ge=0.0, le=1.0, description="整理质量综合评分，0~1，越高越好"
    )

    @field_validator("issues", mode="before")
    @classmethod
    def _coerce_issues(cls, v: object) -> object:
        return _coerce_str_list(v)
