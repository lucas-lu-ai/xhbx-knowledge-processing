"""分组策略与批处理编排的单元测试（fake 模型，不调真实 API）。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from docx import Document

from insurance_coach_agents.parsers.grouping import (
    group_by_directory,
    group_by_single_file,
    load_group,
)
from insurance_coach_agents.pipeline import run_pipeline


def _make_docx(path: Path, with_content: bool = True) -> None:
    doc = Document()
    if with_content:
        doc.add_heading("课程主题：测试", level=1)
        doc.add_paragraph("正文内容。")
    doc.save(str(path))


def _make_cases(tmp_path: Path, n_sections: int = 2) -> Path:
    cases = tmp_path / "cases"
    for i in range(1, n_sections + 1):
        section = cases / "案例A" / f"第{i}节"
        section.mkdir(parents=True)
        _make_docx(section / f"讲义{i}.docx")
        (section / f"音频{i}.mp3").write_bytes(b"")
    return cases


_ASSESS_CONTENT = {
    "worth_storing": True,
    "reason": "包含可复用方法论",
    "topics": ["需求面谈"],
    "serves": {"qa": "high", "recommend": "mid", "exam": "low", "roleplay": "high"},
    "value_score": 0.7,
}
_REVIEW_CONTENT = {
    "passed": True,
    "heading_ok": True,
    "fidelity_ok": True,
    "no_meta_leak": True,
    "issues": [],
    "score": 0.9,
}


class _FakeStructured:
    def __init__(self, content: dict) -> None:
        self.content = content


class _FakeModel:
    async def generate_structured_output(self, messages, structured_model):
        # 按目标结构返回对应内容：Assessment / ReviewResult。
        if structured_model.__name__ == "ReviewResult":
            return _FakeStructured(_REVIEW_CONTENT)
        return _FakeStructured(_ASSESS_CONTENT)

    async def __call__(self, messages):
        return {"content": [{"type": "text", "text": "# 测试标题\n## 模块\n正文"}]}


def test_group_by_directory_finds_section_dirs(tmp_path):
    cases = _make_cases(tmp_path, n_sections=2)
    groups = group_by_directory(cases)
    assert len(groups) == 2
    assert all(g.case_name == "案例A" for g in groups)
    # 媒体被记入 skipped_media，docx 进 file_paths
    assert all(len(g.file_paths) == 1 for g in groups)
    assert all(g.skipped_media for g in groups)


def test_group_by_single_file_one_unit_per_file(tmp_path):
    cases = _make_cases(tmp_path, n_sections=2)
    groups = group_by_single_file(cases)
    # 2 个 docx → 2 个单元；mp3 不计入
    assert len(groups) == 2
    assert all(len(g.file_paths) == 1 for g in groups)


def test_load_group_parses_files(tmp_path):
    cases = _make_cases(tmp_path, n_sections=1)
    group = group_by_directory(cases)[0]
    section = load_group(group)
    assert section.primary_text is not None
    assert "课程主题：测试" in section.primary_text


def test_run_pipeline_produces_outputs_and_manifest(tmp_path):
    # Arrange
    cases = _make_cases(tmp_path, n_sections=2)
    out = tmp_path / "out"
    groups = group_by_directory(cases)

    # Act
    results = asyncio.run(run_pipeline(groups, _FakeModel(), concurrency=2, output_dir=out))

    # Assert
    assert len(results) == 2
    assert all(r.status == "ok" for r in results)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["summary"]["ok"] == 2
    assert manifest["summary"]["worth_storing"] == 2
    assert len(list(out.rglob("*.md"))) == 2


def test_run_pipeline_with_review_records_verdict(tmp_path):
    cases = _make_cases(tmp_path, n_sections=1)
    out = tmp_path / "out"

    results = asyncio.run(
        run_pipeline(
            group_by_directory(cases),
            _FakeModel(),
            output_dir=out,
            vision=False,
            review=True,
        )
    )

    assert results[0].review_passed is True
    assert results[0].review_score == 0.9
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["summary"]["review_failed"] == 0


def test_run_pipeline_incremental_skips_existing(tmp_path):
    cases = _make_cases(tmp_path, n_sections=2)
    out = tmp_path / "out"
    groups = group_by_directory(cases)

    asyncio.run(run_pipeline(groups, _FakeModel(), output_dir=out))
    # 第二次运行（非 force）应全部跳过
    results = asyncio.run(run_pipeline(groups, _FakeModel(), output_dir=out))
    assert all(r.status == "skipped" for r in results)


def test_run_pipeline_isolates_failures(tmp_path):
    # Arrange: 一个正常节 + 一个空 docx 节（无可解析文本）
    cases = tmp_path / "cases"
    ok_dir = cases / "案例A" / "好节"
    bad_dir = cases / "案例A" / "坏节"
    ok_dir.mkdir(parents=True)
    bad_dir.mkdir(parents=True)
    _make_docx(ok_dir / "好.docx", with_content=True)
    _make_docx(bad_dir / "坏.docx", with_content=False)
    out = tmp_path / "out"

    # Act
    results = asyncio.run(
        run_pipeline(group_by_directory(cases), _FakeModel(), output_dir=out)
    )

    # Assert: 坏节 failed，但好节仍 ok
    by_name = {r.section_name: r for r in results}
    assert by_name["好节"].status == "ok"
    assert by_name["坏节"].status == "failed"
    assert "无可解析" in by_name["坏节"].error
