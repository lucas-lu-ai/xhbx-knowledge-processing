from __future__ import annotations

import logging
from datetime import date

from insurance_coach_agents.logging_config import DatedFileHandler, configure_logging


def test_configure_logging_writes_to_dated_file(tmp_path):
    log_path = configure_logging(
        log_dir=tmp_path,
        console=False,
        force=True,
        date_provider=lambda: date(2026, 6, 26),
    )

    logger = logging.getLogger("insurance_coach_agents")
    logger.info("日志消息")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_path == tmp_path / "insurance-coach-2026-06-26.log"
    assert "日志消息" in log_path.read_text(encoding="utf-8")


def test_dated_file_handler_rolls_to_new_file(tmp_path):
    current_date = date(2026, 6, 26)
    handler = DatedFileHandler(tmp_path, date_provider=lambda: current_date)
    logger = logging.getLogger("insurance_coach_agents.tests.daily")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        logger.info("第一天")
        current_date = date(2026, 6, 27)
        logger.info("第二天")
        handler.flush()
    finally:
        logger.handlers = []
        handler.close()

    first = tmp_path / "insurance-coach-2026-06-26.log"
    second = tmp_path / "insurance-coach-2026-06-27.log"
    assert "第一天" in first.read_text(encoding="utf-8")
    assert "第二天" in second.read_text(encoding="utf-8")
