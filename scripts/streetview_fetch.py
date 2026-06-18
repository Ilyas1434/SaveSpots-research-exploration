#!/usr/bin/env python3
"""
SaveSpots — Street View Image Fetcher  (Step 1 of 2)
====================================================
Downloads Google Street View images for the top in-business placement candidates.
This script ONLY fetches imagery (needs GOOGLE_MAPS_API_KEY). It does NOT call any
LLM — the scoring is done afterward by Claude Code reading the saved images, so it
runs on your Claude Code plan with no Anthropic API key / extra billing.

Workflow:
  1. export GOOGLE_MAPS_API_KEY=your_key
  2. python3 scripts/streetview_fetch.py            # downloads images + manifest
  3. Tell Claude Code: "score the street view images"  -> writes batch_gap_analysis.json
  4. Reload the map -> AI Vision tab shows real, Claude-scored results.

Cost: free metadata check skips locations with no imagery; ~4 images per site.
Street View Static API is ~$7 / 1,000 images.
"""
import os, sys, json, math, time, urllib.request, urllib.parse

CLEAN = "data/clean"
OUT_DIR = os.path.join(CLEAN, "streetview_analysis")
IMG_DIR = os.path.join(OUT_DIR, "images")
N_SITES = int(os.environ.get("SV_N_SITES", "15"))   # how many top candidates to image
HEADINGS = (0, 90, 180, 270)                          # 4 directions per site
DEDUPE_M = 150                                         # don't image two sites within 150m
SIZE = "640x640"

KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
META = "https://maps.googleapis.com/maps/api/streetview/metadata"
PIC = "https://maps.googleapis.com/maps/api/streetview"


def dist_m(a, b):
    R = 6371000.0
    dlat = math.radians(b[0] - a[0]); dlon = math.radians(b[1] - a[1])
    h = (math.sin(dlat/2)**2 +
         math.cos(math.radians(a[0]))*math.cos(math.radians(b[0]))*math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(h))


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SaveSpots/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def main():
    if not KEY:
        sys.exit("ERROR: set GOOGLE_MAPS_API_KEY first (see scripts/streetview_fetch.py header).")
    os.makedirs(IMG_DIR, exist_ok=True)

    cands = json.load(open(f"{CLEAN}/placement_candidates.geojson"))["features"]

    # spatially dedupe so we don't waste images on five stores on one corner
    picked = []
    for f in cands:  # already sorted by placement_score
        lat, lon = f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]
        if all(dist_m((lat, lon), (p["lat"], p["lon"])) > DEDUPE_M for p in picked):
            p = f["properties"]
            picked.append({"name": p["name"], "address": p["address"], "type": p["type"],
                           "ca_name": p["ca_name"], "placement_score": p["placement_score"],
                           "recent_deaths_400m": p["recent_deaths_400m"],
                           "nearest_nax_km": p["nearest_nax_km"], "lat": lat, "lon": lon})
        if len(picked) >= N_SITES:
            break

    manifest = []
    for i, s in enumerate(picked):
        sid = f"site{i:02d}"
        # free metadata check — does Street View imagery exist here?
        loc = f"{s['lat']},{s['lon']}"
        meta_url = f"{META}?{urllib.parse.urlencode({'location': loc, 'key': KEY})}"
        try:
            meta = json.loads(get(meta_url))
        except Exception as e:
            print(f"  {sid} metadata failed: {e}"); continue
        if meta.get("status") != "OK":
            print(f"  {sid} no imagery ({meta.get('status')}) — {s['name']}"); continue

        imgs = []
        for h in HEADINGS:
            fn = f"{sid}_h{h}.jpg"
            params = {"location": f"{s['lat']},{s['lon']}", "size": SIZE,
                      "fov": 90, "pitch": 0, "heading": h, "key": KEY}
            try:
                data = get(f"{PIC}?{urllib.parse.urlencode(params)}")
                with open(os.path.join(IMG_DIR, fn), "wb") as fh:
                    fh.write(data)
                imgs.append(fn)
                time.sleep(0.1)
            except Exception as e:
                print(f"    {fn} failed: {e}")
        print(f"  {sid}: {len(imgs)} imgs — {s['name']} ({s['ca_name']})")
        manifest.append({"site_id": sid, "images": imgs, **s})

    with open(os.path.join(OUT_DIR, "fetch_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  {len(manifest)} sites imaged -> {IMG_DIR}")
    print(f"  manifest -> {OUT_DIR}/fetch_manifest.json")
    print("\n  Next: tell Claude Code \"score the street view images\".")


if __name__ == "__main__":
    main()
