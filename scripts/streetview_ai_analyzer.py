#!/usr/bin/env python3
"""
SaveSpots Street View AI Risk Analyzer

Uses Google Street View Static API + Claude vision to score locations for
built-environment overdose risk factors validated in literature:

Evidence base:
  - Oxford AJE 2024: Chicago/NYC case-control — alleys, vacant lots, landscaping
  - PMC 2022 (NYC): abandoned buildings, physical disorder
  - Stopka 2019: liquor store density
  - Fentanyl spatiotemporal Chicago 2025: poverty, spatial clustering

Usage:
  export GOOGLE_MAPS_API_KEY=your_key
  export ANTHROPIC_API_KEY=your_key   (or use existing claude-code session)
  python3 scripts/streetview_ai_analyzer.py --lat 41.878 --lon -87.739 --label "Austin sample"
  python3 scripts/streetview_ai_analyzer.py --batch   # scores gap neighborhoods

The script outputs JSON risk assessments to data/clean/streetview_analysis/
"""
import os, sys, json, base64, argparse, math, time, urllib.request, urllib.parse, datetime

CLEAN = "data/clean"
OUT_DIR = os.path.join(CLEAN, "streetview_analysis")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# RISK FACTOR SCORING PROMPT (literature-grounded)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an urban environment analyst for SaveSpots, a harm-reduction organization.
You are analyzing Google Street View images to assess built-environment risk factors for opioid overdose,
based on published peer-reviewed literature.

You will score the scene on these validated risk factors (each 0-10):

RISK FACTORS (higher = more risk):
1. vacant_lots_or_lots: Empty parcels, vacant land, debris-filled lots visible
   (Oxford AJE 2024: elevated odds in Chicago + NYC)
2. abandoned_deteriorated_buildings: Boarded windows, collapsed structures, extreme deterioration
   (NYC PMC 2022: strongest predictor in NYC; Stopka 2019: Philadelphia)
3. liquor_stores_visible: Signs, storefronts, or windows of liquor/package goods stores
   (Multiple studies: density in high-overdose areas)
4. physical_disorder: Graffiti, litter/trash accumulation, damaged sidewalks, broken infrastructure
   (NYC systematic social observation studies)
5. alley_presence: Alleyways visible — Chicago-specific elevated risk factor
   (Oxford AJE 2024, Chicago-specific finding)
6. social_isolation: Lack of active pedestrians, blank walls, no "eyes on street"
   (Protective effect of active storefronts documented in NYC study)
7. dark_inadequate_lighting: Poor lighting, limited visibility, isolated areas
   (General overdose risk literature)
8. transient_indicators: Hotels/motels, SRO signs, shelters visible
   (Housing instability → overdose risk)

PROTECTIVE FACTORS (higher = more protection, reduces risk):
9. maintained_landscaping: Trees, grass, maintained gardens, green space
   (Oxford AJE 2024: PROTECTIVE — reduced odds Chicago + NYC)
10. active_storefronts: Active businesses with open doors, people entering/exiting
    (Social cohesion protective effect)

Respond ONLY with valid JSON in this exact format:
{
  "vacant_lots": 0-10,
  "abandoned_buildings": 0-10,
  "liquor_stores": 0-10,
  "physical_disorder": 0-10,
  "alley_presence": 0-10,
  "social_isolation": 0-10,
  "poor_lighting": 0-10,
  "transient_indicators": 0-10,
  "landscaping_protection": 0-10,
  "active_storefronts_protection": 0-10,
  "overall_risk_score": 0-100,
  "confidence": "low|medium|high",
  "key_observations": ["observation 1", "observation 2", "observation 3"],
  "recommended_naloxone_placement": true|false,
  "placement_rationale": "one sentence"
}

overall_risk_score = sum of risk factors (max 80) minus protective factors (max 20), normalized to 0-100.
Be specific in observations — quote what you actually see."""

def get_streetview_url(lat, lon, heading=None, fov=90, pitch=0, size="640x640"):
    """Build Google Street View Static API URL."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not key:
        raise ValueError("GOOGLE_MAPS_API_KEY not set. Get a key at console.cloud.google.com/apis.")
    params = {
        "location": f"{lat},{lon}",
        "size": size,
        "fov": fov,
        "pitch": pitch,
        "key": key,
    }
    if heading is not None:
        params["heading"] = heading
    return f"https://maps.googleapis.com/maps/api/streetview?{urllib.parse.urlencode(params)}"

def fetch_streetview_image(lat, lon, heading=None):
    """Download Street View image as base64."""
    url = get_streetview_url(lat, lon, heading)
    req = urllib.request.Request(url, headers={"User-Agent": "SaveSpots/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        if r.status != 200:
            raise RuntimeError(f"Street View API returned {r.status}")
        return base64.b64encode(r.read()).decode()

def analyze_with_claude(image_b64, lat, lon, label=""):
    """Score the Street View image using Claude vision."""
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}
                },
                {
                    "type": "text",
                    "text": f"Analyze this Google Street View image at coordinates ({lat}, {lon}){' — ' + label if label else ''}. Score the built-environment overdose risk factors."
                }
            ]
        }]
    )
    raw = response.content[0].text.strip()
    # Extract JSON even if Claude adds prose
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])

def score_location(lat, lon, label="", headings=(0, 90, 180, 270)):
    """Score a location using multiple Street View headings and average."""
    print(f"\nAnalyzing: {label or f'({lat},{lon})'}")
    all_scores = []
    for h in headings:
        print(f"  heading {h}°...", end=" ")
        try:
            img = fetch_streetview_image(lat, lon, heading=h)
            score = analyze_with_claude(img, lat, lon, label)
            all_scores.append(score)
            print(f"risk={score['overall_risk_score']}")
            time.sleep(0.5)
        except Exception as e:
            print(f"failed: {e}")

    if not all_scores:
        return None

    # Average numeric fields
    avg = {
        "lat": lat, "lon": lon, "label": label,
        "analyzed_at": datetime.datetime.now().isoformat(),
        "headings_analyzed": len(all_scores),
    }
    numeric = ["vacant_lots","abandoned_buildings","liquor_stores","physical_disorder",
               "alley_presence","social_isolation","poor_lighting","transient_indicators",
               "landscaping_protection","active_storefronts_protection","overall_risk_score"]
    for k in numeric:
        vals = [s[k] for s in all_scores if k in s]
        avg[k] = round(sum(vals)/len(vals), 1) if vals else 0

    avg["confidence"] = all_scores[0].get("confidence","medium")
    avg["key_observations"] = [obs for s in all_scores for obs in s.get("key_observations",[])][:6]
    avg["recommended_naloxone_placement"] = avg["overall_risk_score"] >= 55
    avg["placement_rationale"] = all_scores[-1].get("placement_rationale","")

    return avg

def batch_score_gap_areas():
    """Score highest-gap community area centroids."""
    if not os.path.exists(f"{CLEAN}/risk_scores.json"):
        print("ERROR: Run build_risk_layer.py first")
        return
    risk = json.load(open(f"{CLEAN}/risk_scores.json"))
    # Score top 10 highest OERS areas
    results = []
    for area in risk[:10]:
        result = score_location(area["lat"], area["lon"], area["community_area"])
        if result:
            result["oers"] = area["oers"]
            result["death_recent"] = area["death_recent"]
            results.append(result)
        time.sleep(1)
    path = os.path.join(OUT_DIR, "batch_gap_analysis.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved batch analysis -> {path}")
    return results

def demo_mode():
    """Run a demo without API keys, using pre-scored representative data."""
    print("\n[DEMO MODE] No API keys detected. Showing pre-computed example scores.")
    print("To run real analysis: export GOOGLE_MAPS_API_KEY=... && export ANTHROPIC_API_KEY=...")
    demo = [
        {"label":"Austin (W Chicago Ave)", "lat":41.8989,"lon":-87.7636,
         "overall_risk_score":82,"vacant_lots":7,"abandoned_buildings":8,
         "liquor_stores":6,"physical_disorder":7,"alley_presence":9,"social_isolation":6,
         "poor_lighting":5,"transient_indicators":4,
         "landscaping_protection":2,"active_storefronts_protection":2,
         "key_observations":["Multiple alleyways visible","Abandoned storefront with boarded windows",
                              "No maintained green space","Graffiti on building facades"],
         "recommended_naloxone_placement":True,
         "placement_rationale":"High vacant/disorder score + 266 recent deaths + only 2 naloxone locations within 1.5km"},
        {"label":"West Garfield Park (Madison St)", "lat":41.881,"lon":-87.738,
         "overall_risk_score":79,"vacant_lots":8,"abandoned_buildings":7,
         "liquor_stores":5,"physical_disorder":8,"alley_presence":9,"social_isolation":7,
         "poor_lighting":6,"transient_indicators":3,
         "landscaping_protection":1,"active_storefronts_protection":3,
         "key_observations":["Significant vacant lot coverage","Deteriorated housing stock","Alley network visible","Minimal retail activity"],
         "recommended_naloxone_placement":True,
         "placement_rationale":"Highest death density on West Side + severe gap in naloxone coverage"},
        {"label":"Humboldt Park (Division St)", "lat":41.899,"lon":-87.722,
         "overall_risk_score":71,"vacant_lots":6,"abandoned_buildings":5,
         "liquor_stores":7,"physical_disorder":6,"alley_presence":8,"social_isolation":4,
         "poor_lighting":4,"transient_indicators":5,
         "landscaping_protection":4,"active_storefronts_protection":5,
         "key_observations":["Multiple liquor stores on corridor","Some active commercial activity","Alley access behind buildings","Park provides some green space"],
         "recommended_naloxone_placement":True,
         "placement_rationale":"High liquor density + 124 recent deaths + limited naloxone access on north corridor"},
    ]
    path = os.path.join(OUT_DIR, "demo_analysis.json")
    with open(path, "w") as f:
        json.dump(demo, f, indent=2)
    print(f"Demo analysis saved -> {path}")
    return demo

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--label", default="")
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    has_google = bool(os.environ.get("GOOGLE_MAPS_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if args.demo or not (has_google and has_anthropic):
        demo_mode()
    elif args.batch:
        batch_score_gap_areas()
    elif args.lat and args.lon:
        result = score_location(args.lat, args.lon, args.label)
        if result:
            print(json.dumps(result, indent=2))
            fname = f"analysis_{args.lat}_{args.lon}.json"
            with open(os.path.join(OUT_DIR, fname), "w") as f:
                json.dump(result, f, indent=2)
    else:
        parser.print_help()
