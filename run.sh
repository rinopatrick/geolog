#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 is not installed or not on PATH."
  exit 1
fi

PYTHON_VERSION="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit("❌ Python 3.9+ is required.")
PY

echo "✅ Using Python ${PYTHON_VERSION}"

if [[ ! -f requirements.txt ]]; then
  echo "❌ requirements.txt not found in ${ROOT_DIR}"
  exit 1
fi

echo "📦 Installing dependencies from requirements.txt..."
python3 -m pip install -r requirements.txt

echo "🚀 Starting GeoLog API"
echo "🌐 URL: http://localhost:8000"
echo "📘 Swagger UI: http://localhost:8000/docs"

exec python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
