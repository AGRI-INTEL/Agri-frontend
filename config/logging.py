"""
Logging configuration
"""

import logging
import logging.config
import os
from pathlib import Path

from config.config import get_settings

settings = get_settings()


def setup_logging():
    """Setup application logging"""

    # Create logs directory — ignore permission errors in Docker
    log_dir = Path("logs")
    try:
        log_dir.mkdir(exist_ok=True)
    except PermissionError:
        pass

    # Check if we can actually write to the log files
    can_write_logs = os.access(str(log_dir), os.W_OK)

    handlers_config = {
        "console": {
            "class": "logging.StreamHandler",
            "level": settings.LOG_LEVEL,
            "formatter": "default",
        },
    }

    # Only add file handlers if we have write permission
    if can_write_logs:
        handlers_config["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": settings.LOG_LEVEL,
            "formatter": "detailed",
            "filename": settings.LOG_FILE,
            "maxBytes": 10485760,
            "backupCount": 5,
        }
        handlers_config["json_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": settings.LOG_LEVEL,
            "formatter": "json",
            "filename": "logs/agriintel360-json.log",
            "maxBytes": 10485760,
            "backupCount": 5,
        }

    active_handlers = list(handlers_config.keys())

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[{asctime}] {levelname} in {name}: {message}",
                "style": "{",
            },
            "detailed": {
                "format": "[{asctime}] {levelname} {name}:{lineno} - {message}",
                "style": "{",
            },
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            },
        },
        "handlers": handlers_config,
        "loggers": {
            "app": {
                "level": settings.LOG_LEVEL,
                "handlers": active_handlers,
                "propagate": False,
            },
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
        },
        "root": {
            "level": settings.LOG_LEVEL,
            "handlers": active_handlers,
        },
    }

    logging.config.dictConfig(logging_config)

    logger = logging.getLogger("app")
    if not can_write_logs:
        logger.warning("Log directory not writable — logging to console only")
    else:
        logger.info(f"Logging setup complete. Level: {settings.LOG_LEVEL}")

    return logger