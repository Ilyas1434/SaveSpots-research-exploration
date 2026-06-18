#!/usr/bin/env bash
# SaveSpots — full rebuild from scratch (documents the whole pipeline order).
# For routine updates use scripts/refresh.sh; this is the from-zero build.
set -euo pipefail
cd "$(dirname "$0")/.."

# Full pipeline = daily refresh but also rebuild the naloxone supply layer.
bash scripts/refresh.sh --naloxone

cat <<'NOTE'

──────────────────────────────────────────────────────────────────────
Optional (not in the live pipeline — costs Google imagery, runs on the
Claude Code plan for scoring):
  export GOOGLE_MAPS_API_KEY=...
  python3 scripts/streetview_fetch.py        # download imagery for top candidates
  # then ask Claude Code: "score the street view images"  -> batch_gap_analysis.json
──────────────────────────────────────────────────────────────────────
Serve:  bash scripts/serve.sh   →   http://localhost:8000/map/
NOTE
