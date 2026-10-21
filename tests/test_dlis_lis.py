"""Tests for DLIS and LIS parsers (both dlisio paths and fallback scanning)."""

from __future__ import annotations

import numpy as np
import pytest

from backend.dlis_lis_parser import (
    _canon,
    _choose_depth_key,
    _derive_step,
    _extract_ascii_tokens,
    _build_minimal_run_from_tokens,
    parse_dlis_content,
    parse_lis_content,
)


def test_canon_alias_mapping():
    assert _canon("DEPTH") == "DEPT"
    assert _canon("ILD") == "RILD"
    assert _canon("UNKNOWN_MNEM") == "UNKNOWN_MNEM"


def test_choose_depth_key():
    assert _choose_depth_key(["GR", "DEPTH", "RHOB"]) == "DEPTH"
    assert _choose_depth_key(["GR", "DEPT", "RHOB"]) == "DEPT"
    assert _choose_depth_key(["GR", "MD", "RHOB"]) == "MD"
    assert _choose_depth_key(["GR", "CALI"]) == "GR"
    assert _choose_depth_key([]) == "DEPT"


def test_derive_step():
    depth = np.array([100.0, 100.5, 101.0, 101.5])
    assert _derive_step(depth) == 0.5
    assert _derive_step(np.array([100.0])) == 0.0
    assert _derive_step(np.array([])) == 0.0


def test_extract_ascii_tokens():
    raw = b"HEADER\x00\x01\x02 100.5 45.2 2.65 \n 101.0 46.1 2.64"
    tokens = _extract_ascii_tokens(raw)
    assert len(tokens) == 6
    assert tokens[0] == 100.5
    assert tokens[1] == 45.2
    assert tokens[2] == 2.65


def test_build_minimal_run_from_tokens_insufficient():
    tokens = [1.0, 2.0, 3.0]
    with pytest.raises(ValueError, match="not extract enough numeric samples"):
        _build_minimal_run_from_tokens(tokens, "DLIS", "test.dlis")


def test_fallback_dlis_parsing_success():
    # Build at least 21 tokens so len >= 20 passes
    raw_tokens = []
    for i in range(10):
        depth = 1000.0 + i * 0.5
        c1 = 45.0 + i
        c2 = 2.5 + i * 0.01
        raw_tokens.extend([str(depth), str(c1), str(c2)])
    
    mock_bytes = ("SOME_BINARY_DLIS_HEADER " + " ".join(raw_tokens)).encode("latin1")
    parsed = parse_dlis_content(mock_bytes, "synthetic_fallback.dlis")

    assert parsed.source_format == "DLIS"
    assert parsed.well_name == "synthetic_fallback"
    assert len(parsed.runs) == 1
    run = parsed.runs[0]
    assert run.depth_key == "DEPT"
    assert len(run.curves) == 3
    assert "DEPT" in run.data
    assert "CURVE1" in run.data
    assert "CURVE2" in run.data
    assert len(run.depth) == 10
    assert run.start_depth == 1000.0
    assert run.stop_depth == 1004.5
    assert run.step == 0.5


def test_fallback_lis_parsing_success():
    raw_tokens = []
    for i in range(10):
        depth = 2000.0 + i * 1.0
        c1 = 80.0 + i
        c2 = 1.95 + i * 0.02
        raw_tokens.extend([str(depth), str(c1), str(c2)])
    
    mock_bytes = ("LIS_FORMAT_HEADER_DATA " + " ".join(raw_tokens)).encode("latin1")
    parsed = parse_lis_content(mock_bytes, "test_well.lis")

    assert parsed.source_format == "LIS"
    assert parsed.well_name == "test_well"
    assert len(parsed.runs) == 1
    run = parsed.runs[0]
    assert run.start_depth == 2000.0
    assert run.stop_depth == 2009.0
    assert run.step == 1.0

def test_lis_dlisio_wrapper_calls_methods(monkeypatch):
    """LIS header/data_format_specs are methods in dlisio 1.x, not properties."""
    import backend.dlis_lis_parser as parser

    class Meta:
        def __init__(self, mnemonic, units):
            self.mnemonic = mnemonic
            self.units = units

    class Header:
        file_name = "REAL.LIS"
        well_name = ""
        well_id = ""

    class Logical:
        def header(self):
            return Header()

        def data_format_specs(self):
            return [object()]

    class Physical:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __iter__(self):
            return iter([Logical()])

    class FakeLis:
        @staticmethod
        def load(path):
            return Physical()

        @staticmethod
        def curves(logical, spec, strict=False):
            return np.array(
                [(100.0, 50.0), (100.5, 51.0)],
                dtype=[("DEPT", "f4"), ("GR", "f4")],
            )

        @staticmethod
        def curves_metadata(spec, strict=False):
            return {"DEPT": Meta("DEPT", "M"), "GR": Meta("GR", "GAPI")}

    monkeypatch.setattr(parser, "lis_mod", FakeLis)
    parsed = parser._parse_lis_dlisio(b"fake", "real.lis")

    assert parsed.well_name == "REAL.LIS"
    assert len(parsed.runs) == 1
    run = parsed.runs[0]
    assert run.depth_key == "DEPT"
    assert run.curves[0].mnemonic == "DEPT"
    assert run.curves[0].unit == "M"
    assert np.allclose(run.depth, [100.0, 100.5])
    assert np.allclose(run.data["GR"], [50.0, 51.0])
