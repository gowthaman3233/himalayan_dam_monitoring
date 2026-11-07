"""Run-scoped logging setup."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from config.schema import Config, LoggingConfig
from utils.logging import ROOT_LOGGER_NAME, get_logger, new_run_id, setup_logging

RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}$")


def test_run_id_format_is_sortable_and_unique() -> None:
    first = new_run_id()
    assert RUN_ID_PATTERN.match(first), first
    assert len({new_run_id() for _ in range(200)}) == 200


def test_setup_writes_a_log_file_named_after_the_run(tmp_path: Path) -> None:
    run_id = new_run_id()
    logger, log_path = setup_logging(run_id=run_id, log_dir=tmp_path)

    assert log_path is not None
    assert log_path.name == f"{run_id}.log"

    logger.info("phase 0 smoke message")
    for handler in logger.handlers:
        handler.flush()

    assert "phase 0 smoke message" in log_path.read_text(encoding="utf-8")


def test_repeated_setup_does_not_duplicate_handlers(tmp_path: Path) -> None:
    """Stacked handlers would double every log line and every log file."""
    setup_logging(log_dir=tmp_path)
    first_count = len(logging.getLogger(ROOT_LOGGER_NAME).handlers)

    for _ in range(4):
        setup_logging(log_dir=tmp_path)

    assert len(logging.getLogger(ROOT_LOGGER_NAME).handlers) == first_count


def test_file_logging_can_be_disabled(tmp_path: Path) -> None:
    _, log_path = setup_logging(
        LoggingConfig(to_file=False, to_console=True), log_dir=tmp_path
    )
    assert log_path is None
    assert not list(tmp_path.glob("*.log"))


def test_both_sinks_disabled_is_silent_not_broken(tmp_path: Path) -> None:
    logger, log_path = setup_logging(
        LoggingConfig(to_file=False, to_console=False), log_dir=tmp_path
    )
    assert log_path is None
    logger.warning("should not raise")  # a NullHandler keeps stdlib logging quiet


def test_file_level_can_be_more_verbose_than_console(tmp_path: Path) -> None:
    """DEBUG detail belongs in the run log even when the console shows INFO."""
    logger, log_path = setup_logging(
        LoggingConfig(level="INFO", file_level="DEBUG"), log_dir=tmp_path
    )
    assert log_path is not None
    logger.debug("debug detail for the run log")
    for handler in logger.handlers:
        handler.flush()
    assert "debug detail for the run log" in log_path.read_text(encoding="utf-8")


def test_module_loggers_nest_under_the_project_root(tmp_path: Path) -> None:
    setup_logging(log_dir=tmp_path)
    child = get_logger("detection.water")
    assert child.name == f"{ROOT_LOGGER_NAME}.detection.water"
    assert get_logger(None).name == ROOT_LOGGER_NAME


def test_setup_from_a_full_config_uses_the_configured_log_dir(
    cfg: Config, tmp_path: Path
) -> None:
    """A full Config is accepted as well as a bare LoggingConfig."""
    _, log_path = setup_logging(cfg, log_dir=tmp_path)
    assert log_path is not None and log_path.parent == tmp_path
