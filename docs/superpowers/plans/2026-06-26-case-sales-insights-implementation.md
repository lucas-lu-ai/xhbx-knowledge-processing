# Case Sales Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a case-level sales insight extraction flow that turns one full insurance performance case into structured strategies, scripts, objections, and a human-reviewable playbook.

**Architecture:** Add sales-specific Pydantic contracts, two structured-output agents, deterministic sidecar writers, and a case-level pipeline that aggregates all sections in one case. Keep this separate from the existing Markdown extraction path so current `run` and `build` behavior remains stable.

**Tech Stack:** Python 3.12, Pydantic v2, AgentScope `OpenAIChatModel.generate_structured_output`, existing fake-model pytest pattern, JSON/Markdown sidecar files.

---

## File Structure

- Modify `src/insurance_coach_agents/models.py`: add sales evidence and case insight Pydantic contracts.
- Modify `src/insurance_coach_agents/agents/prompts.py`: add sales evidence and case insight system prompts.
- Create `src/insurance_coach_agents/agents/sales_insights.py`: implement `SectionSalesEvidenceAgent`, `CaseSalesInsightAgent`, and rendering helpers.
- Modify `src/insurance_coach_agents/agents/__init__.py`: export the new agents.
- Create `src/insurance_coach_agents/sales_output_writer.py`: write `<节>.sales_evidence.json`, `case.sales_insights.json`, and `case.sales_playbook.md`.
- Create `src/insurance_coach_agents/sales_pipeline.py`: orchestrate a full case across all section groups.
- Modify `src/insurance_coach_agents/cli.py`: add `sales-insights "<案例>"` CLI command.
- Modify `README.md`: document the new command and outputs.
- Create `tests/test_sales_insight_models.py`: data-contract tests.
- Create `tests/test_sales_insight_agents.py`: fake-model tests for the agents.
- Create `tests/test_sales_output_writer.py`: deterministic writer tests.
- Create `tests/test_sales_pipeline.py`: case-level orchestration tests.
- Create `tests/test_cli_sales_insights.py`: CLI group selection and command wiring tests.

This first implementation intentionally does not build the global `sales_playbook/*.jsonl` normalizer. It produces the case-level JSON and Markdown needed to validate the design with real cases.

---

### Task 1: Sales Insight Data Contracts

**Files:**
- Modify: `src/insurance_coach_agents/models.py`
- Create: `tests/test_sales_insight_models.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/test_sales_insight_models.py`:

```python
"""销售策略/话术提取的数据契约测试。"""

from __future__ import annotations

from insurance_coach_agents.models import (
    CaseSalesInsights,
    CaseSalesScript,
    CustomerJourneyStep,
    SectionSalesEvidence,
    StrategyCandidate,
)


def test_section_sales_evidence_accepts_structured_lists():
    evidence = SectionSalesEvidence(
        case_name="案例A",
        section_name="第1节",
        customer_signals=[
            {
                "signal": "客户保障意识弱",
                "evidence": "客户说暂时不需要保险",
                "source_refs": [{"section_name": "第1节", "quote": "暂时不需要"}],
            }
        ],
        sales_actions=[
            {
                "action": "用家庭责任引导风险意识",
                "stage_hint": "售前",
                "evidence": "销售人员继续追问家庭责任",
                "source_refs": [],
            }
        ],
        script_quotes=[
            {
                "quote": "您现在最担心家庭哪方面风险？",
                "speaker": "sales",
                "stage_hint": "售前",
                "scenario_hint": "风险唤醒",
                "source_refs": [],
            }
        ],
        objections=[],
        strategy_candidates=[
            {
                "name": "风险唤醒",
                "reason": "围绕家庭责任和风险缺口展开",
                "confidence": "mid",
                "inferred": True,
                "source_refs": [],
            }
        ],
    )

    assert evidence.case_name == "案例A"
    assert evidence.customer_signals[0].signal == "客户保障意识弱"
    assert evidence.script_quotes[0].speaker == "sales"
    assert isinstance(evidence.strategy_candidates[0], StrategyCandidate)


def test_section_sales_evidence_coerces_json_string_lists():
    evidence = SectionSalesEvidence(
        case_name="案例A",
        section_name="第1节",
        customer_signals='[{"signal":"预算有限","evidence":"客户担心保费","source_refs":[]}]',
        sales_actions="[]",
        script_quotes="[]",
        objections="[]",
        strategy_candidates="[]",
    )

    assert evidence.customer_signals[0].signal == "预算有限"
    assert evidence.sales_actions == []


def test_case_sales_insights_accepts_journey_strategy_scripts_and_objections():
    insights = CaseSalesInsights(
        case_name="案例A",
        case_summary="完整案例围绕风险唤醒和需求面谈展开。",
        customer_journey=[
            {
                "stage": "售前",
                "customer_state": "保障意识弱",
                "sales_goal": "引发风险关注",
                "key_actions": ["场景提问", "家庭责任引导"],
                "evidence_refs": [],
            }
        ],
        strategies=[
            {
                "name": "风险唤醒式需求面谈",
                "aliases": ["风险唤醒"],
                "definition": "通过生活场景和家庭责任引导客户意识到保障缺口。",
                "applicable_stages": ["售前", "需求面谈"],
                "steps": ["场景切入", "风险追问", "缺口确认"],
                "do": ["先接纳客户现状"],
                "dont": ["不要承诺收益或理赔结果"],
                "confidence": "high",
                "inferred": True,
                "evidence_refs": [],
            }
        ],
        scripts=[
            {
                "script_id": "script_001",
                "stage": "售前",
                "scenario": "客户保险意识弱",
                "customer_trigger": "客户认为现在不需要保险",
                "goal": "吸引客户进入需求沟通",
                "source_quote": "原始话术",
                "coach_wording": "教练推荐话术",
                "strategy_names": ["风险唤醒式需求面谈"],
                "follow_up_questions": ["您现在最担心家庭哪方面风险？"],
                "compliance_notes": ["不得承诺收益、理赔结果或夸大保障范围"],
                "evidence_refs": [],
            }
        ],
        objection_handling=[
            {
                "objection": "我现在不需要保险",
                "diagnosis": "客户未感知风险",
                "recommended_response": "先接纳，再用家庭责任引导。",
                "related_strategy_names": ["风险唤醒式需求面谈"],
                "related_script_ids": ["script_001"],
                "evidence_refs": [],
            }
        ],
    )

    assert isinstance(insights.customer_journey[0], CustomerJourneyStep)
    assert isinstance(insights.scripts[0], CaseSalesScript)
    assert insights.scripts[0].script_id == "script_001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_sales_insight_models.py -q
```

Expected: FAIL with import errors for `CaseSalesInsights`, `SectionSalesEvidence`, and related classes.

- [ ] **Step 3: Add sales insight models**

In `src/insurance_coach_agents/models.py`, add this helper after `_coerce_str_list`:

```python
def _coerce_model_list(value: object) -> object:
    """把 LLM 偶尔返回的 JSON 字符串形式列表规整为 list。"""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else [parsed]
    return value
```

In the imports near `ValueLevel`, keep the existing `Literal` import and add no new third-party imports.

Append these contracts after `ReviewResult`:

```python
# ---- 销售策略 / 话术提取契约 ----

ConfidenceLevel = Literal["high", "mid", "low"]


class SalesEvidenceRef(BaseModel):
    """销售证据的来源引用，尽量指向节、文件和原文片段。"""

    model_config = ConfigDict(frozen=True)

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
    compliance_notes: list[str] = Field(default_factory=list)
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
```

- [ ] **Step 4: Run model tests**

Run:

```bash
uv run pytest tests/test_sales_insight_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Check staged diff before any commit**

Run:

```bash
git diff -- src/insurance_coach_agents/models.py tests/test_sales_insight_models.py
```

Expected: diff only contains sales insight models and their tests.

Commit only if the user has approved commits:

```bash
git add src/insurance_coach_agents/models.py tests/test_sales_insight_models.py
git diff --cached --name-only
git commit -m "feat: add sales insight data contracts"
```

Expected staged files:

```text
src/insurance_coach_agents/models.py
tests/test_sales_insight_models.py
```

---

### Task 2: Sales Insight Agents

**Files:**
- Modify: `src/insurance_coach_agents/agents/prompts.py`
- Create: `src/insurance_coach_agents/agents/sales_insights.py`
- Modify: `src/insurance_coach_agents/agents/__init__.py`
- Create: `tests/test_sales_insight_agents.py`

- [ ] **Step 1: Write failing agent tests**

Create `tests/test_sales_insight_agents.py`:

```python
"""销售洞察 agent 测试，使用 fake model，不调用真实 API。"""

from __future__ import annotations

import asyncio

from insurance_coach_agents.agents import (
    CaseSalesInsightAgent,
    SectionSalesEvidenceAgent,
)
from insurance_coach_agents.models import (
    CaseSalesInsights,
    FileType,
    ParsedFile,
    RawSection,
    SectionSalesEvidence,
)


class _FakeStructured:
    def __init__(self, content: dict) -> None:
        self.content = content


class _FakeSalesModel:
    def __init__(self) -> None:
        self.user_materials: list[str] = []

    async def generate_structured_output(
        self, messages, structured_model, tool_choice=None
    ):
        self.user_materials.append(str(getattr(messages[-1], "content", "")))
        if structured_model.__name__ == "SectionSalesEvidence":
            return _FakeStructured(
                {
                    "case_name": "案例A",
                    "section_name": "第1节",
                    "customer_signals": [
                        {
                            "signal": "客户保障意识弱",
                            "evidence": "客户说暂时不需要保险",
                            "source_refs": [
                                {
                                    "section_name": "第1节",
                                    "filename": "讲义.txt",
                                    "quote": "暂时不需要保险",
                                }
                            ],
                        }
                    ],
                    "sales_actions": [],
                    "script_quotes": [
                        {
                            "quote": "您现在最担心家庭哪方面风险？",
                            "speaker": "sales",
                            "stage_hint": "售前",
                            "scenario_hint": "风险唤醒",
                            "source_refs": [],
                        }
                    ],
                    "objections": [],
                    "strategy_candidates": [
                        {
                            "name": "风险唤醒",
                            "reason": "围绕家庭责任展开追问",
                            "confidence": "high",
                            "inferred": True,
                            "source_refs": [],
                        }
                    ],
                }
            )
        return _FakeStructured(
            {
                "case_name": "案例A",
                "case_summary": "案例围绕风险唤醒展开。",
                "customer_journey": [
                    {
                        "stage": "售前",
                        "customer_state": "保障意识弱",
                        "sales_goal": "引发风险关注",
                        "key_actions": ["场景提问"],
                        "evidence_refs": [],
                    }
                ],
                "strategies": [
                    {
                        "name": "风险唤醒式需求面谈",
                        "aliases": ["风险唤醒"],
                        "definition": "通过家庭责任引导客户看到保障缺口。",
                        "applicable_stages": ["售前"],
                        "steps": ["场景切入", "风险追问"],
                        "do": ["先接纳客户现状"],
                        "dont": ["不要承诺收益"],
                        "confidence": "high",
                        "inferred": True,
                        "evidence_refs": [],
                    }
                ],
                "scripts": [
                    {
                        "script_id": "script_001",
                        "stage": "售前",
                        "scenario": "客户保险意识弱",
                        "customer_trigger": "客户认为现在不需要保险",
                        "goal": "吸引客户进入需求沟通",
                        "source_quote": "您现在最担心家庭哪方面风险？",
                        "coach_wording": "可以先从家庭责任切入，询问客户最担心的风险。",
                        "strategy_names": ["风险唤醒式需求面谈"],
                        "follow_up_questions": ["如果风险发生，会先影响谁？"],
                        "compliance_notes": ["不得承诺收益或理赔结果"],
                        "evidence_refs": [],
                    }
                ],
                "objection_handling": [],
            }
        )


def _section() -> RawSection:
    return RawSection(
        case_name="案例A",
        section_name="第1节",
        section_dir="案例A/第1节",
        files=(
            ParsedFile(
                file_type=FileType.TXT,
                filename="讲义.txt",
                text="客户：暂时不需要保险。销售：您现在最担心家庭哪方面风险？",
            ),
        ),
    )


def test_section_sales_evidence_agent_returns_structured_evidence():
    model = _FakeSalesModel()
    evidence = asyncio.run(SectionSalesEvidenceAgent(model).extract(_section()))

    assert isinstance(evidence, SectionSalesEvidence)
    assert evidence.case_name == "案例A"
    assert evidence.customer_signals[0].signal == "客户保障意识弱"
    assert evidence.script_quotes[0].quote.startswith("您现在")
    assert "案例：案例A" in model.user_materials[0]
    assert "讲义.txt" in model.user_materials[0]


def test_case_sales_insight_agent_receives_all_section_evidence():
    model = _FakeSalesModel()
    evidence = SectionSalesEvidenceAgent(model)
    first = asyncio.run(evidence.extract(_section()))
    second = first.model_copy(update={"section_name": "第2节"})

    insights = asyncio.run(
        CaseSalesInsightAgent(model).extract("案例A", [first, second])
    )

    assert isinstance(insights, CaseSalesInsights)
    assert insights.case_name == "案例A"
    assert insights.strategies[0].name == "风险唤醒式需求面谈"
    assert insights.scripts[0].script_id == "script_001"
    assert "第1节" in model.user_materials[-1]
    assert "第2节" in model.user_materials[-1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_sales_insight_agents.py -q
```

Expected: FAIL with import errors for `CaseSalesInsightAgent` and `SectionSalesEvidenceAgent`.

- [ ] **Step 3: Add prompts**

Append to `src/insurance_coach_agents/agents/prompts.py`:

```python

# SectionSalesEvidenceAgent：从单节中采集销售证据。
SECTION_SALES_EVIDENCE_SYSTEM_PROMPT = """你是保险公司 AI 教练系统的【销售证据采集专家】。

你的任务：从给定的单节绩优案例素材中，采集对销售策略和销售话术提取有价值的证据。

请只做证据采集，不要把单节内容直接包装成完整方法论。

需要提取：
1. customer_signals：客户状态、需求信号、异议苗头、决策障碍；
2. sales_actions：销售人员采取的动作，如场景提问、风险唤醒、需求追问、异议接纳、促成；
3. script_quotes：素材中真实出现的话术，尽量保留原话；
4. objections：客户明确表达的异议及素材中的应对证据；
5. strategy_candidates：本节可能体现的候选策略，必须说明依据，不能当作最终定论。

要求：
- 严格基于素材，不得杜撰客户背景、产品条款、收益、理赔或监管要求；
- 每条证据尽量带 source_refs，至少写明 section_name、filename 或短 quote；
- 原始话术和教练改写不要混在一起，本阶段只保存素材中的原始话术；
- 对不确定的策略归因使用 inferred=true，并给出 low/mid/high 置信度；
- 不提取寒暄、致谢、无信息量口号和个人情绪抒发。"""


# CaseSalesInsightAgent：整合同一案例下所有节级证据，形成案例级销售洞察。
CASE_SALES_INSIGHT_SYSTEM_PROMPT = """你是保险公司 AI 教练系统的【案例级销售洞察专家】。

你会收到同一个绩优案例下多个章节的销售证据。你的任务是从完整案例视角提炼：
1. customer_journey：客户从售前到成交/经营的状态变化、销售目标和关键动作；
2. strategies：贯穿案例的销售策略，必须能被多个或明确的证据支持；
3. scripts：可复用的场景化话术，区分原始话术 source_quote 和教练推荐话术 coach_wording；
4. objection_handling：客户异议、异议诊断、推荐回应方式和关联话术。

要求：
- 以完整案例为单位归纳，不要把每节割裂成孤立结论；
- 策略是对证据的抽象，不能把没有证据的通用销售理论塞进结果；
- 话术必须标注 stage、scenario、customer_trigger、goal 和 compliance_notes；
- coach_wording 可以更适合教练训练，但必须忠于 source_quote 的语义；
- 涉及收益、理赔、核保、产品责任、竞品比较时必须写合规提醒；
- 如果某个策略只是模型归纳，请保留 inferred=true，不要包装成公司标准打法。"""
```

- [ ] **Step 4: Create sales insight agents**

Create `src/insurance_coach_agents/agents/sales_insights.py`:

```python
"""销售策略 / 话术洞察智能体。"""

from __future__ import annotations

import json

from agentscope.message import SystemMsg, UserMsg
from agentscope.model import OpenAIChatModel

from ..models import CaseSalesInsights, RawSection, SectionSalesEvidence
from .factory import STRUCTURED_TOOL_CHOICE, render_section_material
from .prompts import (
    CASE_SALES_INSIGHT_SYSTEM_PROMPT,
    SECTION_SALES_EVIDENCE_SYSTEM_PROMPT,
)


def render_case_sales_evidence(
    case_name: str, evidences: list[SectionSalesEvidence]
) -> str:
    """把同一案例下的节级销售证据渲染为模型可读文本。"""
    blocks = [f"案例：{case_name}", "以下是该案例下各章节的销售证据："]
    for evidence in evidences:
        blocks.append(
            "===== 章节："
            f"{evidence.section_name} =====\n"
            f"{json.dumps(evidence.model_dump(), ensure_ascii=False, indent=2)}"
        )
    return "\n\n".join(blocks)


class SectionSalesEvidenceAgent:
    """从单节素材采集销售策略/话术证据。"""

    def __init__(self, model: OpenAIChatModel) -> None:
        self._model = model

    async def extract(self, section: RawSection) -> SectionSalesEvidence:
        material = render_section_material(section)
        messages = [
            SystemMsg(name="system", content=SECTION_SALES_EVIDENCE_SYSTEM_PROMPT),
            UserMsg(name="user", content=material),
        ]
        response = await self._model.generate_structured_output(
            messages,
            structured_model=SectionSalesEvidence,
            tool_choice=STRUCTURED_TOOL_CHOICE,
        )
        content = dict(response.content)
        content["case_name"] = str(content.get("case_name") or section.case_name)
        content["section_name"] = str(
            content.get("section_name") or section.section_name
        )
        return SectionSalesEvidence(**content)


class CaseSalesInsightAgent:
    """整合同一案例的节级证据，生成案例级销售洞察。"""

    def __init__(self, model: OpenAIChatModel) -> None:
        self._model = model

    async def extract(
        self, case_name: str, evidences: list[SectionSalesEvidence]
    ) -> CaseSalesInsights:
        material = render_case_sales_evidence(case_name, evidences)
        messages = [
            SystemMsg(name="system", content=CASE_SALES_INSIGHT_SYSTEM_PROMPT),
            UserMsg(name="user", content=material),
        ]
        response = await self._model.generate_structured_output(
            messages,
            structured_model=CaseSalesInsights,
            tool_choice=STRUCTURED_TOOL_CHOICE,
        )
        content = dict(response.content)
        content["case_name"] = str(content.get("case_name") or case_name)
        return CaseSalesInsights(**content)
```

- [ ] **Step 5: Export the agents**

Modify `src/insurance_coach_agents/agents/__init__.py`:

```python
from .sales_insights import CaseSalesInsightAgent, SectionSalesEvidenceAgent
```

Add both names to `__all__`:

```python
    "CaseSalesInsightAgent",
    "SectionSalesEvidenceAgent",
```

- [ ] **Step 6: Run agent tests**

Run:

```bash
uv run pytest tests/test_sales_insight_agents.py -q
```

Expected: PASS.

- [ ] **Step 7: Check staged diff before any commit**

Run:

```bash
git diff -- src/insurance_coach_agents/agents/prompts.py src/insurance_coach_agents/agents/sales_insights.py src/insurance_coach_agents/agents/__init__.py tests/test_sales_insight_agents.py
```

Expected: diff only contains sales insight prompts, agents, exports, and tests.

Commit only if the user has approved commits:

```bash
git add src/insurance_coach_agents/agents/prompts.py src/insurance_coach_agents/agents/sales_insights.py src/insurance_coach_agents/agents/__init__.py tests/test_sales_insight_agents.py
git diff --cached --name-only
git commit -m "feat: add sales insight agents"
```

Expected staged files:

```text
src/insurance_coach_agents/agents/__init__.py
src/insurance_coach_agents/agents/prompts.py
src/insurance_coach_agents/agents/sales_insights.py
tests/test_sales_insight_agents.py
```

---

### Task 3: Sales Insight Output Writer

**Files:**
- Create: `src/insurance_coach_agents/sales_output_writer.py`
- Create: `tests/test_sales_output_writer.py`

- [ ] **Step 1: Write failing writer tests**

Create `tests/test_sales_output_writer.py`:

```python
"""销售洞察 sidecar 写入测试。"""

from __future__ import annotations

import json

from insurance_coach_agents.models import CaseSalesInsights, SectionSalesEvidence
from insurance_coach_agents.sales_output_writer import (
    write_case_sales_insights,
    write_section_sales_evidence,
)


def _evidence() -> SectionSalesEvidence:
    return SectionSalesEvidence(
        case_name="案例A",
        section_name="第1节",
        customer_signals=[],
        sales_actions=[],
        script_quotes=[
            {
                "quote": "您现在最担心家庭哪方面风险？",
                "speaker": "sales",
                "stage_hint": "售前",
                "scenario_hint": "风险唤醒",
                "source_refs": [],
            }
        ],
        objections=[],
        strategy_candidates=[],
    )


def _insights() -> CaseSalesInsights:
    return CaseSalesInsights(
        case_name="案例A",
        case_summary="案例围绕风险唤醒展开。",
        customer_journey=[
            {
                "stage": "售前",
                "customer_state": "保障意识弱",
                "sales_goal": "引发风险关注",
                "key_actions": ["场景提问"],
                "evidence_refs": [],
            }
        ],
        strategies=[
            {
                "name": "风险唤醒式需求面谈",
                "aliases": ["风险唤醒"],
                "definition": "通过家庭责任引导客户看到保障缺口。",
                "applicable_stages": ["售前"],
                "steps": ["场景切入", "风险追问"],
                "do": ["先接纳客户现状"],
                "dont": ["不要承诺收益"],
                "confidence": "high",
                "inferred": True,
                "evidence_refs": [],
            }
        ],
        scripts=[
            {
                "script_id": "script_001",
                "stage": "售前",
                "scenario": "客户保险意识弱",
                "customer_trigger": "客户认为现在不需要保险",
                "goal": "吸引客户进入需求沟通",
                "source_quote": "您现在最担心家庭哪方面风险？",
                "coach_wording": "可以先从家庭责任切入。",
                "strategy_names": ["风险唤醒式需求面谈"],
                "follow_up_questions": ["如果风险发生，会先影响谁？"],
                "compliance_notes": ["不得承诺收益或理赔结果"],
                "evidence_refs": [],
            }
        ],
        objection_handling=[],
    )


def test_write_section_sales_evidence_creates_json_sidecar(tmp_path):
    path = write_section_sales_evidence(_evidence(), output_dir=tmp_path)

    assert path == tmp_path / "案例A" / "第1节.sales_evidence.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["case_name"] == "案例A"
    assert data["script_quotes"][0]["quote"].startswith("您现在")


def test_write_case_sales_insights_creates_json_and_playbook(tmp_path):
    result = write_case_sales_insights(_insights(), output_dir=tmp_path)

    assert result.insights_path == tmp_path / "案例A" / "case.sales_insights.json"
    assert result.playbook_path == tmp_path / "案例A" / "case.sales_playbook.md"
    data = json.loads(result.insights_path.read_text(encoding="utf-8"))
    assert data["strategies"][0]["name"] == "风险唤醒式需求面谈"
    playbook = result.playbook_path.read_text(encoding="utf-8")
    assert "# 案例A - 销售洞察手册" in playbook
    assert "## 销售策略" in playbook
    assert "不得承诺收益或理赔结果" in playbook
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_sales_output_writer.py -q
```

Expected: FAIL with import error for `insurance_coach_agents.sales_output_writer`.

- [ ] **Step 3: Implement writer module**

Create `src/insurance_coach_agents/sales_output_writer.py`:

```python
"""销售策略 / 话术洞察产物写入。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import OUTPUT_DIR
from .models import CaseSalesInsights, SectionSalesEvidence
from .output_writer import _atomic_write_text, _safe_name


@dataclass(frozen=True)
class CaseSalesWriteResult:
    """案例级销售洞察写入结果。"""

    insights_path: Path
    playbook_path: Path


def write_section_sales_evidence(
    evidence: SectionSalesEvidence, output_dir: Path = OUTPUT_DIR
) -> Path:
    """写出单节销售证据 JSON sidecar。"""
    case_dir = output_dir / _safe_name(evidence.case_name)
    case_dir.mkdir(parents=True, exist_ok=True)
    path = case_dir / f"{_safe_name(evidence.section_name)}.sales_evidence.json"
    _atomic_write_text(
        path,
        json.dumps(evidence.model_dump(), ensure_ascii=False, indent=2),
    )
    return path


def _render_list(items: list[str]) -> str:
    if not items:
        return "- 无"
    return "\n".join(f"- {item}" for item in items)


def _render_case_playbook(insights: CaseSalesInsights) -> str:
    lines = [
        f"# {insights.case_name} - 销售洞察手册",
        "",
        "## 案例概览",
        insights.case_summary,
        "",
        "## 客户旅程",
    ]
    if insights.customer_journey:
        for step in insights.customer_journey:
            lines.extend(
                [
                    f"### {step.stage}",
                    f"- 客户状态: {step.customer_state}",
                    f"- 销售目标: {step.sales_goal}",
                    "- 关键动作:",
                    _render_list(step.key_actions),
                    "",
                ]
            )
    else:
        lines.extend(["无", ""])

    lines.append("## 销售策略")
    if insights.strategies:
        for strategy in insights.strategies:
            lines.extend(
                [
                    f"### {strategy.name}",
                    f"- 定义: {strategy.definition}",
                    f"- 适用阶段: {'、'.join(strategy.applicable_stages) or '未标注'}",
                    f"- 置信度: {strategy.confidence}",
                    f"- 模型归纳: {'是' if strategy.inferred else '否'}",
                    "- 步骤:",
                    _render_list(strategy.steps),
                    "- 建议做法:",
                    _render_list(strategy.do),
                    "- 避免做法:",
                    _render_list(strategy.dont),
                    "",
                ]
            )
    else:
        lines.extend(["无", ""])

    lines.append("## 场景话术")
    if insights.scripts:
        for script in insights.scripts:
            lines.extend(
                [
                    f"### {script.script_id} - {script.scenario}",
                    f"- 阶段: {script.stage}",
                    f"- 客户触发点: {script.customer_trigger}",
                    f"- 目标: {script.goal}",
                    f"- 原始话术: {script.source_quote}",
                    f"- 教练推荐话术: {script.coach_wording}",
                    f"- 关联策略: {'、'.join(script.strategy_names) or '未标注'}",
                    "- 追问建议:",
                    _render_list(script.follow_up_questions),
                    "- 合规提醒:",
                    _render_list(script.compliance_notes),
                    "",
                ]
            )
    else:
        lines.extend(["无", ""])

    lines.append("## 异议处理")
    if insights.objection_handling:
        for item in insights.objection_handling:
            lines.extend(
                [
                    f"### {item.objection}",
                    f"- 异议诊断: {item.diagnosis}",
                    f"- 推荐回应: {item.recommended_response}",
                    f"- 关联策略: {'、'.join(item.related_strategy_names) or '未标注'}",
                    f"- 关联话术: {'、'.join(item.related_script_ids) or '未标注'}",
                    "",
                ]
            )
    else:
        lines.extend(["无", ""])
    return "\n".join(lines).rstrip() + "\n"


def write_case_sales_insights(
    insights: CaseSalesInsights, output_dir: Path = OUTPUT_DIR
) -> CaseSalesWriteResult:
    """写出案例级销售洞察 JSON 和人工审阅 Markdown。"""
    case_dir = output_dir / _safe_name(insights.case_name)
    case_dir.mkdir(parents=True, exist_ok=True)
    insights_path = case_dir / "case.sales_insights.json"
    playbook_path = case_dir / "case.sales_playbook.md"
    _atomic_write_text(
        insights_path,
        json.dumps(insights.model_dump(), ensure_ascii=False, indent=2),
    )
    _atomic_write_text(playbook_path, _render_case_playbook(insights))
    return CaseSalesWriteResult(
        insights_path=insights_path,
        playbook_path=playbook_path,
    )
```

- [ ] **Step 4: Run writer tests**

Run:

```bash
uv run pytest tests/test_sales_output_writer.py -q
```

Expected: PASS.

- [ ] **Step 5: Check staged diff before any commit**

Run:

```bash
git diff -- src/insurance_coach_agents/sales_output_writer.py tests/test_sales_output_writer.py
```

Expected: diff only contains writer module and tests.

Commit only if the user has approved commits:

```bash
git add src/insurance_coach_agents/sales_output_writer.py tests/test_sales_output_writer.py
git diff --cached --name-only
git commit -m "feat: write sales insight sidecars"
```

Expected staged files:

```text
src/insurance_coach_agents/sales_output_writer.py
tests/test_sales_output_writer.py
```

---

### Task 4: Case-Level Sales Pipeline

**Files:**
- Create: `src/insurance_coach_agents/sales_pipeline.py`
- Create: `tests/test_sales_pipeline.py`

- [ ] **Step 1: Write failing pipeline tests**

Create `tests/test_sales_pipeline.py`:

```python
"""案例级销售洞察 pipeline 测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from insurance_coach_agents.parsers.grouping import group_by_directory
from insurance_coach_agents.sales_pipeline import run_case_sales_insights


class _FakeStructured:
    def __init__(self, content: dict) -> None:
        self.content = content


class _FakeSalesModel:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_structured_output(
        self, messages, structured_model, tool_choice=None
    ):
        user_content = str(getattr(messages[-1], "content", ""))
        self.calls.append(user_content)
        if structured_model.__name__ == "SectionSalesEvidence":
            section_name = "第2节" if "第2节" in user_content else "第1节"
            return _FakeStructured(
                {
                    "case_name": "案例A",
                    "section_name": section_name,
                    "customer_signals": [],
                    "sales_actions": [
                        {
                            "action": f"{section_name}销售动作",
                            "stage_hint": "售前",
                            "evidence": f"{section_name}证据",
                            "source_refs": [],
                        }
                    ],
                    "script_quotes": [
                        {
                            "quote": f"{section_name}原始话术",
                            "speaker": "sales",
                            "stage_hint": "售前",
                            "scenario_hint": "测试场景",
                            "source_refs": [],
                        }
                    ],
                    "objections": [],
                    "strategy_candidates": [],
                }
            )
        return _FakeStructured(
            {
                "case_name": "案例A",
                "case_summary": "整案销售洞察。",
                "customer_journey": [
                    {
                        "stage": "售前",
                        "customer_state": "保障意识弱",
                        "sales_goal": "建立风险意识",
                        "key_actions": ["第1节销售动作", "第2节销售动作"],
                        "evidence_refs": [],
                    }
                ],
                "strategies": [
                    {
                        "name": "风险唤醒",
                        "aliases": [],
                        "definition": "用风险问题建立保障意识。",
                        "applicable_stages": ["售前"],
                        "steps": ["提问", "追问"],
                        "do": ["先接纳"],
                        "dont": ["不承诺收益"],
                        "confidence": "high",
                        "inferred": True,
                        "evidence_refs": [],
                    }
                ],
                "scripts": [
                    {
                        "script_id": "script_001",
                        "stage": "售前",
                        "scenario": "测试场景",
                        "customer_trigger": "客户不想聊保险",
                        "goal": "打开话题",
                        "source_quote": "第1节原始话术",
                        "coach_wording": "教练推荐话术",
                        "strategy_names": ["风险唤醒"],
                        "follow_up_questions": [],
                        "compliance_notes": ["不承诺收益"],
                        "evidence_refs": [],
                    }
                ],
                "objection_handling": [],
            }
        )


def _make_case(root: Path) -> list:
    first = root / "案例A" / "第1节"
    second = root / "案例A" / "第2节"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "讲义.txt").write_text("第1节：客户不想聊保险。", encoding="utf-8")
    (second / "讲义.txt").write_text("第2节：继续追问家庭责任。", encoding="utf-8")
    return group_by_directory(root)


def test_run_case_sales_insights_writes_evidence_and_case_outputs(tmp_path):
    groups = _make_case(tmp_path / "cases")
    output = tmp_path / "output"
    model = _FakeSalesModel()

    result = asyncio.run(
        run_case_sales_insights(
            "案例A",
            groups,
            model,
            output_dir=output,
            vision=False,
        )
    )

    assert result.status == "ok"
    assert len(result.evidence_paths) == 2
    assert result.insights_path == str(output / "案例A" / "case.sales_insights.json")
    assert (output / "案例A" / "第1节.sales_evidence.json").exists()
    assert (output / "案例A" / "第2节.sales_evidence.json").exists()
    data = json.loads((output / "案例A" / "case.sales_insights.json").read_text())
    assert data["case_summary"] == "整案销售洞察。"
    assert data["strategies"][0]["name"] == "风险唤醒"
    assert "第1节" in model.calls[0]
    assert "第2节" in model.calls[1]
    assert "第1节销售动作" in model.calls[-1]
    assert "第2节销售动作" in model.calls[-1]


def test_run_case_sales_insights_fails_when_case_has_no_groups(tmp_path):
    result = asyncio.run(
        run_case_sales_insights(
            "不存在案例",
            [],
            _FakeSalesModel(),
            output_dir=tmp_path / "output",
            vision=False,
        )
    )

    assert result.status == "failed"
    assert "未找到案例" in result.error
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_sales_pipeline.py -q
```

Expected: FAIL with import error for `insurance_coach_agents.sales_pipeline`.

- [ ] **Step 3: Implement case-level pipeline**

Create `src/insurance_coach_agents/sales_pipeline.py`:

```python
"""案例级销售策略 / 话术洞察编排。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentscope.model import OpenAIChatModel

from .agents import CaseSalesInsightAgent, ImageDescriber, SectionSalesEvidenceAgent
from .agents.enrich import enrich_section_with_vision
from .config import OUTPUT_DIR
from .parsers.grouping import SourceGroup, load_group
from .pipeline import IMAGE_CACHE_DIRNAME
from .sales_output_writer import (
    write_case_sales_insights,
    write_section_sales_evidence,
)


@dataclass(frozen=True)
class CaseSalesInsightResult:
    """案例级销售洞察处理结果。"""

    case_name: str
    status: str
    evidence_paths: tuple[str, ...] = ()
    insights_path: str | None = None
    playbook_path: str | None = None
    error: str | None = None


def _case_groups(case_name: str, groups: list[SourceGroup]) -> list[SourceGroup]:
    """从全部知识单元中过滤并稳定排序某个案例的节。"""
    return sorted(
        [group for group in groups if group.case_name == case_name],
        key=lambda group: group.identifier,
    )


async def run_case_sales_insights(
    case_name: str,
    groups: list[SourceGroup],
    model: OpenAIChatModel,
    output_dir: Path = OUTPUT_DIR,
    vision: bool = True,
    vision_model: OpenAIChatModel | None = None,
) -> CaseSalesInsightResult:
    """对一个完整案例提取销售证据与案例级销售洞察。"""
    selected = _case_groups(case_name, groups)
    if not selected:
        return CaseSalesInsightResult(
            case_name=case_name,
            status="failed",
            error=f"未找到案例: {case_name}",
        )

    evidence_agent = SectionSalesEvidenceAgent(model)
    case_agent = CaseSalesInsightAgent(model)
    describer = (
        ImageDescriber(
            vision_model or model,
            cache_dir=output_dir / IMAGE_CACHE_DIRNAME,
        )
        if vision
        else None
    )

    evidence_paths: list[str] = []
    evidences = []
    try:
        for group in selected:
            section = load_group(group)
            if describer is not None:
                section = await enrich_section_with_vision(
                    section,
                    group.file_paths,
                    describer,
                )
            if not section.primary_text:
                continue
            evidence = await evidence_agent.extract(section)
            evidences.append(evidence)
            evidence_paths.append(
                str(write_section_sales_evidence(evidence, output_dir=output_dir))
            )

        if not evidences:
            return CaseSalesInsightResult(
                case_name=case_name,
                status="failed",
                error=f"案例无可解析销售证据: {case_name}",
            )

        insights = await case_agent.extract(case_name, evidences)
        write_result = write_case_sales_insights(insights, output_dir=output_dir)
        return CaseSalesInsightResult(
            case_name=case_name,
            status="ok",
            evidence_paths=tuple(evidence_paths),
            insights_path=str(write_result.insights_path),
            playbook_path=str(write_result.playbook_path),
        )
    except Exception as exc:  # noqa: BLE001 - 案例级失败隔离
        return CaseSalesInsightResult(
            case_name=case_name,
            status="failed",
            evidence_paths=tuple(evidence_paths),
            error=repr(exc),
        )
```

- [ ] **Step 4: Run pipeline tests**

Run:

```bash
uv run pytest tests/test_sales_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 5: Check staged diff before any commit**

Run:

```bash
git diff -- src/insurance_coach_agents/sales_pipeline.py tests/test_sales_pipeline.py
```

Expected: diff only contains sales pipeline and tests.

Commit only if the user has approved commits:

```bash
git add src/insurance_coach_agents/sales_pipeline.py tests/test_sales_pipeline.py
git diff --cached --name-only
git commit -m "feat: add case sales insight pipeline"
```

Expected staged files:

```text
src/insurance_coach_agents/sales_pipeline.py
tests/test_sales_pipeline.py
```

---

### Task 5: CLI Command

**Files:**
- Modify: `src/insurance_coach_agents/cli.py`
- Create: `tests/test_cli_sales_insights.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_sales_insights.py`:

```python
"""sales-insights CLI 辅助逻辑测试。"""

from __future__ import annotations

from pathlib import Path

from insurance_coach_agents.cli import _select_case_names
from insurance_coach_agents.parsers.grouping import SourceGroup


def _group(case_name: str, unit_name: str) -> SourceGroup:
    return SourceGroup(
        case_name=case_name,
        unit_name=unit_name,
        identifier=f"{case_name}/{unit_name}",
        file_paths=(Path(f"{case_name}/{unit_name}/讲义.txt"),),
    )


def test_select_case_names_returns_explicit_case_when_present():
    groups = [_group("案例A", "第1节"), _group("案例B", "第1节")]

    assert _select_case_names(groups, case_name="案例B", all_cases=False) == ["案例B"]


def test_select_case_names_returns_all_cases_sorted():
    groups = [_group("案例B", "第1节"), _group("案例A", "第1节")]

    assert _select_case_names(groups, case_name=None, all_cases=True) == [
        "案例A",
        "案例B",
    ]


def test_select_case_names_raises_for_missing_case():
    groups = [_group("案例A", "第1节")]

    try:
        _select_case_names(groups, case_name="案例X", all_cases=False)
    except ValueError as exc:
        assert "未找到案例" in str(exc)
    else:
        raise AssertionError("missing case should raise ValueError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_cli_sales_insights.py -q
```

Expected: FAIL with import error for `_select_case_names`.

- [ ] **Step 3: Add CLI helper and command**

Modify imports in `src/insurance_coach_agents/cli.py`:

```python
from .sales_pipeline import run_case_sales_insights
```

Add this helper above `_cmd_run`:

```python
def _select_case_names(
    groups, case_name: str | None, all_cases: bool
) -> list[str]:
    """选择要生成销售洞察的案例名。"""
    available = sorted({group.case_name for group in groups})
    if all_cases:
        return available
    if not case_name:
        raise ValueError("请提供案例名称，或使用 --all 处理全部案例")
    if case_name not in available:
        raise ValueError(f"未找到案例: {case_name}")
    return [case_name]
```

Add async command function above `main()`:

```python
async def _run_sales_insights(args: argparse.Namespace) -> int:
    groups = group_by_directory()
    try:
        case_names = _select_case_names(
            groups,
            case_name=args.case,
            all_cases=args.all,
        )
    except ValueError as exc:
        LOGGER.error("%s", exc)
        return 1

    model = build_chat_model()
    vision = not args.no_vision
    vision_model = build_vision_model() if vision else None
    failed = 0
    for case_name in case_names:
        LOGGER.info("提取案例级销售洞察: %s", case_name)
        result = await run_case_sales_insights(
            case_name,
            groups,
            model,
            output_dir=OUTPUT_DIR,
            vision=vision,
            vision_model=vision_model,
        )
        if result.status == "ok":
            LOGGER.info("  sales insights: %s", result.insights_path)
            LOGGER.info("  sales playbook: %s", result.playbook_path)
        else:
            failed += 1
            LOGGER.error("  失败: %s", result.error)
    return 1 if failed else 0


def _cmd_sales_insights(args: argparse.Namespace) -> int:
    return asyncio.run(_run_sales_insights(args))
```

Register the subcommand in `main()` before parsing args:

```python
    p_sales = sub.add_parser(
        "sales-insights",
        help="按完整案例提取销售策略、销售话术和异议处理洞察",
    )
    p_sales.add_argument("case", nargs="?", help="案例名称；使用 --all 时可省略")
    p_sales.add_argument("--all", action="store_true", help="处理全部案例")
    p_sales.add_argument(
        "--no-vision", action="store_true", help="跳过课件配图的视觉识别"
    )
    p_sales.set_defaults(func=_cmd_sales_insights)
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
uv run pytest tests/test_cli_sales_insights.py -q
```

Expected: PASS.

- [ ] **Step 5: Run help command**

Run:

```bash
uv run insurance-coach-md sales-insights --help
```

Expected: output includes `按完整案例提取销售策略、销售话术和异议处理洞察`.

- [ ] **Step 6: Check staged diff before any commit**

Run:

```bash
git diff -- src/insurance_coach_agents/cli.py tests/test_cli_sales_insights.py
```

Expected: diff only contains the new CLI command, helper, and tests.

Commit only if the user has approved commits:

```bash
git add src/insurance_coach_agents/cli.py tests/test_cli_sales_insights.py
git diff --cached --name-only
git commit -m "feat: add sales insights cli"
```

Expected staged files:

```text
src/insurance_coach_agents/cli.py
tests/test_cli_sales_insights.py
```

---

### Task 6: README and Regression Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README usage**

In `README.md`, add this block after the existing `build`/`run` command examples:

```markdown

# 案例级销售洞察：整合一个完整案例下所有节，提取销售策略、销售话术与异议处理
uv run insurance-coach-md sales-insights "<案例>"
uv run insurance-coach-md sales-insights "<案例>" --no-vision
uv run insurance-coach-md sales-insights --all
```

In the “产物” tree, add:

```text
├── <案例>/<节>.sales_evidence.json  # 单节销售证据：客户信号/销售动作/原始话术/异议
├── <案例>/case.sales_insights.json  # 案例级销售策略、话术、异议处理结构化数据
├── <案例>/case.sales_playbook.md    # 面向人工审阅的案例销售洞察手册
```

Add this paragraph below the output explanation:

```markdown
`sales-insights` 会以完整案例为单位整合所有节的内容：先生成节级销售证据，
再提炼案例级销售策略、场景化话术和异议处理建议。该链路仍只写本地 sidecar 文件，
不做 embedding、不写向量库。
```

- [ ] **Step 2: Run targeted tests**

Run:

```bash
uv run pytest tests/test_sales_insight_models.py tests/test_sales_insight_agents.py tests/test_sales_output_writer.py tests/test_sales_pipeline.py tests/test_cli_sales_insights.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 4: Check final diff**

Run:

```bash
git status --short
git diff -- README.md
```

Expected: README diff only documents `sales-insights` command and outputs. `git status --short` may include pre-existing unrelated changes; do not stage unrelated files.

Commit only if the user has approved commits:

```bash
git add README.md
git diff --cached --name-only
git commit -m "docs: document sales insights extraction"
```

Expected staged file:

```text
README.md
```

---

## Self-Review

Spec coverage:

- Case-level extraction is implemented by `run_case_sales_insights`.
- Section evidence is implemented by `SectionSalesEvidenceAgent` and `<节>.sales_evidence.json`.
- Case-level strategy/script/objection output is implemented by `CaseSalesInsightAgent`, `case.sales_insights.json`, and `case.sales_playbook.md`.
- AI coach retrieval fields are present in `CaseSalesScript`, `CaseSalesStrategy`, `ObjectionHandling`, and `CustomerJourneyStep`.
- Compliance boundaries are represented in prompts, `dont`, and `compliance_notes`.
- Global strategy normalization is intentionally outside this first implementation and remains a follow-up after case-level output is validated.

Placeholder scan:

- The plan contains no implementation placeholders.
- Every new file has concrete test and implementation snippets.
- Every command includes expected result.

Type consistency:

- `SectionSalesEvidenceAgent.extract()` returns `SectionSalesEvidence`.
- `CaseSalesInsightAgent.extract()` returns `CaseSalesInsights`.
- `write_case_sales_insights()` returns `CaseSalesWriteResult`.
- `run_case_sales_insights()` returns `CaseSalesInsightResult`.
- CLI uses `run_case_sales_insights()` and the existing `group_by_directory()`.
