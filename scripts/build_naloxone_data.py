#!/usr/bin/env python3
"""
Build naloxone location dataset from all known public sources.

PRIMARY SOURCE (Chicago, 151 locations, live):
  CDPH ArcGIS Feature Service — the data behind the city's "Find Narcan" map.
  No auth required. Already geocoded to WGS84.
  https://services7.arcgis.com/A03QrhyHnDaUmK0W/arcgis/rest/services/Harm_Reduction_Boxes/FeatureServer/60

SUPPLEMENTAL (suburban Cook County + CTA address patch):
  Cook County Health vending machine addresses (courthouses + Howard Red Line CTA station).
  Geocoded via US Census Bureau geocoder (free, no key needed).

Outputs: data/clean/naloxone_locations.geojson
"""
import json, time, os, urllib.parse, urllib.request

CLEAN_DIR = "data/clean"
os.makedirs(CLEAN_DIR, exist_ok=True)

CDPH_ARCGIS = (
    "https://services7.arcgis.com/A03QrhyHnDaUmK0W/arcgis/rest/services/"
    "Harm_Reduction_Boxes/FeatureServer/60/query"
    "?where=Status%3D%27Active%27&outFields=*&outSR=4326&f=json"
)

# CTA station addresses are null in the CDPH dataset — patch them here.
# Howard Red Line is confirmed on cookcountyhealth.org/naloxone but not yet in the CDPH feed.
CTA_ADDRESS_PATCH = {
    "Wilson Red Line Terminal":       ("4620 N Broadway", "Chicago", "IL", "60640"),
    "Harlem Green Line Terminal":     ("1 Harlem Ave",    "Oak Park", "IL", "60130"),
    "Jefferson Park Blue Line Terminal": ("4917 N Milwaukee Ave", "Chicago", "IL", "60630"),
    "Central Park Pink Line Terminal": ("721 N Central Park Ave", "Chicago", "IL", "60624"),
    "47th St Red Line Terminal":      ("220 W 47th St",   "Chicago", "IL", "60609"),
}

# Suburban Cook County locations not covered by the Chicago-only CDPH feed.
# Sourced from cookcountyhealth.org/naloxone/ and the original Cook County map.
SUBURBAN_LOCATIONS = [
    # Cook County Health suburban courthouses (vending machines, code 555)
    {"name": "Bridgeview Courthouse",           "address": "10220 S 76th Ave",   "city": "Bridgeview",     "state": "IL", "zip": "60455", "type": "vending_machine",  "operator": "Cook County Health", "source": "cookcountyhealth.org/naloxone 2026"},
    {"name": "Markham Courthouse",              "address": "16501 Kedzie Ave",   "city": "Markham",        "state": "IL", "zip": "60428", "type": "vending_machine",  "operator": "Cook County Health", "source": "cookcountyhealth.org/naloxone 2026"},
    {"name": "Maywood Courthouse",              "address": "1311 Maybrook Dr",   "city": "Maywood",        "state": "IL", "zip": "60153", "type": "vending_machine",  "operator": "Cook County Health", "source": "cookcountyhealth.org/naloxone 2026"},
    {"name": "Rolling Meadows Courthouse",      "address": "2121 Euclid Ave",    "city": "Rolling Meadows","state": "IL", "zip": "60008", "type": "vending_machine",  "operator": "Cook County Health", "source": "cookcountyhealth.org/naloxone 2026"},
    {"name": "Skokie Courthouse",               "address": "5600 Old Orchard Rd","city": "Skokie",         "state": "IL", "zip": "60077", "type": "vending_machine",  "operator": "Cook County Health", "source": "cookcountyhealth.org/naloxone 2026"},
    # Howard Red Line — confirmed on CCH live page but not yet in CDPH ArcGIS feed
    {"name": "Howard Red Line Station",         "address": "7519 N Paulina St",  "city": "Chicago",        "state": "IL", "zip": "60626", "type": "vending_machine",  "operator": "Cook County Health / CTA", "source": "cookcountyhealth.org/naloxone 2026"},
    # CTA Harlem/Lake is Oak Park (suburban), needs geocoding
    {"name": "Harlem/Lake Green Line Station",  "address": "1 Harlem Ave",       "city": "Oak Park",       "state": "IL", "zip": "60130", "type": "vending_machine",  "operator": "Cook County Health / CTA", "source": "CCH/CTA pilot Sep 2025"},
    # West Side Heroin/Opioid Task Force (harm reduction org, West Side)
    {"name": "West Side Heroin/Opioid Task Force", "address": "310 N Pulaski Rd", "city": "Chicago",       "state": "IL", "zip": "60624", "type": "harm_reduction_org", "operator": "West Side Task Force", "source": "Block Club Chicago Jan 2026"},
    # Suburban distribution boxes (Cook County map, mostly suburbs)
    {"name": "Ajeeba Hair Design",              "address": "1254 Burnham Ave",   "city": "Calumet City",   "state": "IL", "zip": "60409", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "AristaCare",                      "address": "1056 W Golf Rd",     "city": "Hoffman Estates","state": "IL", "zip": "60169", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Bellwood Liquor and Grocery",     "address": "5001 Saint Charles Rd","city": "Bellwood",     "state": "IL", "zip": "60104", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Blue Island Public Library",      "address": "2433 York Street",   "city": "Blue Island",    "state": "IL", "zip": "60406", "type": "library",          "operator": "Cook County", "source": "Cook County map"},
    {"name": "Center of Concern",               "address": "1665 Elk Blvd",      "city": "Des Plaines",    "state": "IL", "zip": "60016", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Chicago Ridge Library",           "address": "10400 Oxford Ave",   "city": "Chicago Ridge",  "state": "IL", "zip": "60415", "type": "library",          "operator": "Cook County", "source": "Cook County map"},
    {"name": "Corazon Community Services",      "address": "5339 W 25th St",     "city": "Cicero",         "state": "IL", "zip": "60804", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "DA Candy Corner",                 "address": "1117 Madison St",    "city": "Maywood",        "state": "IL", "zip": "60153", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Debbie's Darn Good Deals",        "address": "1950 S Ruby Street", "city": "Melrose Park",   "state": "IL", "zip": "60160", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Drama Beauty Cicero",             "address": "4909 W 14th St",     "city": "Cicero",         "state": "IL", "zip": "60804", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Express Food Mart",               "address": "7026 16th St",       "city": "Berwyn",         "state": "IL", "zip": "60402", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Healthy Soul Talk LLC",           "address": "1701 S 1st Ave",     "city": "Maywood",        "state": "IL", "zip": "60153", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Lansing Public Library",          "address": "2750 Indiana Ave",   "city": "Lansing",        "state": "IL", "zip": "60438", "type": "library",          "operator": "Cook County", "source": "Cook County map"},
    {"name": "Maine Township",                  "address": "1700 Ballard Road",  "city": "Park Ridge",     "state": "IL", "zip": "60068", "type": "government",       "operator": "Cook County", "source": "Cook County map"},
    {"name": "New Era Restaurant",              "address": "15 N 5th Ave",       "city": "Maywood",        "state": "IL", "zip": "60153", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Niles-Maine District Library",    "address": "6960 W Oakton St",   "city": "Niles",          "state": "IL", "zip": "60714", "type": "library",          "operator": "Cook County", "source": "Cook County map"},
    {"name": "Oak Lawn Public Library",         "address": "9427 Raymond Avenue","city": "Oak Lawn",       "state": "IL", "zip": "60453", "type": "library",          "operator": "Cook County", "source": "Cook County map"},
    {"name": "Perros Brothers South Chicago Heights", "address": "2601 Chicago Rd","city": "South Chicago Heights","state": "IL","zip": "60411","type": "distribution_box","operator": "Cook County","source": "Cook County map"},
    {"name": "Perros Brothers Olympia Fields",  "address": "3770 Lincoln Highway","city": "Olympia Fields", "state": "IL", "zip": "60461", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "PLCCA",                           "address": "411 Madison St",     "city": "Maywood",        "state": "IL", "zip": "60153", "type": "harm_reduction_org","operator": "Cook County", "source": "Cook County map"},
    {"name": "RayMil Consulting",               "address": "518 S 7th Avenue",   "city": "Maywood",        "state": "IL", "zip": "60153", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Respond Now",                     "address": "1250 Portland Ave",  "city": "Chicago Heights","state": "IL", "zip": "60411", "type": "harm_reduction_org","operator": "Cook County", "source": "Cook County map"},
    {"name": "Riverdale Public Library",        "address": "208 W 144th St",     "city": "Riverdale",      "state": "IL", "zip": "60827", "type": "library",          "operator": "Cook County", "source": "Cook County map"},
    {"name": "Salvation Army Community Ctr",    "address": "2337 S Laramie Ave", "city": "Cicero",         "state": "IL", "zip": "60804", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Self-Help Closet & Pantry",       "address": "769 Holiday Ln",     "city": "Des Plaines",    "state": "IL", "zip": "60016", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "South Suburban College Oak Forest","address": "16333 S Kilbourn Ave","city": "Oak Forest",   "state": "IL", "zip": "60452", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "South Suburban College South Holland","address": "15800 State St", "city": "South Holland",  "state": "IL", "zip": "60473", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "South Suburban Council",          "address": "1909 Cheker Square", "city": "Hazel Crest",    "state": "IL", "zip": "60429", "type": "harm_reduction_org","operator": "Cook County", "source": "Cook County map"},
    {"name": "Steger Library",                  "address": "54 E 31st St",       "city": "Steger",         "state": "IL", "zip": "60475", "type": "library",          "operator": "Cook County", "source": "Cook County map"},
    {"name": "The Print Labb",                  "address": "1819 Roosevelt Rd",  "city": "Broadview",      "state": "IL", "zip": "60155", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Thornton Public Library",         "address": "115 E Margaret St",  "city": "Thornton",       "state": "IL", "zip": "60476", "type": "library",          "operator": "Cook County", "source": "Cook County map"},
    {"name": "Tinley Park Apothecary",          "address": "17320 Oak Park Ave", "city": "Tinley Park",    "state": "IL", "zip": "60477", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Tinley Park Public Library",      "address": "7851 Timber Dr",     "city": "Tinley Park",    "state": "IL", "zip": "60477", "type": "library",          "operator": "Cook County", "source": "Cook County map"},
    {"name": "Tony's Food & Liquor",            "address": "1709 E Sauk Trl",    "city": "Chicago Heights","state": "IL", "zip": "60411", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Towncare Pharmacy LLC",           "address": "13805 S Cicero Ave", "city": "Midlothian",     "state": "IL", "zip": "60455", "type": "pharmacy",         "operator": "Cook County", "source": "Cook County map"},
    {"name": "Triton College",                  "address": "2000 North 5th Avenue","city": "River Grove",  "state": "IL", "zip": "60171", "type": "distribution_box", "operator": "Cook County", "source": "Cook County map"},
    {"name": "Village of Bellwood",             "address": "3200 Washington Blvd","city": "Bellwood",      "state": "IL", "zip": "60104", "type": "government",       "operator": "Cook County", "source": "Cook County map"},
    {"name": "Village of Maywood",              "address": "40 Madison St",      "city": "Maywood",        "state": "IL", "zip": "60153", "type": "government",       "operator": "Cook County", "source": "Cook County map"},
    {"name": "Village of Maywood Masonic Temple","address": "200 S 5th Ave",     "city": "Maywood",        "state": "IL", "zip": "60153", "type": "government",       "operator": "Cook County", "source": "Cook County map"},
    {"name": "William Leonard Library of Robbins","address": "13820 Central Park Ave","city": "Robbins",   "state": "IL", "zip": "60472", "type": "library",          "operator": "Cook County", "source": "Cook County map"},
    {"name": "Commissioner Kevin Morrison Office","address": "1325 Wiley Road Suite 141","city": "Schaumburg","state": "IL","zip": "60173","type": "government",      "operator": "Cook County", "source": "Cook County map"},
    {"name": "Commissioner Kisha McCaskill Office","address": "3039 W 159th Street","city": "Markham",     "state": "IL", "zip": "60428", "type": "government",       "operator": "Cook County", "source": "Cook County map"},
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SaveSpots/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def geocode(address, city, state, zip_):
    params = urllib.parse.urlencode({
        "street": address, "city": city, "state": state, "zip": zip_,
        "benchmark": "Public_AR_Current", "format": "json"
    })
    url = f"https://geocoding.geo.census.gov/geocoder/locations/address?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SaveSpots/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        matches = d.get("result", {}).get("addressMatches", [])
        if matches:
            c = matches[0]["coordinates"]
            return float(c["x"]), float(c["y"])  # lon, lat
    except Exception:
        pass
    return None, None


def fetch_cdph_chicago():
    """Pull all active locations from CDPH ArcGIS feature service (Chicago only, pre-geocoded)."""
    print("Pulling CDPH ArcGIS naloxone feed (Chicago)...")
    data = get(CDPH_ARCGIS)
    features = []
    skipped_null_geo = 0
    for f in data.get("features", []):
        a = f["attributes"]
        g = f.get("geometry")
        if not g or g.get("x") is None:
            # Patch known CTA stations that have null geometry in the feed
            patch = CTA_ADDRESS_PATCH.get(a.get("LOCATION_NAME", ""))
            if patch:
                addr, city, state, zip_ = patch
                lon, lat = geocode(addr, city, state, zip_)
                if not lon:
                    skipped_null_geo += 1
                    continue
                time.sleep(0.15)
            else:
                skipped_null_geo += 1
                continue
        else:
            lon, lat = g["x"], g["y"]

        addr_str = a.get("ADDRESS") or ""
        zip_str = str(a.get("ZIP_CODE") or "")
        in_chicago = a.get("COMMUNITY_AREA") is not None

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": a.get("LOCATION_NAME", ""),
                "address": f"{addr_str}, Chicago, IL {zip_str}".strip(", "),
                "city": "Chicago",
                "zip": zip_str,
                "type": (a.get("LOCATION_TYPE") or "").lower().replace(" ", "_"),
                "operator": a.get("LOCATION_TYPE", ""),
                "community_area": a.get("COMMUNITY_AREA"),
                "ward": a.get("WARD_NUM"),
                "phone": a.get("PHONE"),
                "source": "CDPH ArcGIS Harm_Reduction_Boxes (live)",
                "in_chicago": in_chicago,
            }
        })

    print(f"  {len(features)} Chicago locations from CDPH ArcGIS ({skipped_null_geo} skipped / null geo)")
    return features


def geocode_suburban():
    """Geocode suburban Cook County + non-CDPH supplemental locations."""
    print(f"\nGeocoding {len(SUBURBAN_LOCATIONS)} supplemental/suburban locations...")
    features = []
    for i, loc in enumerate(SUBURBAN_LOCATIONS):
        lon, lat = geocode(loc["address"], loc["city"], loc["state"], loc["zip"])
        status = "✓" if lon else "✗"
        print(f"  {status} [{i+1}/{len(SUBURBAN_LOCATIONS)}] {loc['name']}")
        if lon and lat:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "name": loc["name"],
                    "address": f"{loc['address']}, {loc['city']}, {loc['state']} {loc['zip']}",
                    "city": loc["city"],
                    "zip": loc["zip"],
                    "type": loc["type"],
                    "operator": loc["operator"],
                    "source": loc["source"],
                    "in_chicago": loc["city"].lower() == "chicago",
                }
            })
        time.sleep(0.15)
    print(f"  {len(features)} geocoded (of {len(SUBURBAN_LOCATIONS)})")
    return features


def main():
    chicago_feats = fetch_cdph_chicago()
    suburban_feats = geocode_suburban()

    all_features = chicago_feats + suburban_feats

    out = {
        "type": "FeatureCollection",
        "metadata": {
            "total": len(all_features),
            "chicago": len(chicago_feats),
            "suburban_cook": len(suburban_feats),
            "primary_source": "CDPH ArcGIS Harm_Reduction_Boxes FeatureServer/60 (151 active Chicago locations)",
            "supplemental": "Cook County Health (courthouses/CTA), suburban Cook County map, West Side Task Force",
        },
        "features": all_features,
    }
    path = os.path.join(CLEAN_DIR, "naloxone_locations.geojson")
    with open(path, "w") as f:
        json.dump(out, f)
    print(f"\n  wrote {path} ({len(all_features)} total locations)")
    in_chicago = sum(1 for f in all_features if f["properties"].get("in_chicago"))
    print(f"  {in_chicago} in Chicago, {len(all_features) - in_chicago} suburban Cook")


if __name__ == "__main__":
    main()
