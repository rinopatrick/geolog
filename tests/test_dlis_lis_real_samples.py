"""Opt-in checks against real DLIS/LIS files.

The sample files are third-party test data, so they are not committed. Point the
environment variables at local copies:

    GEOLOG_DLIS_SAMPLE=/path/file.dlis \
    GEOLOG_LIS_SAMPLE=/path/file.lis \
    pytest tests/test_dlis_lis_real_samples.py -q

dlisio's repository publishes samples under ``python/data``. LIS parsing with
dlisio 1.0.4 needs NumPy < 2 (the project pins 1.26.4); the LIS test skips on
NumPy 2 because of that upstream issue.
"""

from __future__ import annotations

import os
import pathlib

import numpy as np
import pytest

from backend.dlis_lis_parser import parse_dlis_content, parse_lis_content, dlis_mod, lis_mod

DLIS_SAMPLE = os.getenv("GEOLOG_DLIS_SAMPLE", "")
LIS_SAMPLE = os.getenv("GEOLOG_LIS_SAMPLE", "")

@pytest.mark.skipif(dlis_mod is None, reason="dlisio is not installed")
@pytest.mark.skipif(not DLIS_SAMPLE or not pathlib.Path(DLIS_SAMPLE).is_file(), reason="GEOLOG_DLIS_SAMPLE is not set")
def test_real_dlis_file_uses_dlisio():
    parsed = parse_dlis_content(pathlib.Path(DLIS_SAMPLE).read_bytes(), pathlib.Path(DLIS_SAMPLE).name)
    assert parsed.warnings == []
    assert parsed.runs
    run = parsed.runs[0]
    assert run.curves
    assert run.depth.size > 1
    assert len(run.curves) == len(run.data)

@pytest.mark.skipif(lis_mod is None, reason="dlisio is not installed")
@pytest.mark.skipif(not LIS_SAMPLE or not pathlib.Path(LIS_SAMPLE).is_file(), reason="GEOLOG_LIS_SAMPLE is not set")
@pytest.mark.skipif(int(np.__version__.split(".")[0]) >= 2, reason="dlisio 1.0.4 LIS curves() needs NumPy < 2")
def test_real_lis_file_uses_dlisio():
    parsed = parse_lis_content(pathlib.Path(LIS_SAMPLE).read_bytes(), pathlib.Path(LIS_SAMPLE).name)
    assert parsed.warnings == []
    assert parsed.runs
    run = parsed.runs[0]
    assert run.curves
    assert run.depth.size > 1
    assert len(run.curves) == len(run.data)
