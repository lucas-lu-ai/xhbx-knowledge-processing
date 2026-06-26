"""``structured_model`` 的单元测试：解包、提取与校验重试。

不调用真实 API：用 ``RobustOpenAIChatModel`` 子类替身覆盖 ``__call__``，
喂入预设的 ``ChatResponse`` 序列，验证容错与重试逻辑。
"""

from __future__ import annotations

import asyncio
import json

import pytest
from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import TextBlock, ToolCallBlock, UserMsg
from agentscope.model import ChatResponse

from insurance_coach_agents.agents.structured_model import (
    RobustOpenAIChatModel,
    _extract_tool_args,
    _unwrap_single_key,
)
from insurance_coach_agents.models import Assessment

_FUNC = "generate_structured_output"

_VALID = {
    "worth_storing": True,
    "reason": "包含完整面谈流程",
    "topics": ["需求面谈"],
    "serves": {"qa": "high", "recommend": "mid", "exam": "low", "roleplay": "high"},
    "value_score": 0.8,
}


def _tool_response(args: dict) -> ChatResponse:
    block = ToolCallBlock(
        type="tool_call", id="c1", name=_FUNC, input=json.dumps(args)
    )
    return ChatResponse(content=[block], is_last=True)


def _text_response() -> ChatResponse:
    return ChatResponse(content=[TextBlock(text="没有调用工具")], is_last=True)


class _StubModel(RobustOpenAIChatModel):
    """按序返回预设响应的替身；记录被调用次数。"""

    def __init__(self, responses: list[ChatResponse]) -> None:
        super().__init__(
            credential=OpenAICredential(api_key="x", base_url="http://x"),
            model="m",
            formatter=OpenAIChatFormatter(),
            stream=False,
        )
        self._responses = responses
        self.calls = 0

    async def __call__(self, messages, tools=None, tool_choice=None, **kwargs):
        response = self._responses[self.calls]
        self.calls += 1
        return response


def _messages():
    return [UserMsg(name="user", content=[TextBlock(text="请研判这段内容")])]


# ---- 纯函数：解包 ----


def test_unwrap_extracts_inner_when_single_unknown_key():
    nested = {"output": _VALID}
    assert _unwrap_single_key(nested, Assessment) == _VALID


def test_unwrap_keeps_multi_field_payload_untouched():
    assert _unwrap_single_key(_VALID, Assessment) == _VALID


def test_unwrap_keeps_single_key_that_is_a_real_field():
    # 'reason' 是 Assessment 的真实字段，不应被误解包
    payload = {"reason": {"nested": "x"}}
    assert _unwrap_single_key(payload, Assessment) == payload


# ---- 纯函数：提取工具参数 ----


def test_extract_tool_args_parses_json_string():
    schema = Assessment.model_json_schema()
    assert _extract_tool_args(_tool_response({"a": 1}), schema) == {"a": 1}


def test_extract_tool_args_returns_none_without_tool_call():
    schema = Assessment.model_json_schema()
    assert _extract_tool_args(_text_response(), schema) is None


# ---- 模型：解包 + 重试 ----


def test_structured_unwraps_nested_output_in_one_call():
    model = _StubModel([_tool_response({"output": _VALID})])
    result = asyncio.run(
        model._call_api_with_structured_output("m", _messages(), Assessment)
    )
    assert result.content["worth_storing"] is True
    assert model.calls == 1


def test_structured_retries_until_valid():
    model = _StubModel([_tool_response({"foo": "bar"}), _tool_response(_VALID)])
    result = asyncio.run(
        model._call_api_with_structured_output("m", _messages(), Assessment)
    )
    assert result.content["value_score"] == 0.8
    assert model.calls == 2


def test_structured_retries_on_invalid_json():
    # 模型偶发生成无法修复的非法 JSON（如纯文本）：应作废本次并重试，而非崩溃
    bad = ToolCallBlock(
        type="tool_call", id="c0", name=_FUNC, input="好的，我已完成质检。"
    )
    bad_response = ChatResponse(content=[bad], is_last=True)
    model = _StubModel([bad_response, _tool_response(_VALID)])
    result = asyncio.run(
        model._call_api_with_structured_output("m", _messages(), Assessment)
    )
    assert result.content["worth_storing"] is True
    assert model.calls == 2


def test_structured_raises_after_exhausting_attempts():
    model = _StubModel([_text_response(), _text_response(), _text_response()])
    with pytest.raises(Exception):
        asyncio.run(
            model._call_api_with_structured_output("m", _messages(), Assessment)
        )
    assert model.calls == 3
