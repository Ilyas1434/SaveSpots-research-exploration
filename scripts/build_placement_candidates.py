#!/usr/bin/env python3
"""
SaveSpots — In-Business Placement Candidates  (Phase C: reach x need)
=====================================================================
Model = TAKE-HOME retail distribution: a person walks into a trusted everyday business in a
high-need neighborhood, grabs free naloxone + fentanyl test strips, and carries them away for a
future overdose (often at/near home, alone — see reachability.json). So we score storefronts by
DISTRIBUTION REACH x NEED, not by "box near where people died."

Grounded in prior art: geospatial clustering of overdose incidents to site naloxone
(Cambridge EMS study), transit-based placement beating blanket pharmacy placement (CMAJ 2025),
housing-instability/poverty as top risk.

  NEED  = local recent-death density (settled 2022-24, within 400m)
          x coverage discount (closer existing naloxone -> lower)
          x area context (blight + hardship lift)
  REACH = business-type foot-traffic weight x transit-adjacency bonus
  SCORE = NEED x REACH        (AI-Vision suitability applied if a site was scored)

Outputs ranked data/clean/placement_candidates.geojson (+ .csv), spatially deduped to one
storefront per ~120 m so we don't recommend five stores on the same corner.

Run: python3 scripts/build_placement_candidates.py
"""
import json, csv, math, os, time, urllib.parse, urllib.request
from collections import defaultdict

CLEAN = "data/clean"
BIZ = "https://data.cityofchicago.org/resource/r5kz-chrr.json"
ACS = "https://data.cityofchicago.org/resource/kn9c-c2s2.json"
CTA = "https://data.cityofchicago.org/resource/8pix-ypme.json"

TOP_GAP_AREAS = 15
DEATH_RADIUS_M = 400
SETTLED_YEARS = ("2022", "2023", "2024")     # lag-aware: drop undercounted 2025-26
COVERED_KM = 0.5
TRANSIT_KM = 0.4
DEDUPE_M = 120

# business type -> (matchers, reach weight). Higher reach = more at-risk people pass through.
TARGET_TYPES = {
    "Gas / filling station":   ([("filling station", "desc"), ("filling station", "act")], 1.0),
    "Corner store / food mart": ([("retail sales of perishable foods", "act"),
                                  ("retail food establishment", "desc")], 1.0),
    "Liquor / package goods":  ([("package goods", "desc")], 0.9),
    "Tobacco / vape":          ([("tobacco", "desc")], 0.7),
    "Barbershop / salon":      ([("hair services", "act"), ("barber", "act")], 0.6),
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SaveSpots/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def paged(base, where, select, page=10000):
    rows, off = [], 0
    while True:
        q = urllib.parse.urlencode({"$where": where, "$select": select, "$limit": page, "$offset": off})
        batch = get(f"{base}?{q}")
        rows.extend(batch)
        if len(batch) < page:
            break
        off += page
        time.sleep(0.2)
    return rows


def dist_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def classify(desc, act):
    d, a = (desc or "").lower(), (act or "").lower()
    for label, (rules, _) in TARGET_TYPES.items():
        for kw, field in rules:
            if (field == "desc" and kw in d) or (field == "act" and kw in a):
                return label
    return None


def load_json(path, default=None):
    try:
        return json.load(open(path))
    except Exception:
        return default


def main():
    # ---- context layers -------------------------------------------------------
    gap = load_json(f"{CLEAN}/coverage_gap.json", {})
    builtenv = load_json(f"{CLEAN}/builtenv_index.json", {}).get("by_ca", {})
    acs = get(f"{ACS}?$limit=200")
    name_to_num = {r["community_area_name"].upper(): str(r["ca"])
                   for r in acs if r.get("ca") and r.get("community_area_name")}
    hardship = {r["community_area_name"].upper(): float(r.get("hardship_index", 0) or 0) for r in acs}

    ranked = sorted(((ca, v) for ca, v in gap.items() if isinstance(v.get("gap_score"), (int, float))),
                    key=lambda kv: -kv[1]["gap_score"])[:TOP_GAP_AREAS]
    num_to_name = {name_to_num[ca.upper()]: ca for ca, _ in ranked if ca.upper() in name_to_num}
    print(f"[1] {len(num_to_name)} top-gap areas")

    # ---- target storefronts in those areas -----------------------------------
    ca_list = ",".join(f"'{n}'" for n in num_to_name)
    rows = paged(BIZ, f"license_status='AAI' AND latitude IS NOT NULL AND community_area in({ca_list})",
                 "doing_business_as_name,address,community_area,business_activity,license_description,latitude,longitude")
    seen, biz = set(), []
    for r in rows:
        label = classify(r.get("license_description"), r.get("business_activity"))
        if not label:
            continue
        key = (r.get("doing_business_as_name", "").strip().upper(), r.get("address", "").strip().upper())
        if key in seen:
            continue
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, ValueError):
            continue
        seen.add(key)
        biz.append({"name": r.get("doing_business_as_name", ""), "address": r.get("address", ""),
                    "ca_name": num_to_name.get(r.get("community_area"), r.get("community_area")),
                    "type": label, "lat": lat, "lon": lon})
    print(f"[2] {len(biz)} distinct target storefronts")

    # ---- deaths (settled window) + naloxone + transit ------------------------
    deaths = load_json(f"{CLEAN}/opioid_deaths_chicago.geojson", {"features": []})
    recent = [(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0])
              for f in deaths["features"] if f["properties"].get("year") in SETTLED_YEARS]
    nax = load_json(f"{CLEAN}/naloxone_locations.geojson", {"features": []})
    nax_pts = [(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]) for f in nax["features"]]
    stops = get(f"{CTA}?$select=location&$limit=500")
    stop_pts = [(float(s["location"]["latitude"]), float(s["location"]["longitude"]))
                for s in stops if s.get("location", {}).get("latitude")]
    print(f"[3] {len(recent)} settled-window deaths, {len(nax_pts)} naloxone, {len(stop_pts)} CTA stops")

    # AI-Vision suitability (only the on-demand scored sites; optional)
    ai = {}
    for r in load_json(f"{CLEAN}/streetview_analysis/batch_gap_analysis.json", []) or []:
        ai[(r.get("label") or "").split(" — ")[0].strip().upper()] = r

    CELL = 0.01
    grid = defaultdict(list)
    for la, lo in recent:
        grid[(round(la / CELL), round(lo / CELL))].append((la, lo))
    rad = DEATH_RADIUS_M / 1000.0

    def deaths_within(lat, lon):
        c = 0; gy, gx = round(lat / CELL), round(lon / CELL)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for la, lo in grid.get((gy + dy, gx + dx), ()):
                    if dist_km(lat, lon, la, lo) <= rad:
                        c += 1
        return c

    def nearest(pts, lat, lon):
        return min((dist_km(lat, lon, la, lo) for la, lo in pts), default=99.0)

    # ---- score ---------------------------------------------------------------
    print("[4] scoring ...")
    for b in biz:
        d = deaths_within(b["lat"], b["lon"])
        nk = nearest(nax_pts, b["lat"], b["lon"])
        sk = nearest(stop_pts, b["lat"], b["lon"])
        cov_mult = 1.0 if nk >= COVERED_KM else max(0.3, nk / COVERED_KM)
        blight = builtenv.get(b["ca_name"], {}).get("blight_score", 0) / 100.0
        hard = hardship.get(b["ca_name"], 0) / 100.0
        ca_need_mult = 1 + 0.5 * blight + 0.5 * hard
        need = d * cov_mult * ca_need_mult

        type_w = TARGET_TYPES[b["type"]][1]
        transit = sk <= TRANSIT_KM
        reach = type_w * (1 + (0.5 if transit else 0))

        suit = 1.0
        if b["name"].strip().upper() in ai:
            suit = 1.0  # hook: penalize unsuitable sites once scored at scale

        b.update({"recent_deaths_400m": d, "nearest_nax_km": round(nk, 2),
                  "blight_score": round(blight * 100, 1), "hardship": round(hard * 100),
                  "transit_adjacent": transit, "reach": round(reach, 2),
                  "need": round(need, 1), "placement_score": round(need * reach * suit, 1)})

    biz.sort(key=lambda x: -x["placement_score"])

    # ---- spatial dedupe (one storefront per ~120 m) --------------------------
    kept = []
    for b in biz:
        if all(dist_km(b["lat"], b["lon"], k["lat"], k["lon"]) > DEDUPE_M / 1000.0 for k in kept[-400:]):
            kept.append(b)
    print(f"[5] {len(kept)} candidates after {DEDUPE_M}m dedupe (from {len(biz)})")

    # ---- write ---------------------------------------------------------------
    props = ("name", "address", "type", "ca_name", "placement_score", "need", "reach",
             "recent_deaths_400m", "nearest_nax_km", "blight_score", "hardship", "transit_adjacent")
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]},
              "properties": {k: b[k] for k in props}} for b in kept]
    json.dump({"type": "FeatureCollection",
               "metadata": {"generated": time.strftime("%Y-%m-%d"), "n": len(feats),
                            "model": "reach x need (take-home retail distribution)",
                            "settled_window": list(SETTLED_YEARS)},
               "features": feats},
              open(f"{CLEAN}/placement_candidates.geojson", "w"))
    with open(f"{CLEAN}/placement_candidates.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(("rank",) + props)
        for i, b in enumerate(kept, 1):
            w.writerow((i,) + tuple(b[k] for k in props))

    print(f"\n    wrote placement_candidates.geojson/.csv ({len(feats)} sites)")
    print("\n=== TOP 15 STOREFRONTS (reach x need) ===")
    print(f"{'#':>3} {'score':>6} {'deaths':>6} {'naxkm':>6} {'transit':>7}  {'type':<24} name — area")
    for i, b in enumerate(kept[:15], 1):
        print(f"{i:>3} {b['placement_score']:>6} {b['recent_deaths_400m']:>6} {b['nearest_nax_km']:>6} "
              f"{str(b['transit_adjacent']):>7}  {b['type']:<24} {b['name'][:28]} — {b['ca_name']}")


if __name__ == "__main__":
    main()
