from __future__ import annotations

import re
from pathlib import Path

from fastapi import BackgroundTasks, UploadFile
from fastapi.testclient import TestClient

from insurance_coach_agents.web import create_app


class _FakeRunner:
    def __init__(self, result_file: Path) -> None:
        self.result_file = result_file
        self.received_options: dict | None = None
        self.received_filename = ""

    async def submit_upload(
        self, upload: UploadFile, options: dict, background_tasks: BackgroundTasks
    ) -> dict:
        self.received_filename = upload.filename or ""
        self.received_options = options
        return {
            "task_id": "task-1",
            "status": "queued",
            "message": "已加入队列",
            "result_files": [],
        }

    def get_task(self, task_id: str) -> dict | None:
        if task_id != "task-1":
            return None
        return {
            "task_id": "task-1",
            "status": "succeeded",
            "message": "处理完成",
            "result_files": [
                {
                    "path": self.result_file.name,
                    "name": self.result_file.name,
                    "size": self.result_file.stat().st_size,
                }
            ],
        }

    def list_files(self, task_id: str) -> list[dict]:
        task = self.get_task(task_id)
        return [] if task is None else task["result_files"]

    def resolve_file(self, task_id: str, path: str) -> Path:
        return self.result_file

    def resolve_archive(self, task_id: str) -> Path:
        return self.result_file


def _input_tag(html: str, element_id: str) -> str:
    match = re.search(rf'<input[^>]+id="{element_id}"[^>]*>', html)
    assert match is not None
    return match.group(0)


def test_web_app_default_options_match_review_workflow(tmp_path):
    result_file = tmp_path / "result.md"
    result_file.write_text("# 结果", encoding="utf-8")
    client = TestClient(create_app(_FakeRunner(result_file)))

    html = client.get("/").text

    assert "checked" not in _input_tag(html, "visionOption")
    assert "checked" in _input_tag(html, "reviewOption")
    assert "checked" in _input_tag(html, "autoFixOption")
    assert 'id="archiveButton"' in html


def test_web_app_upload_status_and_download_routes(tmp_path):
    result_file = tmp_path / "result.md"
    result_file.write_text("# 结果", encoding="utf-8")
    runner = _FakeRunner(result_file)
    client = TestClient(create_app(runner))

    index = client.get("/")
    assert index.status_code == 200
    assert "任务状态" in index.text

    upload = client.post(
        "/api/tasks",
        files={"file": ("demo.txt", b"hello", "text/plain")},
        data={"review": "true", "auto_fix": "true", "vision": "false"},
    )
    assert upload.status_code == 200
    assert upload.json()["task_id"] == "task-1"
    assert runner.received_filename == "demo.txt"
    assert runner.received_options == {
        "review": True,
        "auto_fix": True,
        "vision": False,
    }

    status = client.get("/api/tasks/task-1")
    assert status.status_code == 200
    assert status.json()["status"] == "succeeded"

    files = client.get("/api/tasks/task-1/files")
    assert files.status_code == 200
    assert files.json()[0]["path"] == "result.md"

    download = client.get("/api/tasks/task-1/files/result.md")
    assert download.status_code == 200
    assert download.text == "# 结果"

    archive = client.get("/api/tasks/task-1/archive")
    assert archive.status_code == 200
    assert archive.text == "# 结果"
