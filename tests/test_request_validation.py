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


# ─── Fuzzing the write endpoints ────────────────────────────────
#
# Found by sending 13 malformed payloads to every write endpoint (1092 requests).
# Four endpoints raised 500 where a 4xx was correct; these are the cases.


def test_non_finite_float_is_422_not_500():
    """`Infinity` in a body must not blow up the error response.

    Python's json *parses* Infinity, so the value reaches FastAPI, which then
    rejects the body. Its default 422 handler echoes the offending input, and
    Starlette serialises responses with allow_nan=False — so building the 422
    raised "Out of range float values are not JSON compliant" and the client got
    a 500 instead. Every endpoint with a Pydantic body model was affected.
    """
    body = b'{"name": "ok", "depth": Infinity}'
    for path in (
        "/api/audit-log/verify/signature",
        "/api/ops/contracts/verify-signature",
        "/api/ops/security-evidence/attest",
        "/api/ops/security-evidence/manifest/verify-signature",
    ):
        response = client.post(
            path, content=body,
            headers={**INTERPRETER, "Content-Type": "application/json"},
        )
        assert response.status_code < 500, (
            f"POST {path} -> {response.status_code} {response.text[:200]}"
        )
        # And the response must itself be valid JSON.
        response.json()


def test_nan_and_infinity_in_nested_positions_are_handled():
    body = b'{"payload": {"a": [NaN, Infinity, -Infinity]}, "signature": "' + b"0" * 64 + b'"}'
    response = client.post(
        "/api/audit-log/verify/signature", content=body,
        headers={**INTERPRETER, "Content-Type": "application/json"},
    )
    assert response.status_code < 500, response.text[:200]
    response.json()


def test_partial_update_rejects_a_non_numeric_float_field():
    """PUT used a bare setattr loop, so a string reached the FLOAT column."""
    response = client.put(
        "/api/tops/1", json={"depth": "abc"}, headers=INTERPRETER,
    )
    assert response.status_code == 400, response.text[:200]
    assert "depth" in response.json()["detail"]


def test_partial_update_rejects_null_for_a_not_null_column():
    response = client.put(
        "/api/tops/1", json={"depth": None}, headers=INTERPRETER,
    )
    assert response.status_code == 400, response.text[:200]
    assert "depth" in response.json()["detail"]


def test_partial_update_rejects_null_name_on_a_well():
    response = client.put(
        "/api/wells/1", json={"name": None}, headers=INTERPRETER,
    )
    assert response.status_code == 400, response.text[:200]


def test_partial_update_allows_null_for_nullable_columns():
    """latitude/longitude/elevation/total_depth are nullable, so null is valid."""
    response = client.put(
        "/api/wells/1", json={"latitude": None, "longitude": None},
        headers=INTERPRETER,
    )
    assert response.status_code == 200, response.text[:200]


def test_partial_update_accepts_valid_values():
    response = client.put(
        "/api/wells/1", json={"name": "Renamed", "total_depth": 1234.5},
        headers=INTERPRETER,
    )
    assert response.status_code == 200, response.text[:200]
    assert response.json()["name"] == "Renamed"
    assert response.json()["total_depth"] == 1234.5


def test_empty_partial_update_is_a_no_op_not_an_error():
    response = client.put("/api/wells/1", json={}, headers=INTERPRETER)
    assert response.status_code == 200, response.text[:200]


def test_apply_template_with_a_non_string_name_is_400_not_500():
    """_find_template called .strip() on whatever the body supplied."""
    for bad in (12345, {"nested": 1}, [1, 2]):
        response = client.post(
            "/api/wells/1/apply-template", json={"name": bad}, headers=INTERPRETER,
        )
        assert response.status_code == 400, (
            f"apply-template with name={bad!r} -> {response.status_code} "
            f"{response.text[:150]}"
        )


def test_canonical_json_rejects_non_finite_values():
    from fastapi import HTTPException

    from backend.validation import canonical_json

    assert canonical_json({"a": 1, "b": "x"}) == '{"a":1,"b":"x"}'
    for bad in ({"x": float("inf")}, {"x": float("nan")}, {"x": float("-inf")}):
        with pytest.raises(HTTPException) as exc:
            canonical_json(bad)
        assert exc.value.status_code == 400


def test_pick_typed_only_returns_present_fields():
    from backend.validation import pick_typed

    assert pick_typed({"name": "a"}, strings=("name", "uwi")) == {"name": "a"}
    assert pick_typed({}, strings=("name",)) == {}
    assert pick_typed({"lat": None}, floats=("lat",), nullable=("lat",)) == {"lat": None}
    assert pick_typed({"lat": "1.5"}, floats=("lat",)) == {"lat": 1.5}
    assert pick_typed({"n": "3"}, ints=("n",)) == {"n": 3}


def test_pick_typed_rejects_bad_types():
    from fastapi import HTTPException

    from backend.validation import pick_typed

    with pytest.raises(HTTPException):
        pick_typed({"name": None}, strings=("name",))
    with pytest.raises(HTTPException):
        pick_typed({"d": "abc"}, floats=("d",))
    with pytest.raises(HTTPException):
        pick_typed({"n": "abc"}, ints=("n",))
    with pytest.raises(HTTPException):
        pick_typed({"name": {"nested": 1}}, strings=("name",))
