#!/usr/bin/env bash
# SaveSpots — daily live refresh (the "constant heatmap" engine)
# Re-pulls every LIVE source and regenerates all derived layers the map consumes,
# then stamps data/clean/last_updated.json. Safe to run on a daily cron.
#
# Naloxone supply (Census-geocoded scrape) changes slowly — only rebuilt with --naloxone
# or if the file is missing. Street View AI is optional/on-demand (not in this pipeline).
#
# Usage: bash scripts/refresh.sh [--naloxone]
set -euo pipefail
cd "$(dirname "$0")/.."

echo "▶ 1/6  Cook County ME deaths (live, daily)…"
python3 scripts/pull_opioid_data.py

if [[ "${1:-}" == "--naloxone" || ! -f data/clean/naloxone_locations.geojson ]]; then
  echo "▶ ·    Existing naloxone supply (geocode)…"
  python3 scripts/build_naloxone_data.py
else
  echo "▶ ·    Naloxone supply: reusing existing file (pass --naloxone to rebuild)"
fi

echo "▶ 2/6  Coverage gap by community area…"
python3 scripts/build_coverage_gap.py
echo "▶ 3/6  CDC context (VSRR lag + tract OD rate)…"
python3 scripts/build_cdc_context.py
echo "▶ 4/6  Supply / temporal / reachability…"
python3 scripts/analyze_supply_temporal.py
echo "▶ 5/6  Built-environment blight index…"
python3 scripts/build_builtenv_index.py
echo "▶ 6/6  Placement candidates (reach × need)…"
python3 scripts/build_placement_candidates.py

python3 - <<'PY'
import json, datetime
json.dump({"generated": datetime.datetime.now().isoformat(timespec="seconds")},
          open("data/clean/last_updated.json", "w"))
print("stamped data/clean/last_updated.json")
PY
echo "✓ refresh complete — reload http://localhost:8000/map/"
