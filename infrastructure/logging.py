"""
infrastructure/logging.py

Structured JSON & formatted application logging with correlation ID propagation.

ARCHITECTURAL PRINCIPLES (Block 8, Requirement 9):
1. Injects correlation_id from contextvars into all log records.
2. Sanitizes sensitive keys (secrets, tokens, passwords, payload PII) before output.
3. Supports standard structured fields (timestamp, level, component, event, duration_ms).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from apps.api.middleware.correlation import get_correlation_id

# Regex patterns for masking sensitive secrets
SECRET_PATTERNS = [
    (re.compile(r'(?i)(api[-_]?key|secret|password|bearer|authorization)["\s:=]+([^\s,";}{]+)'), r'\1="***REDACTED***"'),
    (re.compile(r'(?i)(cvv|card_number|token)["\s:=]+([^\s,";}{]+)'), r'\1="***REDACTED***"'),
    (re.compile(r'(?i)(postgresql(?:\+[a-z0-9_]+)?://[^:]+:)([^@]+)(@)'), r'\1***REDACTED***\3'),
    (re.compile(r'\bAIza[0-9A-Za-z-_]{20,45}\b'), '***REDACTED_GEMINI_KEY***'),
]


def sanitize_log_message(msg: str) -> str:
    """Mask credentials, tokens, connection strings, and sensitive keys in log messages."""
    sanitized = msg
    for pattern, repl in SECRET_PATTERNS:
        sanitized = pattern.sub(repl, sanitized)
    return sanitized


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured JSON with correlation IDs."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_log_message(record.getMessage()),
            "correlation_id": getattr(record, "correlation_id", None) or get_correlation_id(),
        }

        # Attach extra structured fields if present
        for field in ("component", "event_name", "recovery_case_id", "action_id", "outbox_id", "duration_ms"):
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class CorrelationIdFilter(logging.Filter):
    """Logging filter to inject active correlation ID into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id") or not record.correlation_id:
            record.correlation_id = get_correlation_id()
        return True


def configure_structured_logging(log_level: str = "INFO", json_format: bool = False) -> None:
    """Configure root and application loggers with correlation filters and formatters."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.addFilter(CorrelationIdFilter())

    if json_format:
        handler.setFormatter(StructuredJsonFormatter())
    else:
        fmt = "%(asctime)s [%(levelname)s] [%(name)s] [corr=%(correlation_id)s] %(message)s"
        handler.setFormatter(logging.Formatter(fmt))

    root_logger.addHandler(handler)
