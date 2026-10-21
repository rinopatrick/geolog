"""Borehole-image helpers: PNG output, DLIS channel extraction, sinusoid dip fit."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Any

import numpy as np

def _normalize(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image, dtype=np.float64)
    arr = np.nan_to_num(arr, nan=np.nanmedian(arr) if np.any(np.isfinite(arr)) else 0.0)
    lo, hi = np.percentile(arr, [2, 98])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    return np.clip((arr - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)

def save_png_gray(image: np.ndarray, path: str | Path) -> tuple[int, int]:
    """Write an 8-bit grayscale PNG without adding an image dependency."""
    arr = _normalize(image)
    if arr.ndim != 2:
        raise ValueError("image must be 2D")
    height, width = arr.shape
    raw = b"".join(b"\x00" + arr[row].tobytes() for row in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(
            ">I", zlib.crc32(tag + payload) & 0xFFFFFFFF
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)
    return width, height

def png_size(data: bytes) -> tuple[int, int]:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    return 0, 0

def fit_dip(trace: Any, radius: float, azimuth_origin: float = 0.0) -> dict[str, Any]:
    """Fit depth = z0 + a*cos(theta) + b*sin(theta) to picked points.

    The sinusoid amplitude is ``radius * tan(dip)``. The maximum depth
    azimuth is the downdip direction.
    """
    arr = np.asarray(trace, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2 or len(arr) < 3:
        raise ValueError("trace must contain at least three [depth, azimuth] points")
    if not np.all(np.isfinite(arr)):
        raise ValueError("trace contains non-finite values")
    if radius <= 0:
        raise ValueError("borehole_radius must be positive")
    az = np.deg2rad(arr[:, 1] - azimuth_origin)
    z = arr[:, 0]
    if np.ptp(az) < np.deg2rad(20):
        raise ValueError("trace azimuth spread is too small to fit a dip")
    design = np.column_stack([np.ones(len(az)), np.cos(az), np.sin(az)])
    coef, *_ = np.linalg.lstsq(design, z, rcond=None)
    pred = design @ coef
    ss_res = float(np.sum((z - pred) ** 2))
    ss_tot = float(np.sum((z - np.mean(z)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    amplitude = float(np.hypot(coef[1], coef[2]))
    phase = float(np.degrees(np.arctan2(coef[2], coef[1])) % 360.0) + azimuth_origin
    dip = float(np.degrees(np.arctan(amplitude / radius)))
    if dip > 90.0:
        dip = 180.0 - dip
        phase = (phase + 180.0) % 360.0
    return {
        "depth": float(coef[0]),
        "dip_angle": round(dip, 3),
        "dip_azimuth": round(phase % 360.0, 3),
        "amplitude": round(amplitude, 5),
        "r2": round(max(0.0, min(1.0, r2)), 5),
        "points": int(len(arr)),
    }

def extract_dlis_image(path: str, channel_name: str, depth_channel: str = "DEPT") -> dict[str, Any]:
    """Extract the first frame containing a 2D image channel from a DLIS file.

    Vendor-specific conditioning is not performed; values are percentile-
    normalized for display only.
    """
    from dlisio import dlis

    for logical in dlis.load(path):
        for frame in logical.frames:
            try:
                curves = frame.curves()
            except Exception:
                continue
            names = curves.dtype.names or ()
            if channel_name not in names:
                continue
            data = np.asarray(curves[channel_name])
            if data.ndim == 1:
                data = data[:, None]
            elif data.ndim > 2:
                data = data.reshape(data.shape[0], -1)
            if data.shape[1] < 2 or data.shape[0] < 2:
                continue
            if depth_channel in names:
                depth = np.asarray(curves[depth_channel], dtype=np.float64)
            else:
                depth = np.arange(data.shape[0], dtype=np.float64)
            return {
                "depth": depth,
                "image": _normalize(data),
                "channel": channel_name,
                "width": int(data.shape[1]),
                "height": int(data.shape[0]),
                "frame": getattr(frame, "name", ""),
            }
    raise ValueError(f"image channel {channel_name!r} not found")
