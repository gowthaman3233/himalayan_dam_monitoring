"""Run-scoped logging.

Every pipeline execution gets a ``run_id``, and its log is written to
``outputs/logs/<run_id>.log``. The brief's ``runs`` table (Section 10) stores
that ``log_path``, so a stored result can always be traced back to the log of
the run that produced it.

Note: this module is ``utils.logging``, not the stdlib ``logging``. Python 3
uses absolute imports, so ``import logging`` below resolves to the stdlib.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config.schema import Config, LoggingConfig

#: Marks handlers installed by this module, so repeated setup calls replace
#: them instead of stacking duplicates (which would double every log line).
_HANDLER_TAG = "_hdm_handler"

#: Root logger name for the project; all module loggers hang off it.
ROOT_LOGGER_NAME = "hdm"


def new_run_id() -> str:
    """A sortable, unique identifier for one pipeline run.

    Format ``YYYYmmddTHHMMSSZ-<6 hex>``: UTC so runs sort chronologically
    regardless of local timezone, with a short random suffix so two runs started
    in the same second cannot collide.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def setup_logging(
    cfg: Config | LoggingConfig | None = None,
    *,
    run_id: str | None = None,
    log_dir: Path | None = None,
) -> tuple[logging.Logger, Path | None]:
    """Configure the project logger.

    Idempotent: calling it again replaces this module's handlers rather than
    adding more.

    Args:
        cfg: A full :class:`Config` or just its ``logging`` section. ``None``
            uses schema defaults.
        run_id: Reuse an existing run id; a new one is generated if omitted.
        log_dir: Override the log directory. Defaults to the configured
            ``paths.logs``.

    Returns:
        ``(logger, log_path)``. ``log_path`` is ``None`` when file logging is
        disabled.
    """
    log_cfg, resolved_dir = _resolve(cfg, log_dir)
    run_id = run_id or new_run_id()

    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)  # handlers do the filtering
    logger.propagate = False
    _clear_our_handlers(logger)

    formatter = logging.Formatter(log_cfg.format, datefmt=log_cfg.date_format)

    if log_cfg.to_console:
        console = logging.StreamHandler()
        console.setLevel(getattr(logging, log_cfg.level))
        console.setFormatter(formatter)
        setattr(console, _HANDLER_TAG, True)
        logger.addHandler(console)

    log_path: Path | None = None
    if log_cfg.to_file:
        resolved_dir.mkdir(parents=True, exist_ok=True)
        log_path = resolved_dir / f"{run_id}.log"
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(getattr(logging, log_cfg.file_level))
        file_handler.setFormatter(formatter)
        setattr(file_handler, _HANDLER_TAG, True)
        logger.addHandler(file_handler)

    if not logger.handlers:
        # Both sinks disabled: silence the "no handlers" warning explicitly
        # rather than letting stdlib logging emit its own message.
        logger.addHandler(logging.NullHandler())

    logger.debug("logging initialised (run_id=%s, log_path=%s)", run_id, log_path)
    return logger, log_path


def get_logger(name: str | None = None) -> logging.Logger:
    """Logger for a module, nested under the project root logger.

    Call with ``__name__``; the project prefix is added automatically.
    """
    if not name or name == ROOT_LOGGER_NAME:
        return logging.getLogger(ROOT_LOGGER_NAME)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def _resolve(
    cfg: Config | LoggingConfig | None, log_dir: Path | None
) -> tuple[LoggingConfig, Path]:
    """Work out the logging settings and the log directory."""
    from config.loader import repo_root

    if cfg is None:
        log_cfg = LoggingConfig()
        default_dir = repo_root() / "outputs" / "logs"
    elif isinstance(cfg, LoggingConfig):
        log_cfg = cfg
        default_dir = repo_root() / "outputs" / "logs"
    else:
        log_cfg = cfg.logging
        default_dir = (repo_root() / cfg.paths.logs).resolve()

    return log_cfg, Path(log_dir) if log_dir is not None else default_dir


def _clear_our_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_TAG, False) or isinstance(
            handler, logging.NullHandler
        ):
            logger.removeHandler(handler)
            handler.close()
