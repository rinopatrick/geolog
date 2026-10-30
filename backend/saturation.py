"""Saturation equations shared by deterministic and Monte Carlo paths."""

from __future__ import annotations

import numpy as np


def saturation(
    model: str,
    rt,
    phi,
    vsh=0.0,
    a: float = 1.0,
    m: float = 2.0,
    n: float = 2.0,
    rw: float = 0.1,
    rsh: float = 4.0,
):
    """Return water saturation clipped to [0, 1].

    Archie:      Sw^n = a Rw / (phi^m Rt)
    Simandoux:   Sw^n = (a Rw / phi^m) (1/Rt - Vsh/Rsh)
    Indonesian:  Sw = [1 / (sqrt(Rt) (sqrt(phi^m/(a Rw)) + sqrt(Vsh/Rsh)))]^(2/n)
    """
    rt = np.asarray(rt, dtype=float)
    phi = np.maximum(np.asarray(phi, dtype=float), 1e-6)
    vsh = np.clip(np.asarray(vsh, dtype=float), 0.0, 1.0)
    rt_safe = np.maximum(rt, 1e-12)
    name = str(model or "archie").lower()
    if name == "simandoux":
        inner = (float(a) * float(rw) / np.power(phi, float(m))) * (
            1.0 / rt_safe - vsh / max(float(rsh), 1e-6)
        )
        sw = np.power(np.maximum(inner, 0.0), 1.0 / max(float(n), 1e-6))
    elif name == "indonesian":
        denominator = np.sqrt(np.power(phi, float(m)) / max(float(a) * float(rw), 1e-12)) + np.sqrt(
            vsh / max(float(rsh), 1e-6)
        )
        sw = np.power(
            1.0 / np.maximum(np.sqrt(rt_safe) * denominator, 1e-12),
            2.0 / max(float(n), 1e-6),
        )
    else:
        sw = np.power(
            np.maximum(float(a) * float(rw) / (np.power(phi, float(m)) * rt_safe), 0.0),
            1.0 / max(float(n), 1e-6),
        )
    sw = np.clip(sw, 0.0, 1.0)
    return float(sw) if sw.ndim == 0 else sw
