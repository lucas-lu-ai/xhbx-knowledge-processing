"""项目日志配置：控制台输出 + 按日期落盘。"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Callable

from .config import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "logs"
LOG_PREFIX = "insurance-coach"


class DatedFileHandler(logging.Handler):
    """按当前日期写入 ``<prefix>-YYYY-MM-DD.log`` 的日志 handler。"""

    def __init__(
        self,
        log_dir: Path = LOG_DIR,
        *,
        date_provider: Callable[[], date] = date.today,
        prefix: str = LOG_PREFIX,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__()
        self.log_dir = log_dir
        self.date_provider = date_provider
        self.prefix = prefix
        self.encoding = encoding
        self._current_date: date | None = None
        self._handler: logging.FileHandler | None = None
        self._switch_file_if_needed()

    def _path_for(self, value: date) -> Path:
        return self.log_dir / f"{self.prefix}-{value.isoformat()}.log"

    def _switch_file_if_needed(self) -> None:
        today = self.date_provider()
        if self._handler is not None and today == self._current_date:
            return
        if self._handler is not None:
            self._handler.close()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_date = today
        self._handler = logging.FileHandler(
            self._path_for(today), encoding=self.encoding
        )
        self._handler.setFormatter(self.formatter)

    def setFormatter(self, fmt: logging.Formatter | None) -> None:  # noqa: N802
        super().setFormatter(fmt)
        if self._handler is not None:
            self._handler.setFormatter(fmt)

    def emit(self, record: logging.LogRecord) -> None:
        self._switch_file_if_needed()
        if self._handler is not None:
            self._handler.emit(record)

    def flush(self) -> None:
        if self._handler is not None:
            self._handler.flush()

    def close(self) -> None:
        try:
            if self._handler is not None:
                self._handler.close()
        finally:
            self._handler = None
            super().close()


def configure_logging(
    *,
    log_dir: Path = LOG_DIR,
    console: bool = True,
    force: bool = False,
    date_provider: Callable[[], date] = date.today,
) -> Path:
    """配置根 logger，返回当前日期对应的日志文件路径。"""
    root = logging.getLogger()
    if force:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
    elif any(getattr(handler, "_insurance_coach_handler", False) for handler in root.handlers):
        return log_dir / f"{LOG_PREFIX}-{date_provider().isoformat()}.log"

    root.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(message)s")
    file_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler._insurance_coach_handler = True  # type: ignore[attr-defined]
        root.addHandler(console_handler)

    file_handler = DatedFileHandler(log_dir, date_provider=date_provider)
    file_handler.setFormatter(file_formatter)
    file_handler._insurance_coach_handler = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    return log_dir / f"{LOG_PREFIX}-{date_provider().isoformat()}.log"
