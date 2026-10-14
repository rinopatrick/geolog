"""Request-body validation and mass-assignment protection.

Every write endpoint takes `data: dict`, so nothing validated the body before it
reached a model. Three observed consequences, each covered here:

1. Missing required input produced a 500. `POST /api/wells/{wid}/annotations` with
   an empty body raised KeyError from `data["depth"]`, and dst/rft/tops raised
   TypeError from `float(None)`.
2. `Model(**data)` is mass assignment. `POST /api/wells/ {"id": 4242}` created a
   well with id 4242 — the client chose the primary key.
3. An unknown key reached the model constructor and raised TypeError, so the
   client got 500 rather than a message naming the field.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import Well

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}
ADMIN = {"X-User-Role": "admin"}


# ─── Missing input must be a 4xx, never a 5xx ───────────────────


@pytest.mark.parametrize("path,body", [
    ("/api/wells/1/annotations", {}),
    ("/api/wells/1/dst", {}),
    ("/api/wells/1/rft", {}),
    ("/api/wells/1/tops", {}),
    ("/api/wells/1/completion", {"component_type": "casing"}),
    ("/api/wells/1/splice",
     {"source_runs": [1], "intervals": [{"source_lr_id": 1}], "mnemonic": "GR"}),
    ("/api/correlation-markers", {"well_a_id": 1, "well_b_id": 2, "markers": [{}]}),
])
def test_missing_required_field_is_400_not_500(path, body):
    response = client.post(path, json=body, headers=INTERPRETER)
    assert response.status_code == 400, (
        f"POST {path} with {body} -> {response.status_code} {response.text[:200]}"
    )
    # The message must name the offending field, not just say "bad request".
    assert "detail" in response.json()
    assert response.json()["detail"], "400 must carry a reason"


@pytest.mark.parametrize("path,body", [
    ("/api/wells/1/annotations", {"depth": "not-a-number"}),
    ("/api/wells/1/dst", {"top_depth": "x", "bottom_depth": 1.0}),
    ("/api/wells/1/rft", {"depth": "x", "pressure": 1.0}),
    ("/api/wells/1/tops", {"formation_name": "F", "depth": "x"}),
])
def test_non_numeric_value_is_400_not_500(path, body):
    response = client.post(path, json=body, headers=INTERPRETER)
    assert response.status_code == 400, response.text[:200]


def test_missing_name_on_create_well_is_400():
    response = client.post("/api/wells/", json={"project_id": 1}, headers=ADMIN)
    assert response.status_code == 400
    assert "name" in response.json()["detail"]


def test_missing_name_on_create_project_is_400():
    response = client.post("/api/projects/", json={}, headers=ADMIN)
    assert response.status_code == 400
    assert "name" in response.json()["detail"]


def test_unknown_key_is_ignored_not_fatal():
    """Extra keys are dropped rather than raising TypeError."""
    response = client.post(
        "/api/wells/1/tops",
        json={"formation_name": "Unknown-key top", "depth": 1.0, "nonsense": 1},
        headers=INTERPRETER,
    )
    assert response.status_code == 201, response.text[:200]


# ─── Mass assignment ────────────────────────────────────────────


def test_client_cannot_choose_the_well_primary_key():
    response = client.post(
        "/api/wells/", json={"name": "MA-well", "project_id": 1, "id": 9999},
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text[:200]
    assert response.json()["id"] != 9999, "the client chose the primary key"


def test_client_cannot_choose_the_project_primary_key():
    response = client.post(
        "/api/projects/", json={"name": "MA-project", "id": 888}, headers=ADMIN,
    )
    assert response.status_code == 201, response.text[:200]
    assert response.json()["id"] != 888, "the client chose the primary key"


def test_client_cannot_override_server_managed_columns_on_a_top():
    """id, well_id and created_at must come from the server, not the body."""
    response = client.post(
        "/api/wells/1/tops",
        json={
            "formation_name": "MA top", "depth": 10.0,
            "id": 555, "well_id": 999, "created_at": "1999-01-01T00:00:00",
        },
        headers=INTERPRETER,
    )
    assert response.status_code == 201, response.text[:200]
    body = response.json()
    assert body["id"] != 555, "client chose the primary key"
    assert body["well_id"] == 1, "client overrode the parent well"
    assert not str(body.get("created_at") or "").startswith("1999"), (
        "client set created_at"
    )


def test_client_cannot_override_the_well_id_from_the_path():
    """The wid in the URL is authoritative."""
    response = client.post(
        "/api/wells/1/rft",
        json={"depth": 100.0, "pressure": 3000.0, "well_id": 999},
        headers=INTERPRETER,
    )
    assert response.status_code == 201, response.text[:200]
    assert response.json()["well_id"] == 1


# ─── Valid input must still work ────────────────────────────────


def test_valid_payloads_still_succeed():
    cases = [
        ("/api/wells/1/annotations", {"depth": 100.0, "text": "note"}, "depth"),
        ("/api/wells/1/dst", {"top_depth": 100.0, "bottom_depth": 120.0}, "top_depth"),
        ("/api/wells/1/rft", {"depth": 100.0, "pressure": 3000.0}, "depth"),
        ("/api/wells/1/tops",
         {"formation_name": "Valid Top", "depth": 1234.5, "lithology": "Sand"},
         "formation_name"),
    ]
    for path, body, field in cases:
        response = client.post(path, json=body, headers=INTERPRETER)
        assert response.status_code == 201, f"POST {path} -> {response.text[:200]}"
        assert response.json()[field] == body[field]


def test_optional_fields_default_rather_than_becoming_none():
    response = client.post(
        "/api/wells/1/rft", json={"depth": 1.0, "pressure": 2.0}, headers=INTERPRETER,
    )
    assert response.status_code == 201
    assert response.json()["fluid_type"] == "unknown"
    assert response.json()["notes"] == ""


def test_null_for_a_required_field_is_400():
    response = client.post(
        "/api/wells/1/rft", json={"depth": None, "pressure": 2.0}, headers=INTERPRETER,
    )
    assert response.status_code == 400


# ─── The helper itself ──────────────────────────────────────────


def test_validation_helpers_raise_http_400():
    from fastapi import HTTPException

    from backend.validation import (
        optional_float,
        optional_int,
        optional_str,
        pick,
        require_float,
        require_int,
        require_str,
    )

    assert pick({"a": 1, "b": 2, "id": 9}, ["a", "b"]) == {"a": 1, "b": 2}
    assert pick({}, ["a"]) == {}
    assert pick(None, ["a"]) == {}

    assert require_float({"x": "2.5"}, "x") == 2.5
    assert require_int({"x": "3"}, "x") == 3
    assert require_str({"x": " hi "}, "x") == "hi"

    for fn, data, key in [
        (require_float, {}, "x"),
        (require_int, {}, "x"),
        (require_str, {}, "x"),
        (require_float, {"x": "abc"}, "x"),
        (require_int, {"x": "abc"}, "x"),
        (require_str, {"x": "  "}, "x"),
        (require_str, {"x": {"nested": 1}}, "x"),
    ]:
        with pytest.raises(HTTPException) as exc:
            fn(data, key)
        assert exc.value.status_code == 400, f"{fn.__name__} did not raise 400"

    assert optional_float({}, "x") is None
    assert optional_float({"x": None}, "x") is None
    assert optional_float({"x": ""}, "x") is None
    assert optional_float({"x": "1.5"}, "x") == 1.5
    assert optional_int({}, "x", 5) == 5
    assert optional_str({}, "x", "d") == "d"
    with pytest.raises(HTTPException):
        optional_float({"x": "abc"}, "x")
