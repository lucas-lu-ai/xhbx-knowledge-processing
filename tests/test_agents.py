"""智能体层与产物落盘的单元测试。

使用 fake 模型替身，不调用真实 API；异步方法用 ``asyncio.run`` 驱动，
避免引入额外的 pytest-asyncio 依赖。
"""

from __future__ import annotations

import asyncio
import json

from insurance_coach_agents.agents import (
    AssessorAgent,
    ExtractorAgent,
    ReviewerAgent,
)
from insurance_coach_agents.agents.factory import (
    render_section_material,
    response_text,
)
from insurance_coach_agents.models import (
    Assessment,
    ExtractedDoc,
    FileType,
    ParsedFile,
    RawSection,
    ReviewResult,
    ServesRating,
)
from insurance_coach_agents.output_writer import write_section_output


def _section() -> RawSection:
    return RawSection(
        case_name="案例X",
        section_name="第1节",
        section_dir="案例X/第1节",
        files=(
            ParsedFile(file_type=FileType.DOCX, filename="d.docx", text="# 讲义\n要点"),
            ParsedFile(file_type=FileType.TXT, filename="t.txt", text="口语补充"),
        ),
    )


class _FakeStructured:
    def __init__(self, content: dict) -> None:
        self.content = content


class _FakeModel:
    """最小模型替身：分别覆盖结构化与普通调用。"""

    def __init__(self, structured: dict | None = None, content_blocks=None) -> None:
        self._structured = structured
        self._content_blocks = content_blocks

    async def generate_structured_output(self, messages, structured_model):
        return _FakeStructured(self._structured)

    async def __call__(self, messages):
        return {"content": self._content_blocks}


def test_response_text_filters_thinking_blocks():
    response = {
        "content": [
            {"type": "thinking", "text": "内部推理"},
            {"type": "text", "text": "最终答案"},
        ]
    }
    assert response_text(response) == "最终答案"


def test_render_section_material_labels_sources():
    material = render_section_material(_section())
    assert "案例：案例X" in material
    assert "docx 讲义" in material
    assert "txt 音频转写稿" in material
    assert "口语补充" in material


def test_assessor_returns_structured_assessment():
    model = _FakeModel(
        structured={
            "worth_storing": True,
            "reason": "包含完整面谈流程",
            "topics": ["需求面谈"],
            "serves": {
                "qa": "high",
                "recommend": "mid",
                "exam": "low",
                "roleplay": "high",
            },
            "value_score": 0.8,
        }
    )
    assessment = asyncio.run(AssessorAgent(model).assess(_section()))
    assert isinstance(assessment, Assessment)
    assert assessment.worth_storing is True
    assert assessment.serves.qa == "high"
    assert assessment.value_score == 0.8


def test_extractor_strips_code_fence_and_extracts_title():
    blocks = [
        {"type": "thinking", "text": "略"},
        {"type": "text", "text": "```markdown\n# 千万保额健康险\n## 关键一\n正文\n```"},
    ]
    model = _FakeModel(content_blocks=blocks)
    doc = asyncio.run(ExtractorAgent(model).extract(_section()))
    assert isinstance(doc, ExtractedDoc)
    assert doc.title == "千万保额健康险"
    assert doc.body_markdown.startswith("# 千万保额健康险")
    assert "```" not in doc.body_markdown


def test_extractor_falls_back_to_section_name_without_h1():
    blocks = [{"type": "text", "text": "没有标题的正文"}]
    model = _FakeModel(content_blocks=blocks)
    doc = asyncio.run(ExtractorAgent(model).extract(_section()))
    assert doc.title == "第1节"


def test_reviewer_returns_structured_review():
    model = _FakeModel(
        structured={
            "passed": False,
            "heading_ok": True,
            "fidelity_ok": False,
            "no_meta_leak": True,
            "issues": ["遗漏了第二步面谈话术原文"],
            "score": 0.5,
        }
    )
    doc = ExtractedDoc(title="标题", body_markdown="# 标题\n正文")
    review = asyncio.run(ReviewerAgent(model).review(_section(), doc))
    assert isinstance(review, ReviewResult)
    assert review.passed is False
    assert review.fidelity_ok is False
    assert review.issues == ["遗漏了第二步面谈话术原文"]
    assert review.score == 0.5


def test_review_issues_coerces_json_string_to_list():
    # qwen 结构化输出偶尔把 list 字段返回成 JSON 字符串，validator 应转回 list
    model = _FakeModel(
        structured={
            "passed": False,
            "heading_ok": False,
            "fidelity_ok": True,
            "no_meta_leak": True,
            "issues": '["缺少一级标题", "层级跳级"]',
            "score": 0.6,
        }
    )
    doc = ExtractedDoc(title="t", body_markdown="## 无 h1")
    review = asyncio.run(ReviewerAgent(model).review(_section(), doc))
    assert review.issues == ["缺少一级标题", "层级跳级"]


def test_write_section_output_creates_md_and_meta(tmp_path):
    # Arrange
    section = _section()
    assessment = Assessment(
        worth_storing=True,
        reason="理由",
        topics=["需求面谈", "异议处理"],
        serves=ServesRating(qa="high", recommend="mid", exam="low", roleplay="high"),
        value_score=0.86,
    )
    doc = ExtractedDoc(title="千万保额健康险", body_markdown="# 千万保额健康险\n正文")

    # Act
    result = write_section_output(section, assessment, doc, output_dir=tmp_path)

    # Assert: markdown
    md = result.markdown_path.read_text(encoding="utf-8")
    assert md.startswith("---")
    assert 'title: "千万保额健康险"' in md
    assert "value_score: 0.86" in md
    assert "worth_storing: true" in md
    assert "qa: high" in md
    assert "# 千万保额健康险\n正文" in md

    # Assert: meta json
    meta = json.loads(result.meta_path.read_text(encoding="utf-8"))
    assert meta["case"] == "案例X"
    assert meta["topics"] == ["需求面谈", "异议处理"]
    assert meta["serves"]["roleplay"] == "high"
    assert meta["sources"] == ["docx", "txt"]
