"""Saturation-height model fitting and evaluation.

Supported empirical models:
- J-function: Sw = a * J^b
- Brooks-Corey: Sw = (Pe / Pc)^lambda
- Lambda: Sw = (1 + Pc/Pe)^(-lambda)
- Thomeer: Sw = 1 - exp(-G * Pe / Pc)
- Skelt-Harrison: Sw = (1 + (Pc/Pe)^n)^(-1/n)
"""

from __future__ import annotations

import numpy as np

MODEL_TYPES = ("j_function", "brooks_corey", "lambda", "thomeer", "skelt_harrison")

_ALIASES = {
    "j": "j_function",
    "j-function": "j_function",
    "jfunction": "j_function",
    "brooks-corey": "brooks_corey",
    "brooks_corey": "brooks_corey",
    "bc": "brooks_corey",
    "thomeer": "thomeer",
    "lambda": "lambda",
    "skelt-harrison": "skelt_harrison",
    "skelt_harrison": "skelt_harrison",
    "skelt": "skelt_harrison",
}

def normalize_model_type(model_type: str) -> str:
    return normalize(model_type)

def normalize(model_type: str) -> str:
    key = (model_type or "j_function").strip().lower()
    return _ALIASES.get(key, key)

def _r2(observed: np.ndarray, predicted: np.ndarray) -> tuple[float, float]:
    residual = float(np.sum((observed - predicted) ** 2))
    total = float(np.sum((observed - np.mean(observed)) ** 2))
    return (1.0 - residual / total if total > 0 else 0.0), residual

def fit_model(model_type: str, pc: np.ndarray, sw: np.ndarray,
              j: np.ndarray | None = None) -> dict:
    kind = normalize(model_type)
    pc = np.asarray(pc, dtype=np.float64)
    sw = np.asarray(sw, dtype=np.float64)
    mask = np.isfinite(pc) & np.isfinite(sw) & (pc > 0) & (sw > 0) & (sw < 1)
    pc, sw = pc[mask], sw[mask]
    if len(pc) < 3:
        raise ValueError("not enough valid Pc/Sw points")
    if kind == "j_function":
        if j is None:
            raise ValueError("J values are required for j_function")
        j = np.asarray(j, dtype=np.float64)[mask]
        good = np.isfinite(j) & (j > 0)
        x, y = np.log10(j[good]), np.log10(sw[good])
        if len(x) < 3:
            raise ValueError("not enough valid J/Sw points")
        slope, intercept = np.polyfit(x, y, 1)
        if np.isfinite(slope) and abs(slope) > 1e-9:
            params = {"a": float(10 ** intercept), "b": float(slope)}
        else:
            params = {"a": 1.0, "b": 0.0}
        predicted = params["a"] * np.power(j[good], params["b"])
        r2, residual = _r2(sw[good], predicted)
        return {"model_type": kind, "parameters": params, "r2": float(r2),
                "residual": residual, "n": int(len(x))}

    if kind == "brooks_corey":
        x, y = np.log(sw), np.log(pc)
        slope, intercept = np.polyfit(x, y, 1)
        # Pc must fall as Sw rises, so the log-log slope is negative.
        # A non-negative slope means the data violate the model; fail loudly
        # instead of returning a clamped lambda with a garbage entry pressure.
        if slope >= 0:
            raise ValueError("brooks_corey needs monotonically decreasing Pc with Sw")
        lam = float(-1.0 / slope) if abs(slope) > 1e-12 else 1.0
        pe = float(np.exp(intercept))
        lam = max(lam, 1e-6)
        predicted = np.power(np.clip(pe / pc, 1e-12, None), lam)
        params = {"pe": pe, "lambda": lam}
    elif kind == "lambda":
        from scipy.optimize import curve_fit
        def f(p, pe, lam):
            return np.power(1.0 + np.clip(p, 1e-12, None) / max(pe, 1e-9), -max(lam, 1e-9))
        try:
            popt, _ = curve_fit(f, pc, sw, p0=[max(float(np.median(pc)), 1e-6), 1.0],
                                bounds=([1e-9, 1e-9], [np.inf, np.inf]), maxfev=20000)
        except Exception as exc:
            raise ValueError(f"lambda fit failed: {exc}")
        pe, lam = float(popt[0]), float(popt[1])
        predicted = f(pc, pe, lam)
        params = {"pe": pe, "lambda": lam}
    elif kind == "thomeer":
        from scipy.optimize import curve_fit
        def f(p, pe, g):
            return 1.0 - np.exp(-max(g, 1e-9) * max(pe, 1e-9) / np.clip(p, 1e-12, None))
        try:
            popt, _ = curve_fit(f, pc, sw, p0=[max(float(np.median(pc)), 1e-6), 1.0],
                                bounds=([1e-9, 1e-9], [np.inf, np.inf]), maxfev=20000)
        except Exception as exc:
            raise ValueError(f"thomeer fit failed: {exc}")
        pe, g = float(popt[0]), float(popt[1])
        predicted = f(pc, pe, g)
        params = {"pe": pe, "g": g}
    elif kind == "skelt_harrison":
        from scipy.optimize import curve_fit
        def f(p, pe, n):
            return np.power(1.0 + np.power(np.clip(p, 1e-12, None) / max(pe, 1e-9), max(n, 1e-9)),
                            -1.0 / max(n, 1e-9))
        try:
            popt, _ = curve_fit(f, pc, sw, p0=[max(float(np.median(pc)), 1e-6), 1.0],
                                bounds=([1e-9, 1e-9], [np.inf, np.inf]), maxfev=20000)
        except Exception as exc:
            raise ValueError(f"skelt_harrison fit failed: {exc}")
        pe, n = float(popt[0]), float(popt[1])
        predicted = f(pc, pe, n)
        params = {"pe": pe, "n": n}
    else:
        raise ValueError(f"unsupported saturation-height model: {model_type}")

    r2, residual = _r2(sw, predicted)
    return {"model_type": kind, "parameters": params, "r2": float(r2),
            "residual": residual, "n": int(len(pc))}

def apply_model(model_type: str, params: dict, pc: np.ndarray,
                j: np.ndarray | None = None) -> np.ndarray:
    kind = normalize(model_type)
    pc = np.clip(np.asarray(pc, dtype=np.float64), 1e-12, None)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        if kind == "j_function":
            if j is None:
                raise ValueError("J values are required for j_function")
            sw = float(params.get("a", 1.0)) * np.power(np.clip(j, 1e-12, None), float(params.get("b", 1.0)))
        elif kind == "brooks_corey":
            sw = np.power(params.get("pe", 1.0) / pc, float(params.get("lambda", 1.0)))
        elif kind == "lambda":
            sw = np.power(1.0 + pc / max(float(params.get("pe", 1.0)), 1e-9), -float(params.get("lambda", 1.0)))
        elif kind == "thomeer":
            sw = 1.0 - np.exp(-float(params.get("g", 1.0)) * float(params.get("pe", 1.0)) / pc)
        elif kind == "skelt_harrison":
            n = max(float(params.get("n", 1.0)), 1e-9)
            sw = np.power(1.0 + np.power(pc / max(float(params.get("pe", 1.0)), 1e-9), n), -1.0 / n)
        else:
            raise ValueError(f"unsupported saturation-height model: {model_type}")
    return np.clip(sw, 0.0, 1.0)
