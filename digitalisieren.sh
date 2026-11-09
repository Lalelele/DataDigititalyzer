#!/usr/bin/env bash
# Ohne Argument: App im Browser starten.   Mit Datei: ./digitalisieren.sh scan.pdf
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m digitalyzer "$@"
