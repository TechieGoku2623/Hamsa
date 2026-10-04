#!/usr/bin/env bash
# Run the Hamsa API (port 8000) and web app (port 5173) locally with a seeded demo shop.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export HAMSA_JWT_SECRET="${HAMSA_JWT_SECRET:-dev-secret-change-me}"
export HAMSA_DATABASE_URL="${HAMSA_DATABASE_URL:-sqlite+aiosqlite:///$ROOT/services/api/hamsa.db}"

cd "$ROOT/services/api"
[ -d .venv ] || { uv venv -q .venv && uv pip install -q --python .venv/bin/python -r requirements-dev.txt; }
.venv/bin/python -m hamsa.seed
.venv/bin/uvicorn hamsa.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

cd "$ROOT/apps/web"
[ -d node_modules ] || npm install
npm run dev
