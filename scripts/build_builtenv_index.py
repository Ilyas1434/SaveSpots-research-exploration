#!/usr/bin/env python3
"""
SaveSpots — Built-Environment Blight Index  (Phase B, LIVE city data, no Google)
================================================================================
Chicago publishes blight directly, geocoded + auto-updating. We build the
built-environment risk surface from city data instead of a one-time Street View scan.

Signals (literature: vacant/abandoned buildings + physical disorder predict overdose;
Oxford AJE 2024, NYC PMC 2022):
  - 311 Vacant & Abandoned Buildings (7nii-7srd)  -> point-level, the core blight signal
  - 311 Graffiti Removal (hec5-y4x5)              -> physical disorder, by community area

Outputs data/clean/builtenv_index.json:
  - grid       : ~440m cells with abandoned-building counts (the heat surface)
  - hotspots   : top blight cells (centroid + intensity + community area)
  - by_ca      : per-community-area blight score (for the placement model)

Run: python3 scripts/build_builtenv_index.py
"""
import json, os, time, urllib.parse, urllib.request
from collections import defaultdict

CHI = "https://data.cityofchicago.org/resource"
ACS = "https://data.cityofchicago.org/resource/kn9c-c2s2.json"
CLEAN = "data/clean"
CELL = 0.004  # ~440 m grid
os.makedirs(CLEAN, exist_ok=True)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SaveSpots/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def paged(dataset, select, where, page=50000):
    rows, off = [], 0
    while True:
        p = {"$select": select, "$where": where, "$limit": page, "$offset": off}
        batch = get(f"{CHI}/{dataset}.json?{urllib.parse.urlencode(p)}")
        rows.extend(batch)
        if len(batch) < page:
            break
        off += page
        time.sleep(0.2)
    return rows


def main():
    # community-area code -> NAME (to join with death/placement layers that use names)
    acs = get(f"{ACS}?$limit=200")
    num_to_name = {str(r["ca"]): r["community_area_name"].upper()
                   for r in acs if r.get("ca") and r.get("community_area_name")}

    print("[1] 311 Vacant & Abandoned Buildings (point-level) ...")
    ab = paged("7nii-7srd", "latitude,longitude,community_area",
               "latitude IS NOT NULL AND community_area IS NOT NULL")
    print(f"    {len(ab)} geocoded abandoned-building reports")

    print("[2] 311 Graffiti by community area (disorder) ...")
    gr_rows = get(f"{CHI}/hec5-y4x5.json?" + urllib.parse.urlencode(
        {"$select": "community_area, count(1)", "$group": "community_area",
         "$where": "community_area IS NOT NULL", "$limit": 200}))
    graffiti_by_ca = {num_to_name.get(str(r["community_area"]), str(r["community_area"])): int(r["count_1"])
                      for r in gr_rows if r.get("community_area")}

    # grid-bin abandoned buildings + per-CA counts
    grid = defaultdict(int)
    cell_ca = defaultdict(lambda: defaultdict(int))
    abandoned_by_ca = defaultdict(int)
    for r in ab:
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, ValueError):
            continue
        caname = num_to_name.get(str(r.get("community_area")), str(r.get("community_area")))
        key = (round(lat / CELL), round(lon / CELL))
        grid[key] += 1
        cell_ca[key][caname] += 1
        abandoned_by_ca[caname] += 1

    grid_list = [{"lat": gy * CELL, "lon": gx * CELL, "count": c} for (gy, gx), c in grid.items()]
    grid_list.sort(key=lambda d: -d["count"])

    # hotspots = densest cells, tagged with their dominant community area
    hotspots = []
    for (gy, gx), c in sorted(grid.items(), key=lambda kv: -kv[1])[:60]:
        dom = max(cell_ca[(gy, gx)].items(), key=lambda kv: kv[1])[0]
        hotspots.append({"lat": gy * CELL, "lon": gx * CELL, "intensity": c, "community_area": dom})

    # per-CA blight score: normalized abandoned (0.6) + normalized graffiti (0.4), 0-100
    max_ab = max(abandoned_by_ca.values()) if abandoned_by_ca else 1
    max_gr = max(graffiti_by_ca.values()) if graffiti_by_ca else 1
    cas = set(abandoned_by_ca) | set(graffiti_by_ca)
    by_ca = {}
    for ca in cas:
        ab_n = abandoned_by_ca.get(ca, 0) / max_ab
        gr_n = graffiti_by_ca.get(ca, 0) / max_gr
        # abandoned buildings dominate (literature-validated overdose predictor); graffiti is a
        # weak disorder co-signal AND partly reflects 311 reporting propensity, so down-weighted.
        by_ca[ca] = {
            "abandoned_buildings": abandoned_by_ca.get(ca, 0),
            "graffiti": graffiti_by_ca.get(ca, 0),
            "blight_score": round((ab_n * 0.8 + gr_n * 0.2) * 100, 1),
        }

    out = {
        "metadata": {"generated": time.strftime("%Y-%m-%d"),
                     "sources": ["311 Vacant & Abandoned Buildings (7nii-7srd)",
                                 "311 Graffiti Removal (hec5-y4x5)"],
                     "cell_size_deg": CELL, "abandoned_points": len(ab)},
        "grid": grid_list,
        "hotspots": hotspots,
        "by_ca": by_ca,
    }
    json.dump(out, open(f"{CLEAN}/builtenv_index.json", "w"))
    print(f"\n    wrote builtenv_index.json: {len(grid_list)} grid cells, {len(hotspots)} hotspots, "
          f"{len(by_ca)} community areas")
    print("    top blight community areas:")
    for ca, v in sorted(by_ca.items(), key=lambda kv: -kv[1]["blight_score"])[:6]:
        print(f"      {ca:<22} blight={v['blight_score']:<6} abandoned={v['abandoned_buildings']:<5} graffiti={v['graffiti']}")


if __name__ == "__main__":
    main()
