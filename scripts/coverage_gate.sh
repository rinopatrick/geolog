#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python}"

"${PYTHON}" -m coverage erase
"${PYTHON}" -m coverage run --source=backend -m pytest tests/ -q
"${PYTHON}" -m coverage report --fail-under=68
"${PYTHON}" -m coverage report \
  --include='backend/security.py,backend/routers/reports.py,backend/routers/correlation.py,backend/routers/zonation.py' \
  --fail-under=75
# The largest router is the slowest to cover; keep the floor moving up rather
# than letting it regress while the module is being split.
"${PYTHON}" -m coverage report \
  --include='backend/routers/wells.py' \
  --fail-under=45
