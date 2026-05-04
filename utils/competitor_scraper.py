"""
Competitor Keyword Scraper - Production Grade
Scrapes: Thrillophilia, Klook, Incredible India, Uttarakhand Tourism, TripAdvisor, GetYourGuide
for Rishikesh adventure content and keyword signals.

HOW TO RUN:
    cd ai-blog-generator-base-refactor-segmentation
    python utils/competitor_scraper.py

OUTPUT:
    data/competitor_keywords_raw.json  - raw dump from all sources
    Console: keyword priority scores + merge summary
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Fix Windows console encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# -- Path Setup --
BASE_DIR = Path(__file__).parent.parent
DATA_DIR  = BASE_DIR / "data"
CONFIG_DIR = DATA_DIR / "config"
OUTPUT_RAW  = DATA_DIR / "competitor_keywords_raw.json"
KEYWORDS_FILE = CONFIG_DIR / "keywords.json"

# -- Target URLs --
COMPETITOR_URLS = {
    "thrillophilia_activities": "https://www.thrillophilia.com/cities/rishikesh/things-to-do",
    "thrillophilia_rafting":    "https://www.thrillophilia.com/rishikesh-rafting",
    "thrillophilia_camping":    "https://www.thrillophilia.com/rishikesh-camping",
    "uttarakhand_tourism":      "https://uttarakhandtourism.gov.in/destination/rishikesh",
    "incredible_india":         "https://www.incredibleindia.org/content/incredible-india-v2/en/destinations/rishikesh.html",
    "getyourguide_rishikesh":   "https://www.getyourguide.com/rishikesh-l97255/",
    "klook_rishikesh":          "https://www.klook.com/en-IN/city/rishikesh-activities/",
    "tripadvisor_rishikesh":    "https://www.tripadvisor.com/Attractions-g297654-Activities-Rishikesh_Tehri_Garhwal_District_Uttarakhand.html",
}

# -- Rishikesh-specific keyword signals --
RISHIKESH_KEYWORD_SIGNALS = [
    "rishikesh", "rafting", "bungee", "bungy", "jumping", "paragliding",
    "camping", "kayaking", "trekking", "adventure", "river", "ganga",
    "himalayan", "yoga", "meditation", "shivpuri", "kaudiyala", "brahmpuri",
    "lakshman jhula", "ram jhula", "triveni ghat", "ganga aarti",
    "giant swing", "flying fox", "zipline", "zip line", "rappelling",
    "cliff jumping", "rock climbing", "hot air balloon", "wellness",
    "best time", "how to reach", "packages", "price", "cost", "booking",
    "weekend", "family", "couple", "solo", "group", "luxury", "budget",
    "uttarakhand", "haridwar", "dehradun", "neelkanth", "beatles ashram",
    "mohanchatti", "marine drive", "waterfall", "sky cycling", "scad",
    "reverse bungee", "quickjump", "quick jump", "splash bungee"
]


async def scrape_with_playwright(url: str, site_name: str) -> Optional[str]:
    """Scrape a JS-rendered page using Playwright."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            content = await page.content()
            await browser.close()
            print(f"  [OK] [{site_name}] Scraped {len(content)} chars")
            return content
    except Exception as e:
        print(f"  [FAIL] [{site_name}] Playwright failed: {e}")
        return None


async def scrape_with_requests(url: str, site_name: str) -> Optional[str]:
    """Fallback: simple HTTP GET (works for static/SSR pages)."""
    import urllib.request
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            print(f"  [OK] [{site_name}] Static fetch: {len(content)} chars")
            return content
    except Exception as e:
        print(f"  [WARN] [{site_name}] Static fetch failed: {e}")
        return None


def extract_text_from_html(html: str) -> str:
    """Strip HTML tags from raw content."""
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_keywords_from_text(text: str, site: str) -> List[Dict]:
    """
    Extract relevant keyword phrases from page text.
    Returns list of {keyword, source, weight}.
    """
    found = []

    # 1. Extract heading-style phrases (Title Case phrases 2-6 words)
    heading_matches = re.findall(
        r'\b([A-Z][a-z]+(?: [A-Z]?[a-z]+){1,5})\b',
        text
    )
    for match in heading_matches:
        m_lower = match.lower()
        if any(sig in m_lower for sig in RISHIKESH_KEYWORD_SIGNALS):
            if len(m_lower.split()) >= 2:
                found.append({
                    "keyword": m_lower.strip(),
                    "source": site,
                    "weight": 3
                })

    # 2. Extract anchor text from links (slug-based keywords)
    text_lower = text.lower()
    anchor_slugs = re.findall(r'/([a-z][a-z0-9-]{3,40})(?:\?|"|\'|/|$)', text_lower)
    for slug in anchor_slugs:
        phrase = slug.replace("-", " ").replace("_", " ").strip()
        if any(sig in phrase for sig in RISHIKESH_KEYWORD_SIGNALS) and len(phrase.split()) >= 2:
            found.append({
                "keyword": phrase,
                "source": site,
                "weight": 2
            })

    # 3. Extract FAQ-style questions
    questions = re.findall(r'([A-Z][^.!?]{15,80}\?)', text)
    for q in questions:
        q_lower = q.lower()
        if any(sig in q_lower for sig in RISHIKESH_KEYWORD_SIGNALS):
            found.append({
                "keyword": q_lower.strip().rstrip("?"),
                "source": site,
                "weight": 4
            })

    return found


def score_and_deduplicate(raw_keywords: List[Dict]) -> List[Dict]:
    """
    Aggregate, score, and deduplicate keywords from all sources.
    Score = total_weight * sqrt(frequency) * source_diversity
    """
    aggregated: Dict[str, Dict] = {}

    for item in raw_keywords:
        kw = item["keyword"].lower().strip()
        kw = re.sub(r'[^a-z0-9 ]', ' ', kw)
        kw = re.sub(r'\s+', ' ', kw).strip()

        if len(kw) < 5 or len(kw) > 120:
            continue
        word_count = len(kw.split())
        if word_count < 2 or word_count > 10:
            continue

        if not any(sig in kw for sig in RISHIKESH_KEYWORD_SIGNALS):
            continue

        if kw not in aggregated:
            aggregated[kw] = {
                "keyword": kw,
                "sources": [],
                "total_score": 0,
                "frequency": 0,
            }

        if item["source"] not in aggregated[kw]["sources"]:
            aggregated[kw]["sources"].append(item["source"])

        aggregated[kw]["total_score"] += item["weight"]
        aggregated[kw]["frequency"] += 1

    results = []
    for kw, data in aggregated.items():
        source_diversity = len(set(data["sources"]))
        final_score = data["total_score"] * (data["frequency"] ** 0.5) * source_diversity
        results.append({
            "keyword": data["keyword"],
            "sources": data["sources"],
            "frequency": data["frequency"],
            "total_score": data["total_score"],
            "final_score": round(final_score, 2),
        })

    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results


def classify_keyword(kw: str) -> str:
    """Classify keyword into category bucket for keywords.json."""
    kw = kw.lower()
    if any(w in kw for w in ["bungee", "bungy", "jump", "scad", "reverse bungee"]):
        return "bungee_jumping"
    elif any(w in kw for w in ["rafting", "white water", "river", "kayak", "marine drive", "shivpuri", "kaudiyala", "brahmpuri"]):
        return "river_rafting"
    elif any(w in kw for w in ["paraglid"]):
        return "paragliding"
    elif any(w in kw for w in ["camping", "camp", "tent"]):
        return "adventure_camping"
    elif any(w in kw for w in ["trek", "hike", "hiking", "trail", "waterfall trek", "kunjapuri"]):
        return "trekking"
    elif any(w in kw for w in ["yoga", "meditation", "ashram", "spiritual", "aarti", "ghat", "temple", "beatles", "wellness"]):
        return "spiritual_cultural"
    elif any(w in kw for w in ["flying fox", "zipline", "zip line", "giant swing", "sky cycling", "rope course"]):
        return "aerial_activities"
    elif any(w in kw for w in ["hot air balloon", "balloon", "air safari"]):
        return "hot_air_balloon"
    elif any(w in kw for w in ["package", "tour", "itinerary", "trip", "weekend", "2 night", "3 day", "combo"]):
        return "tour_packages"
    elif any(w in kw for w in ["how to reach", "nearest airport", "train", "bus", "from delhi", "from mumbai"]):
        return "travel_logistics"
    elif any(w in kw for w in ["price", "cost", "fee", "cheap", "budget", "affordable", "discount"]):
        return "pricing_intent"
    elif any(w in kw for w in ["best time", "season", "weather", "when to visit", "monsoon", "winter", "summer"]):
        return "travel_planning"
    elif any(w in kw for w in ["family", "couple", "honeymoon", "solo", "group", "women", "kids"]):
        return "traveler_type"
    else:
        return "general_rishikesh"


def merge_into_keywords_json(scored_keywords: List[Dict], top_n: int = 150) -> Dict:
    """
    Merge top-N competitor keywords into the existing keywords.json.
    Rules:
    - NEVER remove existing keywords
    - Only ADD new, unique keywords
    - Assign to correct category
    """
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        existing = json.load(f)

    # Build a flat set of all existing keywords for dedup
    existing_flat = set()
    for category_data in existing.values():
        if isinstance(category_data, dict):
            for key, val in category_data.items():
                if key.startswith("_"):
                    continue
                if isinstance(val, list):
                    existing_flat.update([k.lower().strip() for k in val if isinstance(k, str)])
                elif isinstance(val, dict):
                    for sub_val in val.values():
                        if isinstance(sub_val, list):
                            existing_flat.update([k.lower().strip() for k in sub_val if isinstance(k, str)])
        elif isinstance(category_data, list):
            existing_flat.update([k.lower().strip() for k in category_data if isinstance(k, str)])

    print(f"\n  [INFO] Existing keywords in DB: {len(existing_flat)}")

    added_count = 0
    skipped_count = 0
    category_additions: Dict[str, List[str]] = {}

    for item in scored_keywords[:top_n]:
        kw = item["keyword"]
        if kw in existing_flat:
            skipped_count += 1
            continue

        category = classify_keyword(kw)
        if category not in category_additions:
            category_additions[category] = []
        category_additions[category].append(kw)
        existing_flat.add(kw)
        added_count += 1

    # Map category names to existing keywords.json keys
    CATEGORY_MAP = {
        "bungee_jumping":     "bungee_jumping",
        "river_rafting":      "river_rafting",
        "paragliding":        "paragliding",
        "adventure_camping":  "camping",
        "trekking":           "trekking_hiking",
        "spiritual_cultural": "spiritual_cultural",
        "aerial_activities":  "flying_fox_zipline",
        "hot_air_balloon":    "hot_air_balloon",
        "tour_packages":      "multi_activity_combos",
        "travel_logistics":   "travel_planning_rishikesh",
        "pricing_intent":     "bungee_jumping",
        "travel_planning":    "travel_planning_rishikesh",
        "traveler_type":      "solo_travel_rishikesh",
        "general_rishikesh":  "things_to_do_rishikesh",
    }

    for comp_cat, keywords_to_add in category_additions.items():
        target_key = CATEGORY_MAP.get(comp_cat, "things_to_do_rishikesh")

        if target_key not in existing:
            existing[target_key] = {
                "_notes": f"Auto-created from competitor scrape ({comp_cat})",
                "keywords": [],
                "informational": [],
                "commercial_investigation": []
            }

        target = existing[target_key]

        for kw in keywords_to_add:
            if any(w in kw for w in ["price", "cost", "book", "package", "how much", "affordable", "cheap"]):
                sub_key = "commercial_investigation"
            elif any(w in kw for w in ["how", "what", "when", "where", "is", "can", "why", "safe", "best time"]):
                sub_key = "informational"
            else:
                sub_key = "keywords"

            if isinstance(target, dict) and sub_key in target and isinstance(target[sub_key], list):
                target[sub_key].append(kw)
            elif isinstance(target, dict) and "keywords" in target and isinstance(target["keywords"], list):
                target["keywords"].append(kw)
            elif isinstance(target, dict) and "informational" in target and isinstance(target["informational"], list):
                target["informational"].append(kw)

    print(f"  [ADDED] {added_count} new competitor keywords merged")
    print(f"  [SKIPPED] {skipped_count} already-existing keywords")

    return existing


async def main():
    print("=" * 65)
    print("  COMPETITOR KEYWORD SCRAPER - Rishikesh Adventure")
    print("=" * 65)

    all_raw_keywords: List[Dict] = []

    # Phase 1: Scrape all competitor pages
    for site_name, url in COMPETITOR_URLS.items():
        print(f"\n[SCRAPING] {site_name}")
        print(f"   URL: {url}")

        # Try Playwright first, fallback to requests
        html = await scrape_with_playwright(url, site_name)
        if not html:
            html = await scrape_with_requests(url, site_name)

        if html:
            text = extract_text_from_html(html)
            keywords = extract_keywords_from_text(text, site_name)
            print(f"   [EXTRACTED] {len(keywords)} raw keyword signals")
            all_raw_keywords.extend(keywords)
        else:
            print(f"   [SKIP] No content retrieved for {site_name}")

        await asyncio.sleep(2)

    print(f"\n[TOTAL] Raw keyword signals: {len(all_raw_keywords)}")

    # Phase 2: Score and deduplicate
    print("\n[SCORING] Deduplicating and scoring...")
    scored = score_and_deduplicate(all_raw_keywords)
    print(f"   After dedup: {len(scored)} unique keywords")

    # Phase 3: Save raw output
    raw_output = {
        "_meta": {
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sources": list(COMPETITOR_URLS.keys()),
            "total_raw_signals": len(all_raw_keywords),
            "unique_after_dedup": len(scored),
        },
        "top_keywords": scored[:200],
    }
    with open(OUTPUT_RAW, "w", encoding="utf-8") as f:
        json.dump(raw_output, f, indent=2, ensure_ascii=False)
    print(f"\n[SAVED] Raw output -> {OUTPUT_RAW}")

    # Phase 4: Print top 30 keywords
    print("\n[TOP 30] COMPETITOR KEYWORDS (by score):")
    print(f"{'#':<4} {'Score':<8} {'Freq':<6} {'Keyword'}")
    print("-" * 70)
    for i, item in enumerate(scored[:30], 1):
        print(f"{i:<4} {item['final_score']:<8} {item['frequency']:<6} {item['keyword']}")

    # Phase 5: Merge into keywords.json
    print(f"\n[MERGE] Merging into {KEYWORDS_FILE.name}...")
    updated_keywords = merge_into_keywords_json(scored, top_n=150)

    with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_keywords, f, indent=2, ensure_ascii=False)
    print(f"[DONE] keywords.json updated -> {KEYWORDS_FILE}")

    print("\n" + "=" * 65)
    print("  SCRAPE COMPLETE - Review data/competitor_keywords_raw.json")
    print("  for full keyword list with scores and sources.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
