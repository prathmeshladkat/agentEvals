import logging

import httpx
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

log = logging.getLogger("vobs.tracing")


class ApiSpanExporter(SpanExporter):
    """Sends finished spans to our ingestion API as JSON."""

    def __init__(self, url: str, adapter=None):
        self._url = url
        self._adapter = adapter
        self._client = httpx.Client(timeout=5)

    def export(self, spans) -> SpanExportResult:
        payload = [self._to_dict(s) for s in spans]
        if self._adapter:
            payload = [self._adapter(p) for p in payload]
        try:
            self._client.post(self._url, json=payload).raise_for_status()
            return SpanExportResult.SUCCESS
        except Exception as e:
            log.warning("span export failed: %s", e)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self._client.close()

    @staticmethod
    def _to_dict(span) -> dict:
        ctx = span.get_span_context()
        return {
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
            "parent_span_id": format(span.parent.span_id, "016x") if span.parent else None,
            "name": span.name,
            "start_ns": span.start_time,
            "end_ns": span.end_time,
            "status": "error" if span.status.status_code.name == "ERROR" else "ok",
            "attributes": dict(span.attributes or {}),
            "events": [
                {"name": e.name, "ts_ns": e.timestamp, "attributes": dict(e.attributes or {})}
                for e in span.events
            ],
        }


def setup_tracing(
    service_name: str = "clinic-agent",
    api_url: str = "http://localhost:8000/v1/spans",
    adapter=None
) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(ApiSpanExporter(api_url, adapter)))
    return provider