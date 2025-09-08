from __future__ import annotations
import logging, os, sys
from logging.handlers import RotatingFileHandler

class ShortFormatter(logging.Formatter):
    """
    Formatter that exposes %(shortname)s = last component of logger name (e.g., NetworkMonitor)
    """
    def format(self, record: logging.LogRecord) -> str:
        record.shortname = record.name.rsplit('.', 1)[-1]
        return super().format(record)

def setup_logging(enabled: bool = True, level: str | int = "INFO", log_file: str | None = None) -> None:
    """
    Configure root logging once. Format: timestamp level [logger.func] message
    Enable/disable with env RVT_LOGGING=1/0; level with RVT_LOG_LEVEL=INFO/DEBUG/etc.
    """
    # If already configured, do not duplicate handlers
    if getattr(setup_logging, "_configured", False):
        return

    if not enabled:
        logging.disable(logging.CRITICAL)
        setup_logging._configured = True
        return

    logging.disable(logging.NOTSET)
    lvl = logging.getLevelName(level) if isinstance(level, str) else level
    fmt = "%(asctime)s %(levelname)s [%(shortname)s.%(funcName)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = ShortFormatter(fmt=fmt, datefmt=datefmt)

    handlers: list[logging.Handler] = []
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(formatter)
    handlers.append(sh)

    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            fh = RotatingFileHandler(log_file, maxBytes=512_000, backupCount=3)
            fh.setFormatter(formatter)
            handlers.append(fh)
        except Exception:
            # Ignore file handler failures; keep console
            pass

    logging.basicConfig(level=lvl, handlers=handlers, force=True)
    setup_logging._configured = True

def resolve_logging_from_env_and_cfg(cfg) -> tuple[bool, str, str | None]:
    """
    Determine enabled/level/file using env first, then cfg if present.
    Env:
      RVT_LOGGING=1|0, RVT_LOG_LEVEL=DEBUG|INFO|..., RVT_LOG_FILE=/path/to/log
    """
    # env first
    env_enabled = os.getenv("RVT_LOGGING")
    enabled = (env_enabled is None) or (env_enabled.lower() not in ("0", "false", "no"))
    level = os.getenv("RVT_LOG_LEVEL", "INFO")
    log_file = os.getenv("RVT_LOG_FILE")

    # optional cfg fallback (no strict schema dependency)
    try:
        if hasattr(cfg, "logging"):
            lcfg = cfg.logging
            if hasattr(lcfg, "enabled") and env_enabled is None:
                enabled = bool(lcfg.enabled)
            if hasattr(lcfg, "level") and os.getenv("RVT_LOG_LEVEL") is None:
                level = str(lcfg.level)
            if hasattr(lcfg, "file") and os.getenv("RVT_LOG_FILE") is None:
                log_file = str(lcfg.file)
    except Exception:
        pass

    return enabled, level, log_file