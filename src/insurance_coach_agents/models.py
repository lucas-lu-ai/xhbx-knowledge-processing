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


def _coerce_model_list(value: object) -> object:
    """把 LLM 偶尔返回的 JSON 字符串形式列表规整为 list。"""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            return value
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return parsed
    if isinstance(value, dict):
        return [value]
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


# ---- 销售策略 / 话术提取契约 ----

ConfidenceLevel = Literal["high", "mid", "low"]
DEFAULT_COMPLIANCE_NOTE = "未识别到特定合规风险，仍需以公司合规要求和正式条款为准。"


class SalesEvidenceRef(BaseModel):
    """销售证据的来源引用，尽量指向节、文件和原文片段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section_name: str = Field(default="", description="证据所在章节")
    source_id: str = Field(default="", description="来源 ID，如 provenance 中的 source_id")
    filename: str = Field(default="", description="来源文件名")
    quote: str = Field(default="", description="支撑该证据的短原文")


class CustomerSignal(BaseModel):
    """客户状态、触发点或需求信号。"""

    model_config = ConfigDict(frozen=True)

    signal: str = Field(description="客户信号，如保障意识弱、预算顾虑、健康风险关注")
    evidence: str = Field(description="素材中支撑该信号的内容")
    source_refs: list[SalesEvidenceRef] = Field(default_factory=list)

    @field_validator("source_refs", mode="before")
    @classmethod
    def _coerce_source_refs(cls, v: object) -> object:
        return _coerce_model_list(v)


class SalesAction(BaseModel):
    """销售人员采取的动作。"""

    model_config = ConfigDict(frozen=True)

    action: str = Field(description="销售动作")
    stage_hint: str = Field(default="", description="阶段线索，如售前/需求面谈/异议处理/促成")
    evidence: str = Field(description="素材中支撑该动作的内容")
    source_refs: list[SalesEvidenceRef] = Field(default_factory=list)

    @field_validator("source_refs", mode="before")
    @classmethod
    def _coerce_source_refs(cls, v: object) -> object:
        return _coerce_model_list(v)


class ScriptQuote(BaseModel):
    """素材中的原始话术。"""

    model_config = ConfigDict(frozen=True)

    quote: str = Field(description="原始话术")
    speaker: str = Field(default="", description="说话人，如 sales/customer/trainer")
    stage_hint: str = Field(default="", description="阶段线索")
    scenario_hint: str = Field(default="", description="场景线索")
    source_refs: list[SalesEvidenceRef] = Field(default_factory=list)

    @field_validator("source_refs", mode="before")
    @classmethod
    def _coerce_source_refs(cls, v: object) -> object:
        return _coerce_model_list(v)


class ObjectionEvidence(BaseModel):
    """客户异议和素材中的应对证据。"""

    model_config = ConfigDict(frozen=True)

    objection: str = Field(description="客户异议")
    response_evidence: str = Field(description="素材中出现的应对方式或话术")
    source_refs: list[SalesEvidenceRef] = Field(default_factory=list)

    @field_validator("source_refs", mode="before")
    @classmethod
    def _coerce_source_refs(cls, v: object) -> object:
        return _coerce_model_list(v)


class StrategyCandidate(BaseModel):
    """从单节证据中识别出的候选销售策略。"""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="候选策略名称")
    reason: str = Field(description="为什么认为素材体现了该策略")
    confidence: ConfidenceLevel = Field(description="置信度")
    inferred: bool = Field(default=True, description="是否由模型归纳推断")
    source_refs: list[SalesEvidenceRef] = Field(default_factory=list)

    @field_validator("source_refs", mode="before")
    @classmethod
    def _coerce_source_refs(cls, v: object) -> object:
        return _coerce_model_list(v)


class SectionSalesEvidence(BaseModel):
    """单节销售证据：保真采集，不做整案策略定论。"""

    model_config = ConfigDict(frozen=True)

    case_name: str
    section_name: str
    customer_signals: list[CustomerSignal] = Field(default_factory=list)
    sales_actions: list[SalesAction] = Field(default_factory=list)
    script_quotes: list[ScriptQuote] = Field(default_factory=list)
    objections: list[ObjectionEvidence] = Field(default_factory=list)
    strategy_candidates: list[StrategyCandidate] = Field(default_factory=list)

    @field_validator(
        "customer_signals",
        "sales_actions",
        "script_quotes",
        "objections",
        "strategy_candidates",
        mode="before",
    )
    @classmethod
    def _coerce_lists(cls, v: object) -> object:
        return _coerce_model_list(v)


class CustomerJourneyStep(BaseModel):
    """案例级客户旅程步骤。"""

    model_config = ConfigDict(frozen=True)

    stage: str = Field(description="销售阶段")
    customer_state: str = Field(description="该阶段客户状态")
    sales_goal: str = Field(description="该阶段销售目标")
    key_actions: list[str] = Field(default_factory=list)
    evidence_refs: list[SalesEvidenceRef] = Field(default_factory=list)

    @field_validator("key_actions", mode="before")
    @classmethod
    def _coerce_key_actions(cls, v: object) -> object:
        return _coerce_str_list(v)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def _coerce_evidence_refs(cls, v: object) -> object:
        return _coerce_model_list(v)


class CaseSalesStrategy(BaseModel):
    """案例级销售策略。"""

    model_config = ConfigDict(frozen=True)

    name: str
    aliases: list[str] = Field(default_factory=list)
    definition: str
    applicable_stages: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    do: list[str] = Field(default_factory=list)
    dont: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel
    inferred: bool = True
    evidence_refs: list[SalesEvidenceRef] = Field(default_factory=list)

    @field_validator("aliases", "applicable_stages", "steps", "do", "dont", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: object) -> object:
        return _coerce_str_list(v)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def _coerce_evidence_refs(cls, v: object) -> object:
        return _coerce_model_list(v)


class CaseSalesScript(BaseModel):
    """案例级场景化话术。"""

    model_config = ConfigDict(frozen=True)

    script_id: str
    stage: str
    scenario: str
    customer_trigger: str
    goal: str
    source_quote: str
    coach_wording: str
    strategy_names: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    compliance_notes: list[str] = Field(default_factory=list, validate_default=True)
    evidence_refs: list[SalesEvidenceRef] = Field(default_factory=list)

    @field_validator(
        "strategy_names",
        "follow_up_questions",
        "compliance_notes",
        mode="before",
    )
    @classmethod
    def _coerce_str_lists(cls, v: object) -> object:
        return _coerce_str_list(v)

    @field_validator("compliance_notes", mode="after")
    @classmethod
    def _default_compliance_notes(cls, v: list[str]) -> list[str]:
        if any(note.strip() for note in v):
            return v
        return [DEFAULT_COMPLIANCE_NOTE]

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def _coerce_evidence_refs(cls, v: object) -> object:
        return _coerce_model_list(v)


class ObjectionHandling(BaseModel):
    """案例级异议处理建议。"""

    model_config = ConfigDict(frozen=True)

    objection: str
    diagnosis: str
    recommended_response: str
    related_strategy_names: list[str] = Field(default_factory=list)
    related_script_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[SalesEvidenceRef] = Field(default_factory=list)

    @field_validator("related_strategy_names", "related_script_ids", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: object) -> object:
        return _coerce_str_list(v)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def _coerce_evidence_refs(cls, v: object) -> object:
        return _coerce_model_list(v)


class CaseSalesInsights(BaseModel):
    """完整案例级销售洞察。"""

    model_config = ConfigDict(frozen=True)

    case_name: str
    case_summary: str
    customer_journey: list[CustomerJourneyStep] = Field(default_factory=list)
    strategies: list[CaseSalesStrategy] = Field(default_factory=list)
    scripts: list[CaseSalesScript] = Field(default_factory=list)
    objection_handling: list[ObjectionHandling] = Field(default_factory=list)

    @field_validator(
        "customer_journey",
        "strategies",
        "scripts",
        "objection_handling",
        mode="before",
    )
    @classmethod
    def _coerce_lists(cls, v: object) -> object:
        return _coerce_model_list(v)
