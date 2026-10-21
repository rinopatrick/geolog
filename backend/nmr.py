"""NMR T2 inversion and derived-curve calculations.

Vendor T2-bin curves can be interpreted directly. Raw CPMG echo trains are
inverted with regularized non-negative least squares (NNLS) on a log-spaced T2
grid; the inversion is deliberately a screening implementation, not a
vendor-grade fluid-typing package.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

import numpy as np

try:
    from scipy.optimize import nnls
except Exception:  # pragma: no cover - exercised only without SciPy
    nnls = None

NMR_ENGINE_VERSION = "nmr-v1"
DEFAULT_T2_MIN_MS = 0.3
DEFAULT_T2_MAX_MS = 3000.0
DEFAULT_T2_BINS = 24
DEFAULT_CUTOFF_MS = 33.0

def t2_grid(min_ms: float = DEFAULT_T2_MIN_MS, max_ms: float = DEFAULT_T2_MAX_MS, count: int = DEFAULT_T2_BINS) -> np.ndarray:
    count = max(4, min(int(count), 128))
    min_ms = max(0.01, float(min_ms))
    max_ms = max(min_ms * 1.01, float(max_ms))
    return np.logspace(np.log10(min_ms), np.log10(max_ms), count)

def build_kernel(te_ms: Iterable[float], t2_ms: np.ndarray) -> np.ndarray:
    te = np.asarray(list(te_ms), dtype=np.float64)
    t2 = np.asarray(t2_ms, dtype=np.float64)
    if te.ndim != 1 or t2.ndim != 1 or te.size == 0 or t2.size == 0:
        raise ValueError("te_ms and t2_ms must be non-empty 1-D arrays")
    if np.any(te <= 0) or np.any(t2 <= 0):
        raise ValueError("TE and T2 values must be positive")
    return np.exp(-te[:, None] / t2[None, :])

def _second_difference(n: int) -> np.ndarray:
    if n < 3:
        return np.zeros((0, n), dtype=np.float64)
    return np.diff(np.eye(n, dtype=np.float64), n=2, axis=0)

def regularized_invert(
    echoes: np.ndarray,
    te_ms: Iterable[float],
    t2_ms: np.ndarray,
    lambda_value: float = 0.1,
) -> np.ndarray:
    """Invert a 2-D echo matrix (n_depth, n_echoes) into T2 amplitudes."""
    if nnls is None:
        raise RuntimeError("SciPy is required for raw-echo NMR inversion")
    data = np.asarray(echoes, dtype=np.float64)
    if data.ndim != 2:
        raise ValueError("echoes must be a 2-D array")
    kernel = build_kernel(te_ms, t2_ms)
    if data.shape[1] != kernel.shape[0]:
        raise ValueError("echo count does not match TE count")
    lam = max(0.0, float(lambda_value))
    difference = _second_difference(kernel.shape[1])
    zeros = np.zeros(difference.shape[0], dtype=np.float64)
    stacked = np.vstack([kernel, lam * difference]) if difference.size else kernel
    out = np.zeros((data.shape[0], kernel.shape[1]), dtype=np.float64)
    for i, row in enumerate(data):
        if not np.all(np.isfinite(row)):
            row = np.nan_to_num(row, nan=0.0, posinf=0.0, neginf=0.0)
        rhs = np.concatenate([row, zeros]) if difference.size else row
        solution, _ = nnls(stacked, rhs, maxiter=500)
        out[i] = np.maximum(solution, 0.0)
    return out

def derived_curves(
    amplitudes: np.ndarray,
    t2_ms: np.ndarray,
    cutoff_ms: float = DEFAULT_CUTOFF_MS,
    sdr_a: float = 4.0,
    coates_c: float = 1e4,
) -> dict[str, np.ndarray]:
    """Return NMRP, BVI, FFI, T2GM, KSDR and KCOATES arrays."""
    amps = np.asarray(amplitudes, dtype=np.float64)
    bins = np.asarray(t2_ms, dtype=np.float64)
    total = amps.sum(axis=1)
    below = bins <= float(cutoff_ms)
    bvi = amps[:, below].sum(axis=1) if np.any(below) else np.zeros(len(amps))
    ffi = np.maximum(total - bvi, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_bins = np.log(np.maximum(bins, 1e-12))
        weighted = np.sum(amps * log_bins[None, :], axis=1)
        t2gm = np.where(total > 0, np.exp(weighted / np.maximum(total, 1e-12)), np.nan)
    ksdr = np.where(total > 0, sdr_a * (total ** 4) * (np.nan_to_num(t2gm) ** 2), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = ffi / np.maximum(bvi, 1e-12)
        kcoates = np.where(total > 0, coates_c * (total ** 4) * (ratio ** 2), np.nan)
    return {
        "NMRP": total,
        "BVI": bvi,
        "FFI": ffi,
        "T2GM": t2gm,
        "KSDR": ksdr,
        "KCOATES": kcoates,
    }

def params_hash(params: dict) -> str:
    raw = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _as_arrays(values: list) -> np.ndarray:
    arr = np.asarray([np.nan if v is None else v for v in values], dtype=np.float64)
    return arr

def read_curve_matrix(db, log_run, names: list[str], strict: bool = True):
    """Read named curves through the shared semantics layer."""
    try:
        from semantics import apply_run_semantics
    except ImportError:
        from backend.semantics import apply_run_semantics

    result = apply_run_semantics(db, log_run, list(names))
    arrays = []
    for name in names:
        values = result["curves"].get(name)
        if values is None:
            # The output may use a canonical alias; find it by raw name.
            match = next((a for a in result["metadata"]["aliases"] if a["raw"] == name), None)
            values = result["curves"].get(match["name"]) if match else None
        if values is None:
            raise ValueError(f"curve not found: {name}")
        arrays.append(_as_arrays(values))
    lengths = {len(a) for a in arrays}
    if strict and len(lengths) > 1:
        raise ValueError("requested curves have different lengths")
    n = min(lengths) if lengths else 0
    if n == 0:
        raise ValueError("curves are empty")
    depth = np.asarray(result["depth"], dtype=np.float64)[:n]
    matrix = np.column_stack([a[:n] for a in arrays])
    return depth, matrix, result

def read_echo_matrix(db, log_run, echo_mnemonics: list[str], te_ms: list[float]):
    depth, matrix, _ = read_curve_matrix(db, log_run, echo_mnemonics)
    te = [float(v) for v in te_ms]
    if len(te) != matrix.shape[1]:
        raise ValueError("te_ms must match the number of echo curves")
    return depth, matrix, te

def store_inversion(
    db,
    well_id: int,
    log_run_id: int,
    method: str,
    t2_ms: np.ndarray,
    amplitudes: np.ndarray,
    depth: np.ndarray,
    cutoff_ms: float,
    lambda_value: float,
    params: dict,
):
    try:
        from models import NmrDistribution, NmrInversion
    except ImportError:
        from backend.models import NmrDistribution, NmrInversion

    inv = NmrInversion(
        well_id=well_id,
        log_run_id=log_run_id,
        method=method,
        t2_bins_json=json.dumps([float(v) for v in t2_ms]),
        cutoff_ms=float(cutoff_ms),
        lambda_value=float(lambda_value),
        n_depth=int(amplitudes.shape[0]),
        n_bins=int(amplitudes.shape[1]),
        params_hash=params_hash(params),
        engine_version=NMR_ENGINE_VERSION,
    )
    db.add(inv)
    db.flush()
    db.add(NmrDistribution(
        inversion_id=inv.id,
        n_depth=int(amplitudes.shape[0]),
        n_bins=int(amplitudes.shape[1]),
        depth_binary=np.asarray(depth, dtype=np.float64).tobytes(),
        amplitudes=np.asarray(amplitudes, dtype=np.float32).tobytes(),
    ))
    db.commit()
    db.refresh(inv)
    return inv


def store_derived_curves(db, log_run_id: int, derived: dict[str, np.ndarray]) -> list[str]:
    """Persist derived scalars as normal curve rows so the viewer can load them."""
    try:
        from models import CurveData
    except ImportError:
        from backend.models import CurveData

    units = {"NMRP": "V/V", "BVI": "V/V", "FFI": "V/V", "T2GM": "MS", "KSDR": "MD", "KCOATES": "MD"}
    saved = []
    for name, values in derived.items():
        arr = np.asarray(values, dtype=np.float64)
        valid = arr[np.isfinite(arr)]
        existing = db.query(CurveData).filter(
            CurveData.log_run_id == log_run_id, CurveData.mnemonic == name
        ).first()
        if existing:
            existing.data_binary = arr.tobytes()
            existing.num_points = int(len(arr))
            existing.min_value = float(np.min(valid)) if valid.size else None
            existing.max_value = float(np.max(valid)) if valid.size else None
            existing.description = f"NMR derived {name}"
        else:
            db.add(CurveData(
                log_run_id=log_run_id,
                mnemonic=name,
                unit=units.get(name, ""),
                description=f"NMR derived {name}",
                num_points=int(len(arr)),
                min_value=float(np.min(valid)) if valid.size else None,
                max_value=float(np.max(valid)) if valid.size else None,
                data_binary=arr.tobytes(),
            ))
        saved.append(name)
    db.commit()
    return saved

def load_amplitudes(inversion) -> np.ndarray:
    if not inversion.distribution or not inversion.distribution.amplitudes:
        return np.zeros((0, 0), dtype=np.float32)
    return np.frombuffer(inversion.distribution.amplitudes, dtype=np.float32).reshape(
        inversion.distribution.n_depth, inversion.distribution.n_bins
    )

def load_depth(inversion) -> np.ndarray:
    if not inversion.distribution or not inversion.distribution.depth_binary:
        return np.zeros((0,), dtype=np.float64)
    return np.frombuffer(inversion.distribution.depth_binary, dtype=np.float64)

def summary(derived: dict[str, np.ndarray]) -> dict[str, Any]:
    out = {}
    for key, values in derived.items():
        valid = values[np.isfinite(values)]
        out[key] = {
            "mean": round(float(np.mean(valid)), 6) if valid.size else None,
            "min": round(float(np.min(valid)), 6) if valid.size else None,
            "max": round(float(np.max(valid)), 6) if valid.size else None,
            "count": int(valid.size),
        }
    return out
