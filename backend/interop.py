"""Read-first WITSML 1.4.1.1 and OSDU Wellbore DDMS adapters.

No credentials are stored in the database. Connection settings come from
environment variables so they can be supplied by the deployment secret store.
WITSML 1.4.1.1 uses SOAP; 2.1/ETP is intentionally not enabled in this increment.
"""

from __future__ import annotations

import base64
import datetime
import html
import json
import os
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

import numpy as np

try:
    from models import CurveData, LogRun, Project, Well
except ImportError:
    from backend.models import CurveData, LogRun, Project, Well

def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

def _text(parent: ET.Element, name: str) -> str:
    for child in parent.iter():
        if local(child.tag) == name and child.text:
            return child.text.strip()
    return ""

def _direct(parent: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in list(parent) if local(c.tag) == name]

def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def witsml_config() -> dict[str, Any]:
    url = (os.environ.get("GEOLOG_WITSML_URL") or "").strip()
    if not url:
        raise RuntimeError("GEOLOG_WITSML_URL is not configured")
    return {
        "url": url,
        "user": os.environ.get("GEOLOG_WITSML_USER", ""),
        "password": os.environ.get("GEOLOG_WITSML_PASSWORD", ""),
        "token": os.environ.get("GEOLOG_WITSML_TOKEN", ""),
        "timeout": float(os.environ.get("GEOLOG_WITSML_TIMEOUT", "30") or 30),
        "verify_tls": not _bool_env("GEOLOG_INTEROP_INSECURE_TLS", False),
    }

def osdu_config() -> dict[str, Any]:
    url = (os.environ.get("GEOLOG_OSDU_URL") or "").strip()
    if not url:
        raise RuntimeError("GEOLOG_OSDU_URL is not configured")
    return {
        "url": url.rstrip("/"),
        "token": os.environ.get("GEOLOG_OSDU_TOKEN", ""),
        "partition": os.environ.get("GEOLOG_OSDU_PARTITION", ""),
        "timeout": float(os.environ.get("GEOLOG_OSDU_TIMEOUT", "30") or 30),
        "verify_tls": not _bool_env("GEOLOG_INTEROP_INSECURE_TLS", False),
        "wellbores_path": os.environ.get("GEOLOG_OSDU_WELLBORES_PATH", "/api/wellbore/v1/wellbores"),
    }

def http_request(method: str, url: str, body: bytes | None, headers: dict[str, str],
                 timeout: float, verify_tls: bool = True) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    context = ssl.create_default_context()
    if not verify_tls:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()

def _witsml_headers(cfg: dict) -> dict[str, str]:
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    elif cfg["user"]:
        raw = f"{cfg['user']}:{cfg['password']}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()
    return headers

def witsml_soap(method: str, query: str = "", capabilities: str = "", cfg: dict | None = None) -> tuple[int, str]:
    cfg = cfg or witsml_config()
    body = f'''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
 <soap:Body>
  <WMLS_GetFromStore xmlns="http://www.witsml.org/wsdl/140">
   <WMLtypeIn>{html.escape(method)}</WMLtypeIn>
   <QueryIn>{html.escape(query)}</QueryIn>
   <OptionsIn>returnElements=all</OptionsIn>
   <CapabilitiesIn>{html.escape(capabilities)}</CapabilitiesIn>
  </WMLS_GetFromStore>
 </soap:Body>
</soap:Envelope>'''.encode("utf-8")
    status, raw = http_request("POST", cfg["url"], body, _witsml_headers(cfg), cfg["timeout"], cfg["verify_tls"])
    return status, raw.decode("utf-8", errors="replace")

def witsml_test(cfg: dict | None = None) -> dict:
    cfg = cfg or witsml_config()
    status, text = witsml_soap("well", "", "", cfg)
    return {"status": status, "ok": status == 200 and "<Result>1</Result>" in text,
            "response": text[:500]}

def witsml_query(kind: str, name: str = "", cfg: dict | None = None) -> str:
    cfg = cfg or witsml_config()
    selector = f'<name>{html.escape(name)}</name>' if name else ""
    if kind == "well":
        query = f'<wells xmlns="http://www.witsml.org/schemas/1series" version="1.4.1.1">{selector}</wells>'
    elif kind == "log":
        query = f'<logs xmlns="http://www.witsml.org/schemas/1series" version="1.4.1.1">{selector}</logs>'
    else:
        raise ValueError("kind must be well or log")
    status, text = witsml_soap(kind, query, "", cfg)
    if status != 200:
        raise RuntimeError(f"WITSML HTTP {status}: {text[:300]}")
    try:
        envelope = ET.fromstring(text)
    except ET.ParseError as exc:
        raise RuntimeError(f"invalid WITSML SOAP response: {exc}")
    xmlout = _text(envelope, "XMLout")
    if not xmlout:
        raise RuntimeError("WITSML response has no XMLout")
    result = _text(envelope, "Result")
    if result not in {"1", "2"}:
        raise RuntimeError(f"WITSML Result={result}: {_text(envelope, 'Message')}")
    return xmlout

def parse_witsml_wells(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for well in [e for e in root.iter() if local(e.tag) == "well"]:
        out.append({
            "name": _text(well, "name"),
            "uwi": _text(well, "uwi") or _text(well, "uid"),
            "operator": _text(well, "operator"),
            "field": _text(well, "field"),
            "country": _text(well, "country"),
            "latitude": _float(_text(well, "latitude")),
            "longitude": _float(_text(well, "longitude")),
            "total_depth": _float(_text(well, "totalDepth") or _text(well, "md")),
        })
    return [w for w in out if w["name"]]

def _float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def parse_witsml_logs(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    logs = []
    for log in [e for e in root.iter() if local(e.tag) == "log"]:
        curves = []
        for info in [e for e in log.iter() if local(e.tag) == "logCurveInfo"]:
            curves.append({
                "mnemonic": _text(info, "mnemonic"),
                "unit": _text(info, "unit"),
                "description": _text(info, "curveDescription") or _text(info, "mnemonic"),
            })
        data_el = next((e for e in log.iter() if local(e.tag) == "data"), None)
        rows = []
        if data_el is not None and data_el.text:
            for line in data_el.text.strip().splitlines():
                parts = [p for p in line.replace("\t", ",").replace(" ", ",").split(",") if p != ""]
                if len(parts) >= len(curves):
                    try:
                        rows.append([float(p) for p in parts[:len(curves)]])
                    except ValueError:
                        continue
        if not curves or not rows:
            continue
        logs.append({
            "name": _text(log, "name"),
            "well_name": _text(log, "wellName") or _text(log, "wellboreName"),
            "index": _text(log, "indexType"),
            "start": _float(_text(log, "startIndex")),
            "stop": _float(_text(log, "endIndex")),
            "curves": curves,
            "rows": rows,
        })
    return logs

def upsert_well(db, project_id: int, payload: dict, source: str) -> tuple[Well, bool]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("project not found")
    q = db.query(Well).filter(Well.project_id == project_id)
    well = None
    if payload.get("uwi"):
        well = q.filter(Well.uwi == payload["uwi"]).first()
    if well is None and payload.get("name"):
        well = q.filter(Well.name == payload["name"]).first()
    created = well is None
    if created:
        well = Well(project_id=project_id, name=payload.get("name") or "Untitled",
                    depth_unit="FT")
        db.add(well)
    well.name = payload.get("name") or well.name
    well.uwi = payload.get("uwi") or well.uwi or ""
    well.operator = payload.get("operator") or well.operator or ""
    well.field_name = payload.get("field") or well.field_name or ""
    if payload.get("latitude") is not None:
        well.latitude = payload["latitude"]
    if payload.get("longitude") is not None:
        well.longitude = payload["longitude"]
    if payload.get("total_depth") is not None:
        well.total_depth = payload["total_depth"]
    well.updated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    db.flush()
    return well, created

def import_witsml_logs(db, well: Well, logs: list[dict], import_curves: bool = True) -> list[dict]:
    report = []
    existing = {r.filename for r in db.query(LogRun).filter(LogRun.well_id == well.id).all()}
    for log in logs:
        filename = f"witsml::{log['name'] or 'log'}"
        if filename in existing:
            report.append({"name": log["name"], "status": "skipped_exists"})
            continue
        rows = np.asarray(log["rows"], dtype=np.float64)
        if rows.size == 0:
            continue
        curves = log["curves"]
        num = len(rows)
        run = LogRun(
            well_id=well.id, run_number=len(existing) + 1, filename=filename,
            las_version="witsml-1.4.1.1", start_depth=log.get("start") or float(rows[0, 0]),
            stop_depth=log.get("stop") or float(rows[-1, 0]),
            step=float(np.median(np.diff(rows[:, 0]))) if num > 1 else None,
            num_points=num, curves_json=json.dumps(curves),
        )
        db.add(run)
        db.flush()
        if import_curves:
            for i, curve in enumerate(curves):
                arr = rows[:, i]
                valid = arr[np.isfinite(arr)]
                db.add(CurveData(
                    log_run_id=run.id, mnemonic=curve["mnemonic"], unit=curve["unit"],
                    description=curve["description"], num_points=num,
                    min_value=float(np.min(valid)) if len(valid) else None,
                    max_value=float(np.max(valid)) if len(valid) else None,
                    data_binary=arr.tobytes(),
                ))
        existing.add(filename)
        report.append({"name": log["name"], "status": "imported", "log_run_id": run.id, "points": num})
    return report

def _osdu_headers(cfg: dict) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    if cfg["partition"]:
        headers["data-partition-id"] = cfg["partition"]
    return headers

def osdu_request(cfg: dict, method: str, path: str, body: bytes | None = None) -> tuple[int, Any]:
    status, raw = http_request(method, cfg["url"] + path, body, _osdu_headers(cfg),
                               cfg["timeout"], cfg["verify_tls"])
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        payload = {"raw": raw[:500].decode("utf-8", errors="replace")}
    return status, payload

def osdu_test(cfg: dict | None = None) -> dict:
    cfg = cfg or osdu_config()
    status, body = osdu_request(cfg, "GET", f"{cfg['wellbores_path']}?limit=1")
    return {"status": status, "ok": 200 <= status < 300, "sample": body}

def osdu_well_payload(record: dict) -> dict:
    data = record.get("data", record)
    return {
        "name": data.get("WellName") or data.get("WellboreName") or data.get("name") or "",
        "uwi": data.get("UWI") or data.get("WellboreID") or data.get("id") or "",
        "operator": data.get("Operator") or "",
        "field": data.get("Field") or "",
        "latitude": data.get("Latitude"),
        "longitude": data.get("Longitude"),
        "total_depth": data.get("TotalDepth") or data.get("TotalMD"),
    }

def osdu_pull_wells(db, project_id: int, limit: int = 100, cfg: dict | None = None) -> dict:
    cfg = cfg or osdu_config()
    status, body = osdu_request(cfg, "GET", f"{cfg['wellbores_path']}?limit={max(1, min(limit, 1000))}")
    if not (200 <= status < 300):
        raise RuntimeError(f"OSDU HTTP {status}: {str(body)[:300]}")
    records = body.get("results") or body.get("wellbores") or []
    created = updated = skipped = 0
    for record in records:
        payload = osdu_well_payload(record)
        if not payload["name"]:
            skipped += 1
            continue
        well, is_new = upsert_well(db, project_id, payload, "osdu")
        created += int(is_new)
        updated += int(not is_new)
    db.commit()
    return {"status": status, "records": len(records), "created": created,
            "updated": updated, "skipped": skipped}

def osdu_push_well(db, well: Well, cfg: dict | None = None) -> dict:
    cfg = cfg or osdu_config()
    payload = {
        "kind": "osdu:wks:master-data--Wellbore:1.0.0",
        "data": {
            "WellName": well.name,
            "UWI": well.uwi or "",
            "Operator": well.operator or "",
            "Field": well.field_name or "",
            "Latitude": well.latitude,
            "Longitude": well.longitude,
            "TotalDepth": well.total_depth,
        },
    }
    status, body = osdu_request(cfg, "POST", cfg["wellbores_path"], json.dumps(payload).encode())
    return {"status": status, "ok": 200 <= status < 300, "response": body}
