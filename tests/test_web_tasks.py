from __future__ import annotations

import asyncio
from zipfile import ZipFile

import pytest

import insurance_coach_agents.web_tasks as web_tasks
from insurance_coach_agents.pipeline import SectionResult
from insurance_coach_agents.web_tasks import (
    TaskRecord,
    WebTaskRunner,
    build_result_archive,
    collect_result_files,
    discover_upload_groups,
    resolve_result_archive,
    resolve_result_file,
    safe_extract_zip,
)


def test_safe_extract_zip_rejects_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("../evil.txt", "bad")

    with pytest.raises(ValueError, match="不安全的压缩包路径"):
        safe_extract_zip(archive, tmp_path / "input")

    assert not (tmp_path / "evil.txt").exists()


def test_discover_upload_groups_names_single_flat_file_after_upload(tmp_path):
    (tmp_path / "讲义.txt").write_text("主干内容", encoding="utf-8")
    (tmp_path / "无关.mp3").write_bytes(b"")

    groups = discover_upload_groups(tmp_path)

    assert len(groups) == 1
    assert groups[0].case_name == "上传任务"
    assert groups[0].unit_name == "讲义"
    assert [path.name for path in groups[0].file_paths] == ["讲义.txt"]
    assert groups[0].skipped_media == ("无关.mp3",)


def test_discover_upload_groups_combines_multiple_flat_files_as_upload_materials(
    tmp_path,
):
    (tmp_path / "讲义.txt").write_text("主干内容", encoding="utf-8")
    (tmp_path / "补充.docx").write_bytes(b"")

    groups = discover_upload_groups(tmp_path)

    assert len(groups) == 1
    assert groups[0].unit_name == "上传资料"
    assert [path.name for path in groups[0].file_paths] == ["补充.docx", "讲义.txt"]


def test_collect_and_resolve_result_files(tmp_path):
    output = tmp_path / "output"
    result = output / "案例A" / "第1节.md"
    result.parent.mkdir(parents=True)
    result.write_text("# 结果", encoding="utf-8")

    files = collect_result_files(output)

    assert files == [
        {
            "path": "案例A/第1节.md",
            "name": "第1节.md",
            "size": result.stat().st_size,
        }
    ]
    assert resolve_result_file(output, "案例A/第1节.md") == result


def test_build_result_archive_preserves_result_tree(tmp_path):
    output = tmp_path / "output"
    result = output / "案例A" / "第1节.md"
    meta = output / "案例A" / "第1节.meta.json"
    hidden = output / ".image_cache" / "cached.txt"
    tmp_file = output / "manifest.json.tmp"
    result.parent.mkdir(parents=True)
    hidden.parent.mkdir(parents=True)
    result.write_text("# 结果", encoding="utf-8")
    meta.write_text("{}", encoding="utf-8")
    hidden.write_text("缓存", encoding="utf-8")
    tmp_file.write_text("临时文件", encoding="utf-8")

    archive = build_result_archive(output, tmp_path / "结果.zip")

    with ZipFile(archive) as zf:
        assert zf.namelist() == ["案例A/第1节.md", "案例A/第1节.meta.json"]
        assert zf.read("案例A/第1节.md").decode("utf-8") == "# 结果"


def test_resolve_result_archive_builds_download_zip(tmp_path):
    output = tmp_path / "output"
    result = output / "案例A" / "第1节.md"
    result.parent.mkdir(parents=True)
    result.write_text("# 结果", encoding="utf-8")

    archive = resolve_result_archive(output, tmp_path / "results.zip")

    assert archive.name == "results.zip"
    with ZipFile(archive) as zf:
        assert zf.namelist() == ["案例A/第1节.md"]


def test_resolve_result_archive_requires_results(tmp_path):
    output = tmp_path / "output"
    output.mkdir()

    with pytest.raises(ValueError, match="暂无可打包的结果文件"):
        resolve_result_archive(output, tmp_path / "results.zip")


def test_resolve_result_file_rejects_path_escape(tmp_path):
    output = tmp_path / "output"
    output.mkdir()

    with pytest.raises(ValueError, match="不安全的下载路径"):
        resolve_result_file(output, "../secret.txt")


def test_web_task_runner_processes_task_and_collects_results(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "素材.txt").write_text("素材内容", encoding="utf-8")
    runner = WebTaskRunner(work_dir=tmp_path / "runs")
    runner.tasks["task-1"] = TaskRecord(
        task_id="task-1", input_dir=input_dir, output_dir=output_dir
    )

    async def fake_run_pipeline(groups, model, **kwargs):
        result = kwargs["output_dir"] / "上传任务" / f"{groups[0].unit_name}.md"
        result.parent.mkdir(parents=True)
        result.write_text("# 结果", encoding="utf-8")
        return [
            SectionResult(
                case_name="上传任务",
                section_name="上传资料",
                identifier="task",
                status="ok",
                markdown_path=str(result),
            )
        ]

    monkeypatch.setattr(web_tasks, "build_chat_model", lambda: object())
    monkeypatch.setattr(web_tasks, "run_pipeline", fake_run_pipeline)

    asyncio.run(
        runner.process_task(
            "task-1", {"vision": False, "review": False, "auto_fix": False}
        )
    )

    task = runner.get_task("task-1")
    assert task["status"] == "succeeded"
    assert task["message"] == "处理完成"
    assert task["result_files"][0]["path"] == "上传任务/素材.md"
