#!/usr/bin/env python3
"""
SaveSpots Phase 0 ETL: pull Cook County Medical Examiner opioid-related deaths
from the live Socrata API, clean/dedupe, and emit analysis-ready CSV + GeoJSON.

Source: https://datacatalog.cookcountyil.gov/resource/cjeq-bs86.json  (updates daily)
Run:    python3 scripts/pull_opioid_data.py
"""
import csv, json, time, datetime, os
import requests

API = "https://datacatalog.cookcountyil.gov/resource/cjeq-bs86.json"
RAW_DIR, CLEAN_DIR = "data/raw", "data/clean"
PAGE = 50000  # Socrata allows large limits on this dataset

FIELDS = [
    "casenumber", "death_date", "incident_date", "age", "gender", "race", "latino",
    "manner", "primarycause", "secondarycause", "gunrelated",
    "latitude", "longitude", "chi_commarea", "chi_ward",
    "incident_street", "incident_city", "incident_zip",
    "residence_city", "residence_zip",
]

def fetch_all():
    rows, offset = [], 0
    while True:
        params = {
            "opioids": "true",
            "$select": ",".join(FIELDS),
            "$order": "casenumber",
            "$limit": PAGE,
            "$offset": offset,
        }
        r = requests.get(API, params=params, timeout=60)
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        time.sleep(0.3)
    return rows

def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(CLEAN_DIR, exist_ok=True)
    stamp = datetime.date.today().isoformat()

    print("Pulling live opioid records from Cook County ME API ...")
    rows = fetch_all()
    print(f"  fetched {len(rows)} opioid-related records (all Cook County)")

    # dedupe by casenumber
    seen, deduped = set(), []
    for row in rows:
        cn = row.get("casenumber")
        if cn and cn not in seen:
            seen.add(cn)
            deduped.append(row)
    rows = deduped

    # raw snapshot
    raw_path = os.path.join(RAW_DIR, f"opioid_me_{stamp}.json")
    with open(raw_path, "w") as f:
        json.dump(rows, f)
    print(f"  saved raw snapshot -> {raw_path}")

    # split + flag
    def has_coords(r):
        return bool(r.get("latitude") and r.get("longitude"))
    def is_chicago(r):
        return bool(r.get("chi_commarea"))

    chicago = [r for r in rows if is_chicago(r)]
    suburban = [r for r in rows if not is_chicago(r)]

    # clean CSV (all Cook, with a scope + geocoded flag so suburbs are 1 filter away)
    csv_path = os.path.join(CLEAN_DIR, "opioid_deaths_cookcounty.csv")
    out_fields = FIELDS + ["scope", "geocoded", "death_year"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for r in rows:
            o = {k: r.get(k, "") for k in FIELDS}
            o["scope"] = "Chicago" if is_chicago(r) else "Suburban Cook"
            o["geocoded"] = "yes" if has_coords(r) else "no"
            dd = r.get("death_date", "")
            o["death_year"] = dd[:4] if dd else ""
            w.writerow(o)
    print(f"  wrote clean CSV -> {csv_path}")

    # GeoJSON for the map (Chicago, geocoded only)
    feats = []
    for r in chicago:
        if not has_coords(r):
            continue
        try:
            lon, lat = float(r["longitude"]), float(r["latitude"])
        except ValueError:
            continue
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "case": r.get("casenumber"),
                "death_date": r.get("death_date", "")[:10],
                "year": r.get("death_date", "")[:4],
                "age": r.get("age"), "gender": r.get("gender"), "race": r.get("race"),
                "cause": r.get("primarycause"),
                "community_area": r.get("chi_commarea"),
                "ward": r.get("chi_ward"),
            },
        })
    geo_path = os.path.join(CLEAN_DIR, "opioid_deaths_chicago.geojson")
    with open(geo_path, "w") as f:
        json.dump({"type": "FeatureCollection",
                   "metadata": {"source": "Cook County ME Case Archive (cjeq-bs86)",
                                "pulled": stamp, "n": len(feats)},
                   "features": feats}, f)
    print(f"  wrote Chicago GeoJSON -> {geo_path} ({len(feats)} mappable points)")

    # quick summary
    print("\n=== SUMMARY ===")
    print(f"total opioid deaths (Cook County):     {len(rows)}")
    print(f"  Chicago (has community area):        {len(chicago)}")
    print(f"  Suburban Cook:                       {len(suburban)}")
    print(f"  Chicago + geocoded (mappable):       {len(feats)}")

if __name__ == "__main__":
    main()
