#!/usr/bin/env bash
# Atalho para o monitor. Ex.:
#   ./monitor.sh --from GRU --to GIG --date 2026-07-23 --interval 30
cd "$(dirname "$0")"
exec ./.venv/bin/python monitor.py "$@"
