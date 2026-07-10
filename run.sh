#!/usr/bin/env bash
# Sobe o servidor FlightZone Local.
# Uso:  ./run.sh        -> http://127.0.0.1:8080
set -e
cd "$(dirname "$0")"
exec ./.venv/bin/python -m app.main
