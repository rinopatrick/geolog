#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python}"

# The critical path is covered by the RBAC suite plus the zone/report paths.
"${PYTHON}" -m coverage erase
"${PYTHON}" -m coverage run -m pytest tests/test_rbac_roles.py tests/test_reports_zones.py -q
"${PYTHON}" -m coverage report -m \
  --include='backend/security.py,backend/routers/reports.py' \
  --fail-under=80
