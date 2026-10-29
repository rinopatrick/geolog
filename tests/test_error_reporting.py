"""Optional error webhook behavior and redaction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend import error_reporting


class FakeRequest:
    method = "POST"
    headers = {"X-Request-ID": "header-rid"}
    url = SimpleNamespace(path="/api/wells/1/compute", query="token=secret")
    state = SimpleNamespace(
        request_id="state-rid",
        trace_id="trace-123",
        user_role="interpreter",
    )


@pytest.fixture(autouse=True)
def clear_state(monkeypatch):
    error_reporting._RECENT.clear()
    monkeypatch.delenv("GEOLOG_ERROR_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("GEOLOG_ERROR_WEBHOOK_INCLUDE_TRACE", raising=False)


def test_disabled_without_url(monkeypatch):
    called = []
    monkeypatch.setattr(error_reporting, "_dispatch", lambda *a: called.append(a))
    assert error_reporting.report_exception(FakeRequest(), RuntimeError("boom")) is False
    assert called == []


def test_payload_is_redacted_and_queued(monkeypatch):
    monkeypatch.setenv("GEOLOG_ERROR_WEBHOOK_URL", "https://errors.example.test/hook")
    sent = []
    monkeypatch.setattr(error_reporting, "_dispatch", lambda url, payload: sent.append((url, payload)))

    assert error_reporting.report_exception(FakeRequest(), RuntimeError("boom")) is True
    assert len(sent) == 1
    url, payload = sent[0]
    assert url == "https://errors.example.test/hook"
    assert payload["path"] == "/api/wells/1/compute"
    assert payload["request_id"] == "state-rid"
    assert payload["trace_id"] == "trace-123"
    assert payload["role"] == "interpreter"
    assert payload["exception_type"] == "RuntimeError"
    assert payload["exception"] == "boom"
    assert "query" not in payload
    assert "secret" not in str(payload)
    assert "traceback" not in payload


def test_traceback_is_opt_in(monkeypatch):
    monkeypatch.setenv("GEOLOG_ERROR_WEBHOOK_URL", "https://errors.example.test/hook")
    monkeypatch.setenv("GEOLOG_ERROR_WEBHOOK_INCLUDE_TRACE", "true")
    sent = []
    monkeypatch.setattr(error_reporting, "_dispatch", lambda url, payload: sent.append(payload))
    try:
        raise ValueError("bad value")
    except ValueError as exc:
        error_reporting.report_exception(FakeRequest(), exc)
    assert "Traceback" in sent[0]["traceback"]


def test_duplicate_errors_are_throttled(monkeypatch):
    monkeypatch.setenv("GEOLOG_ERROR_WEBHOOK_URL", "https://errors.example.test/hook")
    sent = []
    monkeypatch.setattr(error_reporting, "_dispatch", lambda url, payload: sent.append(payload))

    assert error_reporting.report_exception(FakeRequest(), RuntimeError("one")) is True
    assert error_reporting.report_exception(FakeRequest(), RuntimeError("two")) is False
    assert len(sent) == 1
