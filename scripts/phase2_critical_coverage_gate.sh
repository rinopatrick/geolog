#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python -m coverage erase
python -m coverage run -m pytest tests/test_rbac_roles.py -q
python -m coverage report -m \
  --include='backend/security.py,backend/routers/reports.py' \
  --fail-under=80
