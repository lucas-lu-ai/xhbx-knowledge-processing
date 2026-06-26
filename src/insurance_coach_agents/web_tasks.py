"""Web 上传任务管理：保存素材、执行流水线、暴露下载文件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import BackgroundTasks, UploadFile

from .agents import build_chat_model, build_vision_model
from .config import (
    EXTENSION_TO_TYPE,
    MEDIA_EXTENSIONS,
    PROJECT_ROOT,
)
from .parsers.grouping import SourceGroup, group_by_directory, group_by_single_file
from .pipeline import run_pipeline

WEB_RUNS_DIR = PROJECT_ROOT / "web_runs"
SUPPORTED_UPLOAD_EXTENSIONS = frozenset({".zip", *EXTENSION_TO_TYPE.keys()})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_upload_name(filename: str | None) -> str:
    name = Path(filename or "upload").name.strip()
    return name or "upload"


def safe_extract_zip(archive_path: Path, target_dir: Path) -> None:
    """安全解压 zip，拒绝 path traversal 成员。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    root = target_dir.resolve()
    with ZipFile(archive_path) as zf:
        for info in zf.infolist():
            member_name = info.filename.replace("\\", "/")
            parts = PurePosixPath(member_name).parts
            if (
                not parts
                or PurePosixPath(member_name).is_absolute()
                or any(part in {"", ".", ".."} for part in parts)
            ):
                raise ValueError(f"不安全的压缩包路径：{info.filename}")
            target = (target_dir / Path(*parts)).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"不安全的压缩包路径：{info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                dst.write(src.read())


def _direct_group(root: Path) -> SourceGroup | None:
    files: list[Path] = []
    skipped_media: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_file():
            continue
        suffix = child.suffix.lower()
        if suffix in EXTENSION_TO_TYPE:
            files.append(child)
        elif suffix in MEDIA_EXTENSIONS:
            skipped_media.append(child.name)
    if not files:
        return None
    unit_name = files[0].stem if len(files) == 1 else "上传资料"
    return SourceGroup(
        case_name="上传任务",
        unit_name=unit_name,
        identifier=str(root),
        file_paths=tuple(files),
        skipped_media=tuple(skipped_media),
    )


def discover_upload_groups(input_dir: Path) -> list[SourceGroup]:
    """把一次上传目录转换为待处理知识单元。"""
    groups: list[SourceGroup] = []
    direct = _direct_group(input_dir)
    if direct is not None:
        groups.append(direct)
    groups.extend(group_by_directory(input_dir))
    if groups:
        return groups
    return group_by_single_file(input_dir)


def collect_result_files(output_dir: Path) -> list[dict[str, Any]]:
    """列出可下载的结果文件，返回相对路径、文件名和字节数。"""
    if not output_dir.exists():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(output_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if path.name.endswith(".tmp"):
            continue
        files.append(
            {
                "path": rel.as_posix(),
                "name": path.name,
                "size": path.stat().st_size,
            }
        )
    return files


def build_result_archive(output_dir: Path, archive_path: Path) -> Path:
    """把结果目录打成 zip，保留相对路径。"""
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as zf:
        for file in collect_result_files(output_dir):
            zf.write(output_dir / file["path"], file["path"])
    return archive_path


def resolve_result_archive(output_dir: Path, archive_path: Path) -> Path:
    """生成并返回结果 zip；没有结果时拒绝下载。"""
    if not collect_result_files(output_dir):
        raise ValueError("暂无可打包的结果文件")
    return build_result_archive(output_dir, archive_path)


def resolve_result_file(output_dir: Path, relative_path: str) -> Path:
    """把下载相对路径解析为真实文件，拒绝越界。"""
    root = output_dir.resolve()
    target = (output_dir / relative_path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError(f"不安全的下载路径：{relative_path}")
    return target


@dataclass
class TaskRecord:
    task_id: str
    input_dir: Path
    output_dir: Path
    status: str = "queued"
    message: str = "已加入队列"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    result_files: list[dict[str, Any]] = field(default_factory=list)

    def update(self, *, status: str | None = None, message: str | None = None) -> None:
        if status is not None:
            self.status = status
        if message is not None:
            self.message = message
        self.updated_at = _now_iso()

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "message": self.message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result_files": self.result_files,
        }


class WebTaskRunner:
    """内存任务表 + 本地文件工作区。"""

    def __init__(self, work_dir: Path = WEB_RUNS_DIR) -> None:
        self.work_dir = work_dir
        self.tasks: dict[str, TaskRecord] = {}

    async def submit_upload(
        self, upload: UploadFile, options: dict[str, bool], background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        filename = _safe_upload_name(upload.filename)
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
            raise ValueError(f"不支持的上传文件类型：{suffix or '无扩展名'}")

        task_id = uuid4().hex[:12]
        run_dir = self.work_dir / task_id
        input_dir = run_dir / "input"
        output_dir = run_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved = input_dir / filename
        saved.write_bytes(await upload.read())
        if suffix == ".zip":
            extracted = input_dir / "extracted"
            safe_extract_zip(saved, extracted)
            saved.unlink()
            input_dir = extracted

        record = TaskRecord(task_id=task_id, input_dir=input_dir, output_dir=output_dir)
        self.tasks[task_id] = record
        background_tasks.add_task(self.process_task, task_id, options)
        return record.snapshot()

    async def process_task(self, task_id: str, options: dict[str, bool]) -> None:
        record = self.tasks[task_id]
        record.update(status="running", message="正在解析并生成结果")
        try:
            groups = discover_upload_groups(record.input_dir)
            if not groups:
                raise RuntimeError("未发现支持的素材文件")
            model = build_chat_model()
            vision_enabled = options.get("vision", True)
            vision_model = build_vision_model() if vision_enabled else None
            results = await run_pipeline(
                groups,
                model,
                concurrency=1,
                force=True,
                output_dir=record.output_dir,
                vision=vision_enabled,
                vision_model=vision_model,
                review=options.get("review", False),
                auto_fix=options.get("auto_fix", False),
            )
            record.result_files = collect_result_files(record.output_dir)
            if record.result_files:
                self.resolve_archive(task_id)
            failed = [result for result in results if result.status == "failed"]
            if failed:
                record.update(
                    status="failed",
                    message=f"处理失败：{len(failed)}/{len(results)} 个单元失败",
                )
            else:
                record.update(status="succeeded", message="处理完成")
        except Exception as exc:  # noqa: BLE001 - Web 任务需把失败状态返回给前端
            record.result_files = collect_result_files(record.output_dir)
            record.update(status="failed", message=str(exc))

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        record = self.tasks.get(task_id)
        return record.snapshot() if record else None

    def list_files(self, task_id: str) -> list[dict[str, Any]]:
        record = self.tasks.get(task_id)
        if record is None:
            raise KeyError(task_id)
        record.result_files = collect_result_files(record.output_dir)
        return record.result_files

    def resolve_file(self, task_id: str, path: str) -> Path:
        record = self.tasks.get(task_id)
        if record is None:
            raise KeyError(task_id)
        return resolve_result_file(record.output_dir, path)

    def resolve_archive(self, task_id: str) -> Path:
        record = self.tasks.get(task_id)
        if record is None:
            raise KeyError(task_id)
        return resolve_result_archive(
            record.output_dir, record.output_dir.parent / "results.zip"
        )
