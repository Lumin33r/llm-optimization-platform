"""Structured logging configuration with OTEL context propagation.

JSON formatter that automatically injects trace_id and span_id from the
current OpenTelemetry context into every log record, enabling Loki ↔ Tempo
correlation as defined in design-08-otel-schema.md Section 5.
"""

import logging
import json
from opentelemetry import trace
from datetime import datetime


class OTelJSONFormatter(logging.Formatter):
    """JSON formatter with OTel trace correlation."""

    def __init__(self, service_name: str, team: str):
        super().__init__()
        self.service_name = service_name
        self.team = team

    def format(self, record: logging.LogRecord) -> str:
        # Get current trace context
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None

        log_dict = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "service.name": self.service_name,
            "lab.team": self.team,
        }

        # Add trace correlation
        if ctx and ctx.is_valid:
            log_dict["trace_id"] = format(ctx.trace_id, "032x")
            log_dict["span_id"] = format(ctx.span_id, "016x")

        # Add extra attributes from record
        if hasattr(record, "lab_attributes"):
            log_dict.update(record.lab_attributes)

        # Add exception info
        if record.exc_info:
            log_dict["error.type"] = record.exc_info[0].__name__
            log_dict["error.message"] = str(record.exc_info[1])

        return json.dumps(log_dict)


def configure_logging(service_name: str, team: str, level: str = "INFO"):
    """Configure JSON logging with OTel correlation."""
    handler = logging.StreamHandler()
    handler.setFormatter(OTelJSONFormatter(service_name, team))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    return root
