#!/usr/bin/env python3
"""
SaveSpots — Coverage Gap by community area  (pipeline dependency)
=================================================================
Regenerates data/clean/coverage_gap.json from the live-derived death + naloxone layers, so the
self-updating pipeline never serves a stale gap file.

For each Chicago community area:
  total       = all-time mapped opioid deaths
  recent      = deaths 2023-2025
  nax_nearby  = existing naloxone locations within 1.5 km of the area's death centroid
  gap_score   = recent / (nax_nearby + 1)     (higher = more deaths, less existing coverage)

Run: python3 scripts/build_coverage_gap.py
"""
import json, math, os
from collections import defaultdict

CLEAN = "data/clean"
RECENT_YEARS = {"2023", "2024", "2025"}
NAX_RADIUS_KM = 1.5


def dist_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def main():
    deaths = json.load(open(f"{CLEAN}/opioid_deaths_chicago.geojson"))["features"]
    nax = json.load(open(f"{CLEAN}/naloxone_locations.geojson"))["features"]
    nax_pts = [(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]) for f in nax]

    total = defaultdict(int); recent = defaultdict(int); pts = defaultdict(list)
    for f in deaths:
        ca = f["properties"].get("community_area")
        if not ca:
            continue
        lon, lat = f["geometry"]["coordinates"]
        total[ca] += 1
        pts[ca].append((lat, lon))
        if f["properties"].get("year") in RECENT_YEARS:
            recent[ca] += 1

    out = {}
    for ca, p in pts.items():
        clat = sum(x[0] for x in p) / len(p); clon = sum(x[1] for x in p) / len(p)
        nax_near = sum(1 for (la, lo) in nax_pts if dist_km(clat, clon, la, lo) <= NAX_RADIUS_KM)
        out[ca] = {"total": total[ca], "recent": recent[ca], "nax_nearby": nax_near,
                   "gap_score": round(recent[ca] / (nax_near + 1), 1),
                   "lat": round(clat, 5), "lon": round(clon, 5)}

    json.dump(out, open(f"{CLEAN}/coverage_gap.json", "w"))
    print(f"wrote coverage_gap.json ({len(out)} community areas)")
    for ca, v in sorted(out.items(), key=lambda kv: -kv[1]["gap_score"])[:6]:
        print(f"  {ca:<22} gap={v['gap_score']:<7} recent={v['recent']:<5} nax_nearby={v['nax_nearby']}")


if __name__ == "__main__":
    main()
