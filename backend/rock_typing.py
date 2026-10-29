"""Core rock typing: Winland R35, RQI and FZI."""

from __future__ import annotations

import math

WINLAND_CLASSES = (
    ("macroport", 10.0, float("inf"), "#3fb950"),
    ("mesoport", 2.0, 10.0, "#58a6ff"),
    ("microport", 0.5, 2.0, "#d29922"),
    ("nanoport", 0.0, 0.5, "#f85149"),
)


def rqi(porosity: float, perm_md: float) -> float:
    """Reservoir Quality Index (µm)."""
    return 0.0314 * math.sqrt(perm_md / porosity)


def fzi(porosity: float, perm_md: float) -> float:
    """Flow Zone Indicator (µm)."""
    phi_z = porosity / (1.0 - porosity)
    return rqi(porosity, perm_md) / phi_z


def winland_r35(porosity: float, perm_md: float) -> float:
    """Winland R35 pore-throat radius in microns."""
    phi_pct = porosity * 100.0
    log_r35 = 0.732 + 0.588 * math.log10(perm_md) - 0.864 * math.log10(phi_pct)
    return 10.0 ** log_r35


def winland_class(r35: float) -> str:
    if r35 >= 10.0:
        return "macroport"
    if r35 >= 2.0:
        return "mesoport"
    if r35 >= 0.5:
        return "microport"
    return "nanoport"


def classify_plug(porosity, perm_md) -> dict | None:
    try:
        phi = float(porosity)
        perm = float(perm_md)
    except (TypeError, ValueError):
        return None
    if not (0.0 < phi < 1.0) or perm <= 0:
        return None
    return {
        "porosity": phi,
        "perm_md": perm,
        "rqi": rqi(phi, perm),
        "fzi": fzi(phi, perm),
        "r35": winland_r35(phi, perm),
        "winland_class": winland_class(winland_r35(phi, perm)),
    }


def class_color(name: str) -> str:
    for class_name, _, _, color in WINLAND_CLASSES:
        if class_name == name:
            return color
    return "#8b949e"
