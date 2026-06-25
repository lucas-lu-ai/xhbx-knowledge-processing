"""智能体层：研判 / 提取 / 切分 / 质检。

M2 实现 ``AssessorAgent``（研判 + 理由）与 ``ExtractorAgent``（→ 标准 Markdown）。
二者均为单轮 LLM 调用，直接使用 AgentScope 的 model 层（``generate_structured_output``
与 ``__call__``），不引入 ReAct 多轮工具循环。
"""

from .assessor import AssessorAgent
from .extractor import ExtractorAgent
from .factory import build_chat_model, response_text

__all__ = [
    "AssessorAgent",
    "ExtractorAgent",
    "build_chat_model",
    "response_text",
]
