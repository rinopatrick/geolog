"""Well interpretation state: locks, snapshots and template signatures.

These live on disk rather than in the database, and GEOLOG_ARTIFACT_DIR redirects
them so tests can point at a temporary directory instead of leaving a well locked
for the running app.

Separated from the router because RBACWriteGuardMiddleware in main.py reads the
well lock on every write, and from main.py because the /api/wells routes own the
rest of the lifecycle.
"""

from __future__ import annotations

import hashlib
import json
import os

from sqlalchemy.orm import Session

try:
    from filelock import interprocess_lock
except ImportError:
    from backend.filelock import interprocess_lock

try:
    from timeutils import utcnow
except ImportError:
    from backend.timeutils import utcnow

try:
    from models import (
        Annotation,
        CorrelationMarker,
        CorrelationProfile,
        CurveAlias,
        DeviationSurvey,
        LogRun,
        LogRunDepthShift,
        PetroParams,
        ProductionData,
    )
except ImportError:
    from backend.models import (
        Annotation,
        CorrelationMarker,
        CorrelationProfile,
        CurveAlias,
        DeviationSurvey,
        LogRun,
        LogRunDepthShift,
        PetroParams,
        ProductionData,
    )


# Snapshots and locks live on disk, not in the database.
ARTIFACT_DIR = os.environ.get("GEOLOG_ARTIFACT_DIR") or os.path.join(
    os.path.dirname(__file__), "artifacts"
)
SNAPSHOT_DIR = os.path.join(ARTIFACT_DIR, "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
LOCK_FILE = os.path.join(ARTIFACT_DIR, "locks.json")


def _db_enabled() -> bool:
    try:
        from state_backend import enabled
    except ImportError:
        from backend.state_backend import enabled
    return enabled()


def compute_template_signature(params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_template_lock() -> dict:
    return {
        "locked": False,
        "locked_by": None,
        "locked_at": None,
        "reason": None,
        "signature": None,
        "signed_template": None,
        "signed_params": None,
    }


def current_petro_params_payload(db: Session, wid: int) -> dict:
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    if not pp:
        return {
            "saturation_model": "archie",
            "a": 1.0,
            "m": 2.0,
            "n": 2.0,
            "rw": 0.1,
            "vsh_cutoff": 0.35,
            "phie_cutoff": 0.10,
            "sw_cutoff": 0.60,
            "template": "custom",
        }
    return {
        "saturation_model": pp.saturation_model,
        "a": float(pp.a),
        "m": float(pp.m),
        "n": float(pp.n),
        "rw": float(pp.rw),
        "vsh_cutoff": float(pp.vsh_cutoff),
        "phie_cutoff": float(pp.phie_cutoff),
        "sw_cutoff": float(pp.sw_cutoff),
        "template": pp.template,
    }


def load_locks() -> dict:
    if _db_enabled():
        try:
            from state_backend import load_well_state
        except ImportError:
            from backend.state_backend import load_well_state
        data = load_well_state("locks", {})
        return data if isinstance(data, dict) else {}
    if not os.path.exists(LOCK_FILE):
        return {}
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_locks(data: dict):
    if _db_enabled():
        try:
            from state_backend import save_well_state
        except ImportError:
            from backend.state_backend import save_well_state
        save_well_state("locks", data)
        return
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    tmp = LOCK_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, LOCK_FILE)


def get_well_lock(wid: int) -> dict:
    locks = load_locks()
    return locks.get(str(wid), {"locked": False})


def set_well_lock(wid: int, locked: bool, actor: str = "system", snapshot_id: str = None):
    if _db_enabled():
        try:
            from state_backend import mutate_well_state
        except ImportError:
            from backend.state_backend import mutate_well_state

        def _apply(locks):
            current = locks.get(str(wid), {}) if isinstance(locks.get(str(wid), {}), dict) else {}
            current.update({
                "locked": bool(locked),
                "actor": actor,
                "snapshot_id": snapshot_id,
                "updated_at": utcnow().isoformat() + "Z",
            })
            locks[str(wid)] = current

        mutate_well_state("locks", _apply, {})
        return

    with interprocess_lock(LOCK_FILE):
        locks = load_locks()
        current = locks.get(str(wid), {}) if isinstance(locks.get(str(wid), {}), dict) else {}
        current.update({
            "locked": bool(locked),
            "actor": actor,
            "snapshot_id": snapshot_id,
            "updated_at": utcnow().isoformat() + "Z",
        })
        locks[str(wid)] = current
        save_locks(locks)


def get_template_lock(wid: int) -> dict:
    locks = load_locks()
    entry = locks.get(str(wid), {}) if isinstance(locks.get(str(wid), {}), dict) else {}
    tpl = entry.get("template_lock") if isinstance(entry.get("template_lock"), dict) else {}
    out = default_template_lock()
    out.update(tpl)
    return out


def set_template_lock(wid: int, lock_payload: dict):
    if _db_enabled():
        try:
            from state_backend import mutate_well_state
        except ImportError:
            from backend.state_backend import mutate_well_state

        def _apply(locks):
            entry = locks.get(str(wid), {}) if isinstance(locks.get(str(wid), {}), dict) else {}
            entry["template_lock"] = lock_payload
            locks[str(wid)] = entry

        mutate_well_state("locks", _apply, {})
        return

    with interprocess_lock(LOCK_FILE):
        locks = load_locks()
        entry = locks.get(str(wid), {}) if isinstance(locks.get(str(wid), {}), dict) else {}
        entry["template_lock"] = lock_payload
        locks[str(wid)] = entry
        save_locks(locks)


def snapshot_path(wid: int) -> str:
    return os.path.join(SNAPSHOT_DIR, f"well_{wid}.json")

def snapshot_lock(wid: int):
    """Cross-process lock for a read-modify-write of one well's snapshots."""
    return interprocess_lock(os.path.join(SNAPSHOT_DIR, f"well_{wid}"), timeout=10.0)


def load_snapshots(wid: int):
    if _db_enabled():
        try:
            from state_backend import load_well_state
        except ImportError:
            from backend.state_backend import load_well_state
        data = load_well_state(f"snapshots:{wid}", [])
        return data if isinstance(data, list) else []
    p = snapshot_path(wid)
    if not os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # Corrupt/partial file fallback
        return []


def save_snapshots(wid: int, snapshots):
    if _db_enabled():
        try:
            from state_backend import save_well_state
        except ImportError:
            from backend.state_backend import save_well_state
        save_well_state(f"snapshots:{wid}", snapshots)
        return
    # Atomic write + datetime-safe serialization
    out = snapshot_path(wid)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, indent=2, default=str)
    os.replace(tmp, out)

def mutate_snapshots(wid: int, fn):
    """Read-modify-write one well's snapshot list under a cross-process lock."""
    if _db_enabled():
        try:
            from state_backend import mutate_well_state
        except ImportError:
            from backend.state_backend import mutate_well_state
        return mutate_well_state(f"snapshots:{wid}", fn, [])
    with snapshot_lock(wid):
        snapshots = load_snapshots(wid)
        result = fn(snapshots)
        save_snapshots(wid, snapshots)
        return result


def snapshot_template_signature(db: Session, wid: int):
    payload = current_petro_params_payload(db, wid)
    return payload, compute_template_signature(payload)


def delete_well_state(wid: int) -> None:
    """Remove the lock entry and snapshot file for a well."""
    if _db_enabled():
        try:
            from state_backend import delete_well_state as db_delete_well_state, mutate_well_state
        except ImportError:
            from backend.state_backend import delete_well_state as db_delete_well_state, mutate_well_state

        def _drop(locks):
            locks.pop(str(wid), None)

        mutate_well_state("locks", _drop, {})
        db_delete_well_state(f"snapshots:{wid}")
        return

    with interprocess_lock(LOCK_FILE):
        locks = load_locks()
        if str(wid) in locks:
            locks.pop(str(wid), None)
            save_locks(locks)
    try:
        os.remove(snapshot_path(wid))
    except FileNotFoundError:
        pass

def delete_well_data(db: Session, wid: int) -> None:
    """Remove child rows that are not covered by ORM cascades.

    Without this, deleting a well leaves annotations, production, deviation,
    aliases, petro params and correlation markers behind. SQLite can then reuse
    the freed well id, so the next well silently inherits the old data and the
    old lock/snapshot files. Audit rows are intentionally kept.
    """
    run_ids = [row[0] for row in db.query(LogRun.id).filter(LogRun.well_id == wid).all()]
    if run_ids:
        db.query(LogRunDepthShift).filter(
            LogRunDepthShift.log_run_id.in_(run_ids)
        ).delete(synchronize_session=False)
    db.query(Annotation).filter(Annotation.well_id == wid).delete(synchronize_session=False)
    db.query(ProductionData).filter(ProductionData.well_id == wid).delete(synchronize_session=False)
    db.query(DeviationSurvey).filter(DeviationSurvey.well_id == wid).delete(synchronize_session=False)
    db.query(CurveAlias).filter(CurveAlias.well_id == wid).delete(synchronize_session=False)
    db.query(PetroParams).filter(PetroParams.well_id == wid).delete(synchronize_session=False)
    db.query(CorrelationMarker).filter(
        (CorrelationMarker.well_a_id == wid) | (CorrelationMarker.well_b_id == wid)
    ).delete(synchronize_session=False)
    db.query(CorrelationProfile).filter(
        (CorrelationProfile.well_a_id == wid) | (CorrelationProfile.well_b_id == wid)
    ).delete(synchronize_session=False)
    delete_well_state(wid)

# Aliases matching the names main.py used before these moved, so no call site in
# main.py had to change.
_load_locks = load_locks
_save_locks = save_locks
_get_well_lock = get_well_lock
_set_well_lock = set_well_lock
_get_template_lock = get_template_lock
_set_template_lock = set_template_lock
_snapshot_path = snapshot_path
_load_snapshots = load_snapshots
_save_snapshots = save_snapshots
_snapshot_template_signature = snapshot_template_signature
_compute_template_signature = compute_template_signature
_default_template_lock = default_template_lock
_current_petro_params_payload = current_petro_params_payload
_delete_well_data = delete_well_data
_delete_well_state = delete_well_state
_snapshot_lock = snapshot_lock
_mutate_snapshots = mutate_snapshots
