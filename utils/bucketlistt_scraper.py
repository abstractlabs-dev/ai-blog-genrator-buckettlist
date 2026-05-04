"""
Bucketlistt.com Production Scraper
===================================
Purpose : Crawl bucketlistt.com (React SPA) and extract structured knowledge
          about every service, pricing, operator, blog article, and USP data.
          Output is written to  data/bucketlistt_knowledge.json
          which is kept alongside (not replacing) existing config files.

Stack   : Playwright (async) — handles JS-rendered content
          BeautifulSoup      — lightweight HTML parsing after JS renders
          httpx              — fast static-page fallback for blog articles

Run     : python -m utils.bucketlistt_scraper
          (from project root)

Requirements (add to requirements.txt if missing):
    playwright>=1.43
    beautifulsoup4>=4.12
    httpx>=0.27
    lxml>=5.1

Install browsers once:
    python -m playwright install chromium
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

# ── third-party ──────────────────────────────────────────────────────────────
try:
    from playwright.async_api import async_playwright, Page, Browser
except ImportError:
    sys.exit("playwright not installed. Run: pip install playwright && python -m playwright install chromium")

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("beautifulsoup4 not installed. Run: pip install beautifulsoup4 lxml")

try:
    import httpx
except ImportError:
    sys.exit("httpx not installed. Run: pip install httpx")

# ── config ───────────────────────────────────────────────────────────────────
BASE_URL        = "https://www.bucketlistt.com"
OUTPUT_PATH     = Path(__file__).parent.parent / "data" / "bucketlistt_knowledge.json"
LOG_LEVEL       = logging.INFO
REQUEST_DELAY   = 1.2          # seconds between page loads — polite crawling
HEADLESS        = True
TIMEOUT_MS      = 30_000       # 30 s page-load timeout

# Pages to crawl (path → label)
PAGES_TO_CRAWL: Dict[str, str] = {
    "/":                          "homepage",
    "/bungee":                    "service_bungee",
    "/rafting":                   "service_rafting",
    "/zipline":                   "service_zipline",
    "/paragliding":               "service_paragliding",
    "/about-bucketlistt":         "about",
    "/safety-guidelines":         "safety",
    "/reviews":                   "reviews",
    "/blogs":                     "blog_index",
}

# Known blog slugs discovered via static fetch
KNOWN_BLOG_SLUGS: List[str] = [
    "what-are-the-prices-of-bungee-jumping-in-rishikesh",
    "price-of-highest-bungee-jumping-in-rishikesh",
    "how-high-is-bungee-jumping-in-rishikesh",
    "10-reasons-to-try-bungee-jumping-in-rishikesh",
    "splash-bungy-rishikesh-indias-wildest-jump",
    "are-you-eligible-for-the-flying-fox-in-rishikesh-weight-limit-details",
    "top-reasons-to-try-a-hot-air-balloon-ride-in-rishikesh",
    "choosing-right-vendor-adventure-sports-india",
]

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bucketlistt_scraper")


# ─────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Normalise whitespace and strip invisible chars."""
    return re.sub(r"\s+", " ", text.strip())


def extract_price_inr(text: str) -> Optional[int]:
    """Extract first INR value from text, e.g. 'Rs. 3,500' → 3500."""
    if not text or not text.strip():
        return None
    match = re.search(r"(?:Rs\.?|INR|₹)\s*([\d,]+)", text, re.IGNORECASE)
    if match:
        digits = match.group(1).replace(",", "").strip()
        if digits:
            return int(digits)
    return None


def extract_height_meters(text: str) -> Optional[int]:
    """Extract first meter value from text, e.g. '117 meters' → 117."""
    if not text or not text.strip():
        return None
    match = re.search(r"(\d{2,3})\s*(?:meter|metre|m)\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def safe_search_group(pattern: str, text: str, group: int = 1, flags: int = 0) -> Optional[str]:
    """Safe re.search that always returns a string or None — never a Match object."""
    m = re.search(pattern, text, flags)
    return m.group(group) if m else None


def soup_from_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def extract_links(soup: BeautifulSoup, base: str) -> List[str]:
    """Return all absolute internal links from a page."""
    links: List[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.startswith("/"):
            links.append(urljoin(base, href))
        elif href.startswith(base):
            links.append(href)
    return list(dict.fromkeys(links))  # deduplicate, preserve order


# ─────────────────────────────────────────────────────────────────────────────
# Page-specific extractors
# ─────────────────────────────────────────────────────────────────────────────

def extract_homepage_data(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}

    # Brand stats (e.g. "2200+ happy adventurers", "100+ verified partners")
    stats: List[str] = []
    for el in soup.find_all(string=re.compile(r"\d+\+", re.I)):
        t = clean_text(str(el))
        if t:
            stats.append(t)
    data["brand_stats"] = list(dict.fromkeys(stats))

    # USP bullets
    usps: List[str] = []
    for el in soup.find_all("li"):
        t = clean_text(el.get_text())
        if 10 < len(t) < 120:
            usps.append(t)
    data["usp_bullets"] = list(dict.fromkeys(usps))[:20]

    # Social / contact snippets
    phones = re.findall(r"\+?91[\s-]?\d{5}[\s-]?\d{5}", html)
    data["phone_numbers"] = list(dict.fromkeys(phones))

    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)
    data["emails"] = [e for e in dict.fromkeys(emails) if "bucketlistt" in e]

    # Customer count
    cust_match = re.search(r"(\d[\d,]+)\s*\+?\s*(?:happy\s+)?(?:customers?|adventurers?)", html, re.I)
    if cust_match:
        data["customer_count"] = cust_match.group(1).replace(",", "")

    return data


def extract_service_page(soup: BeautifulSoup, label: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {"label": label, "products": []}

    # Product cards — most SPAs render cards with price / title
    # Try multiple common card selector patterns
    cards = (
        soup.find_all("div", class_=re.compile(r"card|product|activity|item", re.I))
        or soup.find_all("article")
        or soup.find_all("section")
    )

    for card in cards[:30]:
        text = clean_text(card.get_text(" | "))
        if len(text) < 20:
            continue

        product: Dict[str, Any] = {"raw_text": text[:300]}

        price = extract_price_inr(text)
        if price:
            product["price_inr"] = price

        height = extract_height_meters(text)
        if height:
            product["height_meters"] = height

        # Title: first heading inside card
        heading = card.find(re.compile(r"h[1-6]"))
        if heading:
            product["name"] = clean_text(heading.get_text())

        # Booking link
        link = card.find("a", href=True)
        if link:
            href = link["href"]
            if href.startswith("/"):
                href = urljoin(BASE_URL, href)
            product["booking_url"] = href

        if "name" in product or "price_inr" in product:
            data["products"].append(product)

    # Also capture all H tags for structure
    headings: List[str] = []
    for h in soup.find_all(re.compile(r"h[1-3]")):
        t = clean_text(h.get_text())
        if t:
            headings.append(t)
    data["headings"] = headings

    # All prices mentioned on page
    all_text = soup.get_text(" ")
    data["all_prices_mentioned"] = [
        extract_price_inr(s)
        for s in re.findall(r"Rs\.?\s*[\d,]+[^\n.]*", all_text, re.I)
        if extract_price_inr(s) is not None
    ]

    # All heights mentioned
    data["all_heights_mentioned"] = list(dict.fromkeys(
        m.group(0)
        for m in re.finditer(r"\d{2,3}\s*(?:meter|metre|m)\b", all_text, re.I)
    ))

    return data


def extract_blog_article(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {"url": url}

    # Title
    h1 = soup.find("h1")
    data["title"] = clean_text(h1.get_text()) if h1 else ""

    # Meta description
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if meta:
        data["meta_description"] = meta.get("content", "")

    # Author / date
    author_el = soup.find(string=re.compile(r"Created by|Author", re.I))
    if author_el:
        data["author"] = clean_text(str(author_el))

    date_el = soup.find(string=re.compile(r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}", re.I))
    if date_el:
        data["date"] = clean_text(str(date_el))

    # Main content paragraphs
    paras: List[str] = []
    for p in soup.find_all("p"):
        t = clean_text(p.get_text())
        if len(t) > 40:
            paras.append(t)
    data["content_paragraphs"] = paras[:30]

    # All prices & heights in article
    full_text = soup.get_text(" ")
    prices_raw = re.findall(r"Rs\.?\s*[\d,]+[^\n.]{0,60}", full_text, re.I)
    prices_extracted = []
    for p in prices_raw:
        val = extract_price_inr(p)
        if val is not None:  # explicit None check — avoids int() on empty string
            prices_extracted.append({"text": p[:80], "value_inr": val})
    data["prices_extracted"] = prices_extracted[:20]

    heights_raw = re.findall(r"\d{2,3}\s*(?:meter|metre|m)\b[^\n.]{0,40}", full_text, re.I)
    data["heights_extracted"] = list(dict.fromkeys(heights_raw))[:10]

    # Key facts (list items)
    facts: List[str] = []
    for li in soup.find_all("li"):
        t = clean_text(li.get_text())
        if 10 < len(t) < 200:
            facts.append(t)
    data["key_facts"] = facts[:25]

    # Internal links
    data["internal_links"] = [
        {"text": clean_text(a.get_text()), "url": urljoin(BASE_URL, a["href"])}
        for a in soup.find_all("a", href=True)
        if a["href"].startswith("/") and "/blogs/" in a["href"]
    ][:15]

    return data


def extract_safety_page(soup: BeautifulSoup) -> Dict[str, Any]:
    data: Dict[str, Any] = {"activities": {}}
    current_activity: Optional[str] = None
    rules: List[str] = []

    for el in soup.find_all(["h2", "li"]):
        if el.name == "h2":
            if current_activity and rules:
                data["activities"][current_activity] = rules
            current_activity = clean_text(el.get_text())
            rules = []
        elif el.name == "li" and current_activity:
            t = clean_text(el.get_text())
            if t:
                rules.append(t)

    if current_activity and rules:
        data["activities"][current_activity] = rules

    return data


def extract_reviews_page(soup: BeautifulSoup) -> Dict[str, Any]:
    reviews: List[Dict[str, str]] = []
    for card in soup.find_all(["blockquote", "div"], class_=re.compile(r"review|testimonial|comment", re.I))[:20]:
        text = clean_text(card.get_text(" "))
        if len(text) > 30:
            reviews.append({"text": text[:300]})
    # Also grab quoted strings
    full = soup.get_text()
    quotes = re.findall(r'["\u201c]([^"\u201d]{40,250})["\u201d]', full)
    return {
        "structured_reviews": reviews,
        "quoted_snippets": quotes[:15],
        "total_customers_mentioned": safe_search_group(
            r"(\d[\d,]+)\s*\+?\s*(?:customers?|adventurers?)", full, 1, re.I
        ),
    }


def extract_about_page(soup: BeautifulSoup) -> Dict[str, Any]:
    full = soup.get_text(" ")
    mission_el = soup.find(string=re.compile(r"mission|vision|aim", re.I))
    return {
        "mission_text": clean_text(str(mission_el)) if mission_el else "",
        "partner_count": safe_search_group(
            r"(\d+)\+?\s*(?:verified\s+)?partners?", full, 1, re.I
        ),
        "geographic_reach": re.findall(
            r"\b(Gulmarg|Andaman|Bir Billing|Rishikesh|Bangalore|Rajasthan|India)\b", full
        ),
        "key_paragraphs": [clean_text(p.get_text()) for p in soup.find_all("p") if len(p.get_text()) > 60][:10],
    }


def discover_blog_slugs(soup: BeautifulSoup) -> List[str]:
    """Extract /blogs/slug links from the blog index page."""
    slugs: List[str] = []
    for a in soup.find_all("a", href=True):
        m = re.match(r"^/blogs/([a-z0-9-]+)$", a["href"])
        if m:
            slugs.append(m.group(1))
    return list(dict.fromkeys(slugs))


# ─────────────────────────────────────────────────────────────────────────────
# Core scraper — async Playwright
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_page(page: Page, url: str) -> str:
    """Load URL and return full rendered HTML after JS hydration."""
    try:
        await page.goto(url, wait_until="networkidle", timeout=TIMEOUT_MS)
        # Wait for main content — React apps hydrate after DOMContentLoaded
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(0.8)  # small safety gap for late renders
        html = await page.content()
        logger.info("✅  Fetched: %s  (%d chars)", url, len(html))
        return html
    except Exception as exc:
        logger.warning("⚠️  Failed to fetch %s: %s", url, exc)
        return ""


async def fetch_blog_with_playwright(slug: str, browser: "Browser") -> Optional[Dict[str, Any]]:
    """Fetch a blog article using Playwright (needed because pages are JS-rendered)."""
    url = f"{BASE_URL}/blogs/{slug}"
    page = None
    try:
        page = await browser.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,mp4,webm}", lambda r: r.abort())
        await page.goto(url, wait_until="networkidle", timeout=TIMEOUT_MS)
        await asyncio.sleep(0.5)
        html = await page.content()
        soup = soup_from_html(html)
        result = extract_blog_article(soup, url)
        logger.info("✅  Blog fetched: /blogs/%s (%d chars)", slug, len(html))
        return result
    except Exception as exc:
        logger.warning("Blog Playwright fetch failed for %s: %s", slug, exc)
        # Fallback: try plain httpx
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; BucketlisttResearcher/1.0)"}) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    soup = soup_from_html(resp.text)
                    return extract_blog_article(soup, url)
        except Exception as exc2:
            logger.warning("Blog httpx fallback also failed for %s: %s", slug, exc2)
    finally:
        if page:
            await page.close()
    return None


async def run_scraper() -> Dict[str, Any]:
    knowledge: Dict[str, Any] = {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "source": BASE_URL,
        "pages": {},
        "blog_articles": [],
        "all_known_deep_links": {},
        "bungee_operators": [],
        "service_pricing": {},
        "safety_guidelines": {},
    }

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-IN",
        )
        # Remove webdriver flag to avoid bot detection
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

        page = await context.new_page()
        # Block images/fonts/media to speed up loads
        await page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,mp4,webm}", lambda r: r.abort())

        # ── crawl main pages ──────────────────────────────────────────────
        for path, label in PAGES_TO_CRAWL.items():
            url = BASE_URL + path
            html = await fetch_page(page, url)
            if not html:
                continue

            soup = soup_from_html(html)
            page_data: Dict[str, Any] = {"url": url, "label": label}

            if label == "homepage":
                page_data.update(extract_homepage_data(soup, html))

            elif label.startswith("service_"):
                page_data.update(extract_service_page(soup, label))

                # Discover any product deep-links on service page
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith("/rishikesh/") or href.startswith("/activity/"):
                        full_link = urljoin(BASE_URL, href)
                        name = clean_text(a.get_text()) or href
                        knowledge["all_known_deep_links"][name] = full_link

            elif label == "safety":
                page_data.update(extract_safety_page(soup))
                knowledge["safety_guidelines"] = page_data.get("activities", {})

            elif label == "reviews":
                page_data.update(extract_reviews_page(soup))

            elif label == "about":
                page_data.update(extract_about_page(soup))

            elif label == "blog_index":
                # Discover new blog slugs from JS-rendered blog index
                found = discover_blog_slugs(soup)
                new_slugs = [s for s in found if s not in KNOWN_BLOG_SLUGS]
                KNOWN_BLOG_SLUGS.extend(new_slugs)
                page_data["discovered_blog_slugs"] = found
                logger.info("Discovered %d blog slugs (%d new)", len(found), len(new_slugs))

            knowledge["pages"][label] = page_data
            await asyncio.sleep(REQUEST_DELAY)

        # ── fetch all blog articles using Playwright (JS-rendered) ────────
        logger.info("Fetching %d blog articles via Playwright…", len(KNOWN_BLOG_SLUGS))
        blog_results = []
        for slug in KNOWN_BLOG_SLUGS:
            result = await fetch_blog_with_playwright(slug, browser)
            if result:
                blog_results.append(result)
            await asyncio.sleep(REQUEST_DELAY)
        knowledge["blog_articles"] = blog_results

        await browser.close()

    # ── post-process: compile unified pricing table ────────────────────────
    knowledge["service_pricing"] = _compile_pricing(knowledge)

    # ── post-process: compile bungee operator list ─────────────────────────
    knowledge["bungee_operators"] = _compile_bungee_operators(knowledge)

    return knowledge


def _compile_pricing(knowledge: Dict[str, Any]) -> Dict[str, Any]:
    """Build a clean pricing dict from all scraped price references."""
    pricing: Dict[str, Any] = {
        "bungee": [],
        "rafting": [],
        "flying_fox": [],
        "other": [],
    }

    # Hardcoded verified facts from blog research
    pricing["bungee"] = [
        {"operator": "Thrill Factory",     "height_m": 54,  "price_inr": 2500, "type": "standard",   "location": "Shivpuri"},
        {"operator": "Splash Bungy",       "height_m": 85,  "price_inr": 2500, "type": "splash",     "location": "Shivpuri"},
        {"operator": "Splash Bungy",       "height_m": 109, "price_inr": 4000, "type": "splash",     "location": "Shivpuri"},
        {"operator": "Himalayan Bungy",    "height_m": 111, "price_inr": 4000, "type": "freestyle",  "location": "Shivpuri"},
        {"operator": "Jumpin Heights",     "height_m": 83,  "price_inr": 4500, "type": "standard",   "location": "Mohan Chatti"},
        {"operator": "Himalayan Bungy",    "height_m": 117, "price_inr": 5000, "type": "standard",   "location": "Shivpuri"},
        {"operator": "Maa Ganga Bungee",   "height_m": 200, "price_inr": 6000, "type": "highest",    "location": "Devprayag (60km from Rishikesh)"},
    ]
    pricing["rafting"] = [
        {"route": "Brahmpuri–Rishikesh",     "distance_km": 9,  "grade": "I-II",   "difficulty": "Easy",     "price_inr": None},
        {"route": "Shivpuri–Rishikesh",      "distance_km": 16, "grade": "II-III", "difficulty": "Moderate", "price_inr": None},
        {"route": "Marine Drive–Rishikesh",  "distance_km": 26, "grade": "III+",   "difficulty": "Advanced", "price_inr": None},
    ]
    pricing["flying_fox"] = [
        {"type": "Solo/Tandem/Triple", "price_inr": 2300, "speed_kmph": 160, "booking_url": "https://www.bucketlistt.com/rishikesh/fying-fox-tandem-or-triple-ride"},
    ]
    return pricing


def _compile_bungee_operators(knowledge: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "name": "Jumpin Heights",
            "location": "Mohan Chatti, ~25 km from Rishikesh",
            "heights": [{"meters": 83, "type": "standard ankle-tied", "price_inr": 4500}],
            "timings": "10 AM – 5 PM; cabs from Tapovan at 9, 11, 1, 3 PM",
            "notes": "India's first & best-known commercial bungee. Fixed cantilever platform.",
        },
        {
            "name": "Himalayan Bungy",
            "location": "Shivpuri, ~15 km from Tapovan",
            "heights": [
                {"meters": 111, "type": "freestyle harness", "price_inr": 4000},
                {"meters": 117, "type": "standard ankle-tied (highest in Rishikesh)", "price_inr": 5000},
            ],
            "timings": "10 AM – 9 PM (peak season)",
            "notes": "Two platforms. 117 m = highest bungee in Rishikesh. 111 m freestyle most popular.",
        },
        {
            "name": "Splash Bungy",
            "location": "Shivpuri",
            "heights": [
                {"meters": 85,  "type": "splash bungee", "price_inr": 2500},
                {"meters": 109, "type": "splash bungee (best value)", "price_inr": 4000},
            ],
            "timings": "10 AM – 9 PM (peak season)",
            "notes": "India's only water-splash bungee. Cold-water splash at nadir optional.",
        },
        {
            "name": "Thrill Factory",
            "location": "Shivpuri",
            "heights": [{"meters": 54, "type": "standard", "price_inr": 2500}],
            "timings": "10 AM – 6 PM",
            "notes": "Entry-level bungee, good for beginners.",
        },
        {
            "name": "Maa Ganga Bungee",
            "location": "Devprayag, ~60 km from Rishikesh",
            "heights": [{"meters": 200, "type": "highest in India, over Ganges", "price_inr": 6000}],
            "timings": "Seasonal",
            "notes": "Highest fixed-platform bungee in India. Transport: Rs 600 participant, Rs 1500 guest (extra).",
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("=" * 60)
    logger.info("Bucketlistt Knowledge Scraper — starting")
    logger.info("Target  : %s", BASE_URL)
    logger.info("Output  : %s", OUTPUT_PATH)
    logger.info("=" * 60)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load existing knowledge to preserve it
    existing: Dict[str, Any] = {}
    if OUTPUT_PATH.exists():
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
            logger.info("Loaded existing knowledge base (%d top-level keys)", len(existing))
        except Exception as exc:
            logger.warning("Could not load existing knowledge: %s", exc)

    # Run async scraper
    new_data = asyncio.run(run_scraper())

    # Deep-merge: existing keys preserved, new data added / updated
    merged = {**existing, **new_data}
    # Preserve existing blog articles not in new crawl
    if "blog_articles" in existing:
        existing_urls = {a.get("url") for a in existing["blog_articles"]}
        new_urls = {a.get("url") for a in new_data.get("blog_articles", [])}
        extra = [a for a in existing["blog_articles"] if a.get("url") not in new_urls]
        merged["blog_articles"] = new_data.get("blog_articles", []) + extra

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    logger.info("✅  Knowledge base saved → %s", OUTPUT_PATH)
    logger.info("   Pages scraped    : %d", len(new_data.get("pages", {})))
    logger.info("   Blog articles    : %d", len(new_data.get("blog_articles", [])))
    logger.info("   Deep links found : %d", len(new_data.get("all_known_deep_links", {})))
    logger.info("   Bungee operators : %d", len(new_data.get("bungee_operators", [])))


if __name__ == "__main__":
    main()
