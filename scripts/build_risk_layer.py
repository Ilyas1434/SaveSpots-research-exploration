#!/usr/bin/env python3
"""
SaveSpots Risk Layer Builder
Pulls validated built-environment risk factors from Chicago open data
and computes a neighborhood-level Overdose Environment Risk Score (OERS)
based on peer-reviewed literature.

Literature basis:
- Stopka et al. (2019) - liquor stores, neighborhood deprivation
- Oxford AJE (2024) - Chicago/NYC case-control: vacant lots, alleys, physical disorder
- NYC PMC study (2022) - abandoned buildings, physical/social disorder
- Chicago fentanyl spatiotemporal study (2025) - poverty as consistent risk factor

Run: python3 scripts/build_risk_layer.py
"""
import json, csv, time, math, urllib.request, urllib.parse, os

CLEAN = "data/clean"
os.makedirs(CLEAN, exist_ok=True)

def fetch(url, label=""):
    print(f"  fetching {label}...")
    req = urllib.request.Request(url, headers={"User-Agent": "SaveSpots/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def fetch_paged(base_url, label, page=5000):
    rows, offset = [], 0
    while True:
        sep = "&" if "?" in base_url else "?"
        url = f"{base_url}{sep}$limit={page}&$offset={offset}"
        batch = fetch(url, f"{label} offset={offset}")
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
        time.sleep(0.2)
    return rows

def dist_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# ---------------------------------------------------------------------------
# 1. Pull data layers
# ---------------------------------------------------------------------------

print("\n[1] Pulling Package Goods (liquor) stores ...")
liquor = fetch_paged(
    "https://data.cityofchicago.org/resource/uupf-x98q.json"
    "?$where=license_description='Package+Goods'%20AND%20license_status='AAI'"
    "&$select=doing_business_as_name,address,community_area_name,latitude,longitude",
    "liquor stores"
)
liquor_pts = [(float(r["latitude"]), float(r["longitude"])) for r in liquor if r.get("latitude") and r.get("longitude")]
print(f"  {len(liquor_pts)} geocoded liquor stores")

print("\n[2] Pulling 311 abandoned building reports (open) ...")
abandoned = fetch_paged(
    "https://data.cityofchicago.org/resource/7as2-ds3y.json"
    "?$where=status='Open'"
    "&$select=latitude,longitude,community_area",
    "abandoned buildings"
)
abandoned_pts = [(float(r["latitude"]), float(r["longitude"])) for r in abandoned if r.get("latitude") and r.get("longitude")]
print(f"  {len(abandoned_pts)} geocoded abandoned building reports")

print("\n[3] Pulling recent graffiti/disorder 311 reports (2022+) ...")
graffiti = fetch_paged(
    "https://data.cityofchicago.org/resource/hec5-y4x5.json"
    "?$select=latitude,longitude,community_area",
    "graffiti"
)
graffiti_pts = [(float(r["latitude"]), float(r["longitude"])) for r in graffiti if r.get("latitude") and r.get("longitude")]
print(f"  {len(graffiti_pts)} geocoded graffiti reports")

print("\n[4] Pulling ACS socioeconomic / hardship index ...")
acs = fetch("https://data.cityofchicago.org/resource/kn9c-c2s2.json?$limit=200", "ACS hardship")
acs_by_ca_num = {r.get("ca", r.get("community_area_number", "")): r for r in acs}

print("\n[5] Pulling public health indicators (poverty, unemployment) ...")
phi = fetch("https://data.cityofchicago.org/resource/iqnk-2tcu.json?$limit=200", "public health indicators")
phi_by_ca_name = {r["community_area_name"].upper(): r for r in phi}

# ---------------------------------------------------------------------------
# 2. Load death data for CA centroids
# ---------------------------------------------------------------------------
print("\n[6] Loading death data + community area centroids ...")
deaths = json.load(open(f"{CLEAN}/opioid_deaths_chicago.geojson"))
gap_data = json.load(open(f"{CLEAN}/coverage_gap.json"))

from collections import defaultdict, Counter
ca_pts = defaultdict(list)
for f in deaths["features"]:
    ca = f["properties"].get("community_area", "")
    lon, lat = f["geometry"]["coordinates"]
    if ca:
        ca_pts[ca].append((lat, lon))

ca_cent = {}
for ca, pts in ca_pts.items():
    ca_cent[ca] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

# CA number mapping (from ACS data)
ca_name_to_num = {}
for r in acs:
    ca_name_to_num[r["community_area_name"].upper()] = r["ca"]

# ---------------------------------------------------------------------------
# 3. Compute Overdose Environment Risk Score (OERS)
# ---------------------------------------------------------------------------
print("\n[7] Computing OERS per community area ...")

def count_within(pts, clat, clon, radius_km):
    return sum(1 for (lat, lon) in pts if dist_km(clat, clon, lat, lon) <= radius_km)

results = []
for ca, (clat, clon) in ca_cent.items():
    r = 2.0  # 2km radius (neighborhood scale)
    r_tight = 0.5  # 500m for hyper-local

    n_liquor = count_within(liquor_pts, clat, clon, r)
    n_liquor_tight = count_within(liquor_pts, clat, clon, r_tight)
    n_abandoned = count_within(abandoned_pts, clat, clon, r)
    n_graffiti = count_within(graffiti_pts, clat, clon, r)
    death_total = gap_data.get(ca, {}).get("total", 0)
    death_recent = gap_data.get(ca, {}).get("recent", 0)
    nax_nearby = gap_data.get(ca, {}).get("nax_nearby", 0)

    # Poverty from ACS
    ca_num = ca_name_to_num.get(ca)
    acs_row = acs_by_ca_num.get(str(ca_num), {}) if ca_num else {}
    poverty_pct = float(acs_row.get("percent_households_below_poverty", 0) or 0)
    hardship = float(acs_row.get("hardship_index", 0) or 0)

    # OERS formula (normalized 0-100, literature-weighted):
    # Poverty: strongest predictor (weight 0.35)
    # Abandoned buildings: strong (0.20)
    # Liquor density: moderate (0.15)
    # Physical disorder/graffiti: moderate (0.15)
    # Death burden: (0.15)
    pov_score = min(poverty_pct / 50, 1.0) * 35
    abn_score = min(n_abandoned / 20, 1.0) * 20
    liq_score = min(n_liquor / 30, 1.0) * 15
    dis_score = min(n_graffiti / 200, 1.0) * 15
    death_score = min(death_recent / 150, 1.0) * 15
    oers = round(pov_score + abn_score + liq_score + dis_score + death_score, 1)

    results.append({
        "community_area": ca,
        "lat": clat, "lon": clon,
        "oers": oers,
        "death_total": death_total,
        "death_recent": death_recent,
        "nax_nearby": nax_nearby,
        "gap_score": gap_data.get(ca, {}).get("gap_score", 0),
        "n_liquor_2km": n_liquor,
        "n_liquor_500m": n_liquor_tight,
        "n_abandoned": n_abandoned,
        "n_graffiti": n_graffiti,
        "poverty_pct": poverty_pct,
        "hardship_index": hardship,
    })

results.sort(key=lambda x: -x["oers"])

# Save
with open(f"{CLEAN}/risk_scores.json", "w") as f:
    json.dump(results, f)

print("\n=== TOP 15 COMMUNITY AREAS BY OERS ===")
print(f"{'Community Area':<26}{'OERS':>6}{'Deaths':>8}{'Recent':>8}{'Nax':>5}{'Poverty%':>10}{'Liquor':>8}{'Aband':>7}")
for r in results[:15]:
    print(f"{r['community_area']:<26}{r['oers']:>6}{r['death_total']:>8}{r['death_recent']:>8}{r['nax_nearby']:>5}{r['poverty_pct']:>10.1f}{r['n_liquor_2km']:>8}{r['n_abandoned']:>7}")

print(f"\n  wrote {CLEAN}/risk_scores.json ({len(results)} areas)")
