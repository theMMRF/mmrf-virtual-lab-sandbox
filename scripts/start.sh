#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/fetch_sources.py
python3 synthetic/generate.py
docker compose build
docker compose up -d --wait --wait-timeout 180
python3 scripts/smoke.py
