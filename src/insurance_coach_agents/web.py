"""保险知识沉淀 Web 界面入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .logging_config import configure_logging
from .web_tasks import WebTaskRunner

STATIC_DIR = Path(__file__).resolve().parent / "web_static"


def _runner(app: FastAPI) -> Any:
    return app.state.runner


def create_app(runner: Any | None = None) -> FastAPI:
    app = FastAPI(title="保险知识沉淀工作台")
    app.state.runner = runner or WebTaskRunner()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    @app.post("/api/tasks")
    async def create_task(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        review: bool = Form(False),
        auto_fix: bool = Form(False),
        vision: bool = Form(True),
    ) -> dict[str, Any]:
        if auto_fix and not review:
            raise HTTPException(status_code=400, detail="--auto-fix 需要同时启用质检")
        options = {"review": review, "auto_fix": auto_fix, "vision": vision}
        try:
            return await _runner(app).submit_upload(file, options, background_tasks)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        task = _runner(app).get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task

    @app.get("/api/tasks/{task_id}/files")
    def list_files(task_id: str) -> list[dict[str, Any]]:
        try:
            return _runner(app).list_files(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="任务不存在") from exc

    @app.get("/api/tasks/{task_id}/files/{file_path:path}")
    def download_file(task_id: str, file_path: str) -> FileResponse:
        try:
            path = _runner(app).resolve_file(task_id, file_path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="任务不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(path, filename=path.name)

    @app.get("/api/tasks/{task_id}/archive")
    def download_archive(task_id: str) -> FileResponse:
        try:
            path = _runner(app).resolve_archive(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="任务不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(path, filename="results.zip")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    configure_logging()
    uvicorn.run(
        "insurance_coach_agents.web:app",
        host="127.0.0.1",
        port=6543,
        reload=False,
    )
