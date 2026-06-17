"""
Structured logging configuration for Studio Voice API.

Uses stdlib only (no structlog dependency).
- Console: human-readable format with timestamp, level, message, context fields
- File: JSON lines to apps/logs/studio.log with rotation (10MB x 5 backups)
- Request correlation IDs via contextvars (set by RequestLoggingMiddleware)
"""

import json
import logging
import logging.handlers
from pathlib import Path
from contextvars import ContextVar

# Per-request context stored in contextvars (async-safe, no threading issues)
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_endpoint_var: ContextVar[str] = ContextVar("endpoint", default="")


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_context(request_id: str, endpoint: str = "") -> None:
    _request_id_var.set(request_id)
    _endpoint_var.set(endpoint)


def clear_request_context() -> None:
    _request_id_var.set("")
    _endpoint_var.set("")


class _ContextFilter(logging.Filter):
    """Inject request_id and endpoint from contextvars into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get() or "-"
        record.endpoint = _endpoint_var.get() or "-"
        return True


class _JsonFormatter(logging.Formatter):
    """One JSON object per line. Includes exc_info when present."""

    def format(self, record: logging.LogRecord) -> str:
        self.formatMessage(record)  # populate record.message
        obj: dict = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "endpoint": getattr(record, "endpoint", "-"),
        }
        # Merge any extra kwargs passed via logger.info("msg", extra={...})
        for key, val in record.__dict__.items():
            if key not in _STDLIB_LOG_ATTRS and not key.startswith("_"):
                obj[key] = val

        if record.exc_info:
            obj["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(obj, ensure_ascii=False, default=str)


# Attributes that are always on LogRecord — skip them when building JSON extra fields
_STDLIB_LOG_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
    "request_id", "endpoint",
})

_CONSOLE_FORMAT = (
    "%(asctime)s.%(msecs)03d [%(levelname)-8s] %(name)s"
    " | %(message)s"
    " | req=%(request_id)s"
)
_CONSOLE_DATE_FORMAT = "%H:%M:%S"


def setup_logging(dev_mode: bool = True, log_dir: Path | None = None) -> None:
    """
    Configure root logger and 'studio_api' logger.

    Args:
        dev_mode: True = console only (human-readable).
                  False = console + JSON file handler.
        log_dir:  Directory for log files. Defaults to apps/logs/ next to this file.
    """
    context_filter = _ContextFilter()

    # --- Console handler ---
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(fmt=_CONSOLE_FORMAT, datefmt=_CONSOLE_DATE_FORMAT)
    )
    console_handler.addFilter(context_filter)
    console_handler.setLevel(logging.DEBUG if dev_mode else logging.INFO)

    handlers: list[logging.Handler] = [console_handler]

    # --- File handler (production / always) ---
    if log_dir is None:
        log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "studio.log"

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(_JsonFormatter())
    file_handler.addFilter(context_filter)
    file_handler.setLevel(logging.INFO)
    handlers.append(file_handler)

    # --- Root logger ---
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Remove any handlers added by previous basicConfig calls
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
