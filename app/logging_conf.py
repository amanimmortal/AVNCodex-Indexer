import logging
import logging.config
import structlog

from app.settings import settings
from pathlib import Path


def configure_logging():
    """
    Configures logging for the application using structlog and standard logging.
    """
    log_level = settings.LOG_LEVEL.upper()
    json_format = settings.LOG_JSON_FORMAT

    # Create logs directory if it doesn't exist
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Handlers config
    handlers = {
        "console": {
            "level": log_level,
            "class": "logging.StreamHandler",
            "formatter": "colored" if not json_format else "json",
        },
        "file": {
            "level": log_level,
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "data/logs/app.json",
            "mode": "a",
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
            "formatter": "json",
            "encoding": "utf-8",
        },
    }

    # Processors shared between structlog and standard logging
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
                "foreign_pre_chain": shared_processors,
            },
            "colored": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(colors=True),
                "foreign_pre_chain": shared_processors,
            },
        },
        "handlers": handlers,
        "loggers": {
            "": {
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": True,
            },
            "uvicorn.access": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False,
            },
            # Prevent noisy libraries from flooding logs unless DEBUG
            "httpcore": {"level": "WARNING"},
            "httpx": {"level": "WARNING"},
        },
    }

    logging.config.dictConfig(logging_config)

    # Structlog configuration
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
