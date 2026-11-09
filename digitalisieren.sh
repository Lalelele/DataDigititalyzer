#!/usr/bin/env bash
# Aufruf: ./digitalisieren.sh scan.pdf   - wertet aus und oeffnet die Pruef-App
set -euo pipefail
cd "$(dirname "$0")"
if [ $# -lt 1 ]; then echo "Aufruf: $0 scan.pdf"; exit 1; fi
exec python3 -m digitalyzer "$@"
