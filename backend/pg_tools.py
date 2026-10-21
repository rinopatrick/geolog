"""Copy/verify/rollback GeoLog data between databases.

The target must be empty. Copy creates the schema, inserts rows in FK order,
verifies row counts and content hashes, and deletes the copied rows if
verification fails. On PostgreSQL, identity sequences are advanced afterwards.

Usage:
  python -m backend.pg_tools copy --source sqlite:///backend/geolog.db \
      --target postgresql+psycopg://user:pass@host/geolog
  python -m backend.pg_tools verify --source ... --target ...
  python -m backend.pg_tools rollback --target ... --confirm
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import sys
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine

try:
    from models import Base
except ImportError:
    from backend.models import Base

def _engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(url)
    return create_engine(url, pool_pre_ping=True)

def _value(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__bytes__": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, (dt.datetime, dt.date)):
        return {"__date__": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    return value

def _raw_map(table, row) -> dict:
    return {c.name: row._mapping[c.name] for c in table.columns}

def _row_map(table, row) -> dict:
    return {c.name: _value(row._mapping[c.name]) for c in table.columns}

def _sort_key(table, row):
    cols = list(table.primary_key.columns) or list(table.columns)
    return tuple(str(row._mapping[c.name]) for c in cols)

def _digest(table, rows) -> str:
    h = hashlib.sha256()
    for row in sorted(rows, key=lambda r: _sort_key(table, r)):
        h.update(json.dumps(_row_map(table, row), sort_keys=True, separators=(",", ":"),
                            default=str).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()

def _count(engine: Engine, table) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar() or 0)

def _snapshot(engine: Engine) -> dict[str, dict]:
    out = {}
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            rows = conn.execute(select(table)).all()
            out[table.name] = {"count": len(rows), "hash": _digest(table, rows)}
    return out

def verify_database(source_url: str, target_url: str) -> dict:
    src, dst = _engine(source_url), _engine(target_url)
    with src.connect() as sc, dst.connect() as dc:
        report = {}
        for table in Base.metadata.sorted_tables:
            srows = sc.execute(select(table)).all()
            drows = dc.execute(select(table)).all()
            sh, dh = _digest(table, srows), _digest(table, drows)
            report[table.name] = {
                "source_count": len(srows), "target_count": len(drows),
                "source_hash": sh, "target_hash": dh,
                "ok": len(srows) == len(drows) and sh == dh,
            }
    return {"ok": all(v["ok"] for v in report.values()), "tables": report}

def _delete_all(engine: Engine) -> None:
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())

def _advance_sequences(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if "id" not in table.c:
                continue
            seq = conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table.name}).scalar()
            if seq:
                conn.execute(text(
                    f'SELECT setval(:seq, COALESCE((SELECT MAX(id) FROM "{table.name}"), 1), '
                    f'(SELECT MAX(id) FROM "{table.name}") IS NOT NULL)'
                ), {"seq": seq})

def copy_database(source_url: str, target_url: str, batch_size: int = 1000) -> dict:
    if source_url == target_url:
        raise ValueError("source and target must differ")
    src, dst = _engine(source_url), _engine(target_url)
    existing = set(inspect(dst).get_table_names())
    if existing:
        nonempty = [t.name for t in Base.metadata.sorted_tables
                    if t.name in existing and _count(dst, t) > 0]
        if nonempty:
            raise RuntimeError(f"target is not empty: {', '.join(nonempty[:5])}")
    Base.metadata.create_all(dst)
    copied = []
    try:
        with src.connect() as sc, dst.begin() as dc:
            for table in Base.metadata.sorted_tables:
                rows = sc.execute(select(table)).all()
                if rows:
                    batch = [_raw_map(table, r) for r in rows]
                    for i in range(0, len(batch), max(1, batch_size)):
                        dc.execute(table.insert(), batch[i:i + batch_size])
                copied.append((table, len(rows)))
        _advance_sequences(dst)
        report = verify_database(source_url, target_url)
        if not report["ok"]:
            _delete_all(dst)
            raise RuntimeError("verification failed; copied rows removed")
        report["copied"] = {t.name: n for t, n in copied}
        return report
    except Exception:
        _delete_all(dst)
        raise

def rollback(target_url: str, confirm: bool = False) -> dict:
    if not confirm:
        raise RuntimeError("rollback deletes every row in the target; pass --confirm")
    eng = _engine(target_url)
    _delete_all(eng)
    return {"ok": True, "action": "deleted all rows", "dialect": eng.dialect.name}

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="GeoLog database copy/verify/rollback")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("copy", "verify"):
        q = sub.add_parser(name)
        q.add_argument("--source", required=True)
        q.add_argument("--target", required=True)
        if name == "copy":
            q.add_argument("--batch-size", type=int, default=1000)
    r = sub.add_parser("rollback")
    r.add_argument("--target", required=True)
    r.add_argument("--confirm", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.command == "copy":
            result = copy_database(args.source, args.target, args.batch_size)
        elif args.command == "verify":
            result = verify_database(args.source, args.target)
        else:
            result = rollback(args.target, args.confirm)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
