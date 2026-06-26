"""鲁棒结构化输出：容错第三方 thinking 模型的工具调用怪癖。

本平台的文本模型（deepseek 等）走 thinking 模式，结构化输出有两个已知坑：

1. 不支持强制（forced）``tool_choice``：默认强制会被平台以 400 拒绝。
2. ``auto`` 模式下偶发把全部字段多包一层外层键返回（实测见过 ``output`` /
   ``structured_output`` 等不固定键名），导致 AgentScope 内置校验直接失败。

AgentScope 默认在 ``_call_api_with_structured_output`` 内部即对目标模型
``model_validate``，调用方拿不到原始 dict、无法补救。``RobustOpenAIChatModel``
覆写该方法：固定走 ``auto``、自行提取工具参数、启发式解包单键嵌套、用 pydantic
严格校验，并在校验失败时重试若干次（覆盖偶发的格式抖动）。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Type

import jsonschema
from pydantic import BaseModel, ValidationError

from agentscope._utils._common import _json_loads_with_repair
from agentscope.exception import ToolJSONDecodeError
from agentscope.message import Msg, TextBlock, UserMsg
from agentscope.model import ChatResponse, OpenAIChatModel, StructuredResponse
from agentscope.tool import ToolChoice

# 工具名沿用 AgentScope 约定，便于模型按既有训练直觉调用。
_FUNC_NAME = "generate_structured_output"
# 格式抖动重试次数：实测约 1/3 概率出现嵌套，3 次足以高概率命中一次干净输出。
_STRUCTURED_MAX_ATTEMPTS = 3

_INSTRUCTION = (
    f"<system-reminder>Now you **MUST** call the tool named '{_FUNC_NAME}' "
    "to generate the structured output required by the user. Provide the "
    "fields directly as the tool arguments; do NOT wrap them in any extra "
    "key. DON'T do anything else.</system-reminder>"
)


def _schema_of(structured_model: Type[BaseModel] | dict) -> dict:
    """取目标模型的 JSON Schema（pydantic 模型或已是 dict 的 schema）。"""
    if isinstance(structured_model, dict):
        return structured_model
    return structured_model.model_json_schema()


def _field_names(structured_model: Type[BaseModel] | dict) -> set[str]:
    """取目标模型的顶层字段名集合，用于判断单键嵌套。"""
    if isinstance(structured_model, dict):
        return set((structured_model.get("properties") or {}).keys())
    return set(structured_model.model_fields)


def _unwrap_single_key(
    data: dict, structured_model: Type[BaseModel] | dict
) -> dict:
    """解包模型偶发的单层嵌套（如 ``{"output": {...真实字段...}}``）。

    仅当 data 是单键 dict、键名不属于目标模型的真实字段、且其值是 dict 时才解包；
    真实模型均为多字段，单键包裹几乎必为模型抖动，故此启发式安全。
    """
    if not isinstance(data, dict) or len(data) != 1:
        return data
    (only_key, inner), = data.items()
    if isinstance(inner, dict) and only_key not in _field_names(structured_model):
        return inner
    return data


def _extract_tool_args(response: ChatResponse, schema: dict) -> dict | None:
    """从响应中取出名为 ``_FUNC_NAME`` 的工具调用参数并解析为 dict。

    兼容块对象与 dict 两种形态；参数为 JSON 字符串时用 AgentScope 的
    ``_json_loads_with_repair`` 容错解析（可修复不完整 JSON）。
    """
    content = getattr(response, "content", None)
    if content is None and hasattr(response, "get"):
        content = response.get("content")
    for block in content or []:
        b_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        name = getattr(block, "name", None) or (
            block.get("name") if isinstance(block, dict) else None
        )
        if b_type != "tool_call" or name != _FUNC_NAME:
            continue
        raw = getattr(block, "input", None)
        if raw is None and isinstance(block, dict):
            raw = block.get("input")
        if isinstance(raw, str):
            return _json_loads_with_repair(raw, schema)
        if isinstance(raw, dict):
            return raw
    return None


def _validate(data: dict, structured_model: Type[BaseModel] | dict) -> None:
    """按目标类型做严格校验；失败时抛出对应的 ValidationError。"""
    if isinstance(structured_model, dict):
        jsonschema.validate(data, structured_model)
    else:
        structured_model.model_validate(data)


class RobustOpenAIChatModel(OpenAIChatModel):
    """对第三方 thinking 模型做结构化输出容错的 ``OpenAIChatModel`` 子类。

    仅覆写结构化输出路径；普通文本调用（``__call__``，如视觉识别 / 提取）行为不变。
    依赖 ``stream=False``（本项目固定如此）以一次性拿到完整 ``ChatResponse``。
    """

    async def _call_api_with_structured_output(
        self,
        model_name: str,
        messages: list[Msg],
        structured_model: Type[BaseModel] | dict,
        tool_choice: ToolChoice | None = None,  # 忽略：thinking 模型只能用 auto
        **kwargs: Any,
    ) -> StructuredResponse:
        schema = _schema_of(structured_model)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": _FUNC_NAME,
                    "description": "Call this function to generate "
                    "structured output required by the user.",
                    "parameters": schema,
                },
            }
        ]
        convo = deepcopy(messages)
        reminder = TextBlock(text=_INSTRUCTION)
        if convo and convo[-1].role == "user":
            convo[-1].content = convo[-1].get_content_blocks() + [reminder]
        else:
            convo.append(UserMsg(name="user", content=[reminder]))

        last_error: Exception | None = None
        for _ in range(_STRUCTURED_MAX_ATTEMPTS):
            response = await self(
                convo,
                tools=tools,
                tool_choice=ToolChoice(mode="auto"),
                **kwargs,
            )
            try:
                data = _extract_tool_args(response, schema)
            except (ToolJSONDecodeError, ValueError) as exc:
                # 模型生成的工具参数 JSON 非法且无法修复（偶发，如长中文串内
                # 未转义引号）：本次作废，重试让模型重新生成。
                last_error = exc
                continue
            if data is None:
                last_error = RuntimeError(
                    "模型未调用结构化输出工具，无法解析结构化结果。"
                )
                continue
            data = _unwrap_single_key(data, structured_model)
            try:
                _validate(data, structured_model)
            except (ValidationError, jsonschema.ValidationError) as exc:
                last_error = exc
                continue
            return StructuredResponse(
                content=data,
                id=getattr(response, "id", ""),
                created_at=getattr(response, "created_at", ""),
                usage=getattr(response, "usage", None),
            )

        raise last_error or RuntimeError("结构化输出失败：已达最大重试次数。")
