#!/usr/bin/env bash
# Serve the prototype map locally (file:// fetch is blocked by browsers, so use a server).
# Usage: bash scripts/serve.sh   then open http://localhost:8000/map/
cd "$(dirname "$0")/.." || exit 1
echo "Serving SaveSpots prototype at http://localhost:8000/map/"
python3 -m http.server 8000
