"""Physical plausibility checks for stored curves.

Why this exists: LAS parsing was once positional-unsafe, so two vendor mnemonics
that mapped to the same canonical name caused every later curve to read its
neighbour's column. The resulting numbers are physically impossible for their
mnemonic (a GR of 0.068 GAPI, a sonic of 2.9 us/ft) but nothing complained.

The raw uploaded file is not retained, so affected wells cannot be re-parsed and
must be re-uploaded. These checks identify which ones, from what is stored.

Two confidence levels, deliberately kept apart:

- ``corrupt``    the stored range cannot belong to that mnemonic at all.
- ``suspicious`` a cross-curve relationship looks wrong. Heuristic, and
                 reservoir-dependent; needs a human look.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

# For each canonical mnemonic, the range the curve should reach into over a
# logged interval. A curve that never gets above `lo` or never drops below `hi`
# is not that curve. Bounds are deliberately wide — this is meant to catch
# values from a different physical quantity, not to second-guess geology.
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "GR": (10.0, 500.0),        # GAPI; any real GR exceeds ~10 somewhere
    "SGR": (10.0, 500.0),
    "CGR": (10.0, 500.0),
    "CAL": (4.0, 30.0),         # inches
    "BS": (4.0, 30.0),
    "RHOB": (1.6, 3.2),         # g/cc; coal ~1.2, heavies ~3.0
    "RHOZ": (1.6, 3.2),
    "NPHI": (0.05, 0.90),       # v/v, after percent normalisation
    "DPOR": (-0.15, 0.80),
    "SPOR": (-0.15, 0.80),
    "DT": (40.0, 220.0),        # us/ft
    "DTC": (40.0, 220.0),
    "DTS": (50.0, 400.0),
    "PE": (0.5, 20.0),          # barns/electron
    "PEF": (0.5, 20.0),
    "DRHO": (-0.5, 0.5),        # g/cc
    "DGA": (1.0, 4.0),
    "RT": (0.05, 50000.0),      # ohm-m
    "RILD": (0.05, 50000.0),
    "RILM": (0.05, 50000.0),
    "RXO": (0.05, 50000.0),
    "RLL3": (0.05, 50000.0),
    "RLLS": (0.05, 50000.0),
    "MSFL": (0.05, 50000.0),
    "PHIE": (0.0, 0.60),
    "PHIT": (0.0, 0.80),
    "SW": (0.0, 1.05),
    "VSH": (0.0, 1.05),
    "K": (0.0, 100000.0),
}

# Very short curves (sparse sampling, test stubs) are not worth judging.
MIN_POINTS_FOR_CHECK = 50

# Resistivity curves, ordered deepest to shallowest. In an invaded zone the
# expected relationship is deep >= medium >= shallow; a swap is a strong hint
# that two columns were exchanged.
RESISTIVITY_DEPTH_ORDER = ("RILD", "RILM", "RXO")
ORDERING_TOLERANCE = 1.25  # allow this much inversion before flagging


@dataclass
class Finding:
    mnemonic: str
    severity: str  # "corrupt" | "suspicious"
    detail: str

    def as_dict(self) -> dict:
        return {"mnemonic": self.mnemonic, "severity": self.severity, "detail": self.detail}


def check_curve(
    mnemonic: str,
    num_points: Optional[int],
    min_value: Optional[float],
    max_value: Optional[float],
) -> Optional[Finding]:
    """Return a 'corrupt' finding if the stored range cannot be this mnemonic."""
    if mnemonic not in PLAUSIBLE_RANGES:
        return None
    if min_value is None or max_value is None:
        return None
    if (num_points or 0) < MIN_POINTS_FOR_CHECK:
        return None
    # An all-null curve carries no information and is not evidence of anything.
    if min_value == max_value:
        return None

    lo, hi = PLAUSIBLE_RANGES[mnemonic]
    if max_value < lo:
        return Finding(
            mnemonic, "corrupt",
            f"max {max_value:g} is below the plausible floor {lo:g}; "
            f"values look like a different quantity",
        )
    if min_value > hi:
        return Finding(
            mnemonic, "corrupt",
            f"min {min_value:g} is above the plausible ceiling {hi:g}; "
            f"values look like a different quantity",
        )
    return None


def check_resistivity_ordering(ranges: dict[str, tuple[float, float]]) -> list[Finding]:
    """Flag resistivities whose relative magnitudes look swapped.

    Advisory only: uses curve maxima as a proxy, and invasion is not always
    present. Reported as 'suspicious' so a human decides.
    """
    findings: list[Finding] = []
    for deeper, shallower in zip(RESISTIVITY_DEPTH_ORDER, RESISTIVITY_DEPTH_ORDER[1:]):
        if deeper not in ranges or shallower not in ranges:
            continue
        deep_max = ranges[deeper][1]
        shallow_max = ranges[shallower][1]
        if deep_max <= 0 or shallow_max <= 0:
            continue
        if shallow_max > deep_max * ORDERING_TOLERANCE:
            findings.append(Finding(
                shallower, "suspicious",
                f"{shallower} max {shallow_max:g} exceeds {deeper} max {deep_max:g}; "
                f"expected {deeper} >= {shallower} — possible column swap",
            ))
    return findings


def audit_curves(curves: Iterable[dict]) -> list[Finding]:
    """Audit one log run.

    `curves` yields dicts with mnemonic / num_points / min_value / max_value.
    """
    curves = list(curves)
    findings: list[Finding] = []
    ranges: dict[str, tuple[float, float]] = {}

    for c in curves:
        mnemonic = c.get("mnemonic") or ""
        finding = check_curve(
            mnemonic,
            c.get("num_points"),
            c.get("min_value"),
            c.get("max_value"),
        )
        if finding:
            findings.append(finding)
        if c.get("min_value") is not None and c.get("max_value") is not None:
            ranges[mnemonic] = (c["min_value"], c["max_value"])

    findings.extend(check_resistivity_ordering(ranges))
    return findings
