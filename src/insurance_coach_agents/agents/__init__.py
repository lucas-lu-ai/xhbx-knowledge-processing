"""智能体层：研判 / 提取 / 切分 / 质检 / 返修 / 销售洞察。

M2 实现 ``AssessorAgent``（研判 + 理由）与 ``ExtractorAgent``（→ 标准 Markdown）。
二者均为单轮 LLM 调用，直接使用 AgentScope 的 model 层（``generate_structured_output``
与 ``__call__``），不引入 ReAct 多轮工具循环。
销售洞察智能体负责从节级素材采集销售证据，并整合同一案例的证据生成策略与话术洞察。
"""

from .assessor import AssessorAgent
from .enrich import enrich_section_with_vision
from .extractor import ExtractorAgent
from .factory import build_chat_model, build_vision_model, response_text
from .reviser import ReviserAgent
from .reviewer import ReviewerAgent
from .sales_insights import CaseSalesInsightAgent, SectionSalesEvidenceAgent
from .vision import ImageDescriber

__all__ = [
    "AssessorAgent",
    "CaseSalesInsightAgent",
    "ExtractorAgent",
    "ImageDescriber",
    "ReviserAgent",
    "ReviewerAgent",
    "SectionSalesEvidenceAgent",
    "build_chat_model",
    "build_vision_model",
    "enrich_section_with_vision",
    "response_text",
]
