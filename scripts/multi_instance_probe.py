#!/usr/bin/env python3
"""Probe two GeoLog instances backed by one PostgreSQL database.

This is intentionally an end-to-end check, not a unit test: it logs in through
the public API, creates ACL state on instance A, verifies it on instance B,
shares a login lockout, submits a job on A and polls it on B, and proves the
well lock/snapshot state crosses instances.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import time
from typing import Any

import jwt
import requests

DEFAULT_SECRET = "multi-instance-secret-0123456789"


def token(subject: str, role: str, secret: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {
            "sub": subject,
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        },
        secret,
        algorithm="HS256",
    )


def wait_ready(base: str, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            r = requests.get(base + "/api/health", timeout=3)
            if r.status_code == 200:
                return
            last = r.text
        except Exception as exc:  # noqa: BLE001 - diagnostic value
            last = str(exc)
        time.sleep(1)
    raise RuntimeError(f"{base} did not become ready: {last}")


class Probe:
    def __init__(self, a: str, b: str, secret: str):
        self.a = a.rstrip("/")
        self.b = b.rstrip("/")
        self.secret = secret
        self.checks: list[str] = []

    def h(self, role: str, subject: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token(subject, role, self.secret)}"}

    def call(
        self,
        method: str,
        base: str,
        path: str,
        headers: dict[str, str] | None = None,
        expected: int | tuple[int, ...] = 200,
        **kwargs: Any,
    ) -> requests.Response:
        r = requests.request(method, base + path, headers=headers, timeout=30, **kwargs)
        allowed = (expected,) if isinstance(expected, int) else expected
        if r.status_code not in allowed:
            raise AssertionError(f"{method} {base}{path} -> {r.status_code}: {r.text[:500]}")
        return r

    def run(self) -> dict[str, Any]:
        wait_ready(self.a)
        wait_ready(self.b)

        admin = self.h("admin", "ci-admin")
        alice = self.h("viewer", "alice")
        bob = self.h("interpreter", "bob")

        # ACL state created on A must be visible on B.
        project = self.call("POST", self.a, "/api/projects/", admin, 201, json={"name": "multi-instance"}).json()
        pid = int(project["id"])
        self.call(
            "POST", self.a, f"/api/projects/{pid}/members", admin, 201,
            json={"subject": "alice", "role": "viewer"},
        )
        well = self.call(
            "POST", self.a, "/api/wells/", admin, 201,
            json={"project_id": pid, "name": "multi-instance-well"},
        ).json()
        wid = int(well["id"])
        self.call(
            "POST", self.a, f"/api/wells/{wid}/members", admin, 201,
            json={"subject": "bob", "role": "interpreter"},
        )

        self.call("GET", self.b, f"/api/wells/{wid}", alice, 403)
        self.call("GET", self.a, f"/api/wells/{wid}", bob, 200)
        self.call("GET", self.b, f"/api/projects/{pid}/summary", alice, 200)
        self.call("GET", self.a, f"/api/projects/{pid}/summary", bob, 403)
        self.checks.append("acl_shared")

        # Snapshot created on A is visible and enforced on B.
        snap = self.call(
            "POST", self.a, f"/api/wells/{wid}/snapshots", admin, 201,
            json={"label": "multi-instance"},
        ).json()
        snap_id = str(snap["snapshot_id"])
        listed = self.call("GET", self.b, f"/api/wells/{wid}/snapshots", admin, 200).json()
        assert any(s.get("snapshot_id") == snap_id for s in listed["snapshots"]), listed
        self.call(
            "POST", self.a, f"/api/wells/{wid}/snapshots/{snap_id}/approve", admin, 200,
            json={"approved_by": "ci-admin"},
        )
        lock = self.call("GET", self.b, f"/api/wells/{wid}/lock-status", admin, 200).json()
        assert lock.get("locked") is True, lock
        self.call(
            "POST", self.b, f"/api/wells/{wid}/annotations", bob, 423,
            json={"depth": 1000.0, "text": "must be blocked"},
        )
        self.call("POST", self.b, f"/api/wells/{wid}/unlock", admin, 200)
        self.call(
            "POST", self.b, f"/api/wells/{wid}/annotations", bob, 201,
            json={"depth": 1000.0, "text": "after unlock"},
        )
        self.checks.append("snapshot_lock_shared")

        # A failed login on A must consume the shared account budget on B.
        username = f"multi-{int(time.time())}"
        created = self.call("POST", self.a, "/api/users", admin, 201, json={"username": username, "role": "viewer"}).json()
        password = str(created["token"])
        for index in range(4):
            self.call(
                "POST", self.a if index % 2 == 0 else self.b, "/api/users/token",
                expected=401, json={"username": username, "token": "wrong"},
            )
        self.call(
            "POST", self.b, "/api/users/token", expected=429,
            json={"username": username, "token": "wrong"},
        )
        self.call(
            "POST", self.a, "/api/users/token", expected=429,
            json={"username": username, "token": password},
        )
        self.checks.append("login_lockout_shared")

        # A job created on A is visible and pollable on B.
        projects = self.call("GET", self.a, "/api/projects/", admin, 200).json()
        seeded = next((p for p in projects if int(p.get("well_count") or 0) > 0), None)
        assert seeded, "no seeded project with wells"
        job = self.call(
            "POST", self.a, f"/api/projects/{seeded['id']}/batch-petro-async", admin, 202, json={},
        ).json()
        job_id = str(job["job_id"])
        job_seen = False
        status = "queued"
        deadline = time.time() + 90
        while time.time() < deadline:
            data = self.call("GET", self.b, f"/api/jobs/{job_id}", admin, 200).json()
            job_seen = data.get("id") == job_id
            status = str(data.get("status") or "")
            if status in {"done", "failed"}:
                break
            time.sleep(0.5)
        assert job_seen, f"job {job_id} was not visible on B"
        assert status in {"done", "failed"}, f"job stayed {status}"
        self.checks.append("job_shared")

        return {"ok": True, "checks": self.checks, "job_status": status}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-a", default=os.getenv("GEOLOG_INSTANCE_A", "http://127.0.0.1:8001"))
    parser.add_argument("--base-b", default=os.getenv("GEOLOG_INSTANCE_B", "http://127.0.0.1:8002"))
    parser.add_argument("--secret", default=os.getenv("AUTH_JWT_SECRET", DEFAULT_SECRET))
    args = parser.parse_args()
    try:
        result = Probe(args.base_a, args.base_b, args.secret).run()
    except Exception as exc:  # noqa: BLE001 - CI needs the diagnostic
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
