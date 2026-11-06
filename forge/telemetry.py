"""Local, content-free JSON telemetry. No document text, question, or model output."""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult


class LocalExporter(SpanExporter):
    def __init__(self, path: Path):
        self.handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=2)

    def export(self, spans: Any) -> SpanExportResult:
        try:
            for span in spans:
                self.write(span)
            return SpanExportResult.SUCCESS
        except OSError:
            return SpanExportResult.FAILURE

    def write(self, span: ReadableSpan) -> None:
        context = span.get_span_context()
        payload = {
            "name": span.name,
            "trace_id": f"{context.trace_id:032x}" if context else None,
            "span_id": f"{context.span_id:016x}" if context else None,
            "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else None,
            "start": span.start_time,
            "end": span.end_time,
            "attributes": dict(span.attributes or {}),
        }
        self.handler.emit(logging.makeLogRecord({"msg": json.dumps(payload), "levelno": 20}))

    def shutdown(self) -> None:
        self.handler.close()


def configure(data_dir: Path) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": "ai-platform-forge"}))
    provider.add_span_processor(SimpleSpanProcessor(LocalExporter(data_dir / "traces.jsonl")))
    return provider
