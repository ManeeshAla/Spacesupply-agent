#!/usr/bin/env bash
# One-command start: backend (serves the built dashboard if present)
set -e
cd "$(dirname "$0")/backend"
[ -d ../.venv ] || { python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt; }
if [ -d ../frontend ] && [ ! -d ../frontend/dist ]; then (cd ../frontend && npm install && npm run build); fi
exec ../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
