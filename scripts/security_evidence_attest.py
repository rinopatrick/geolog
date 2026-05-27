#!/usr/bin/env python3
"""Attest backup drill evidence against GeoLog API contract.

Usage:
  python scripts/security_evidence_attest.py \
    --base-url http://127.0.0.1:8000 \
    --artifact-dir artifacts/backup-drill
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request


def _read_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_evidence_paths(artifact_dir: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path] | None:
    report_path = artifact_dir / "report.json"
    sig_path = artifact_dir / "report.signature.json"
    if report_path.exists() and sig_path.exists():
        return report_path, sig_path

    candidates = sorted(
        [p for p in artifact_dir.glob("*/report.json") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for rp in candidates:
        sp = rp.with_name("report.signature.json")
        if sp.exists():
            return rp, sp
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--artifact-dir", default="artifacts/backup-drill")
    args = p.parse_args()

    artifact_dir = pathlib.Path(args.artifact_dir)
    resolved = _resolve_evidence_paths(artifact_dir)
    if not resolved:
        print("missing evidence files", file=sys.stderr)
        return 2
    report_path, sig_path = resolved

    payload = {
        "report": _read_json(report_path),
        "signature": _read_json(sig_path),
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        args.base_url.rstrip("/") + "/api/ops/security-evidence/attest",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-User-Role": "interpreter",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        print(f"attest call failed: HTTP {e.code} {msg}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"attest call failed: {e}", file=sys.stderr)
        return 4

    print(json.dumps(data, ensure_ascii=False))
    return 0 if bool(data.get("ok")) else 5


if __name__ == "__main__":
    raise SystemExit(main())
