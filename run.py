"""
run.py - Interactive Terminal Control Panel
============================================
Run this file from the project root to get a full interactive menu
for all article generation and social media export operations.

Usage
-----
    python run.py

No API server required. Everything runs directly in the terminal.
"""
from __future__ import annotations

import csv
import logging
import os
import sys
from pathlib import Path

# -- Bootstrap path so imports work from project root --------------------------
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.config import Config
from src.publishers.social_exporter import SocialExporter
from src.publishers.related_article_finder import RelatedArticleFinder

# -- Logging: INFO-level to file, WARNING+ to console so the menu stays clean --
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s - %(message)s",
)
file_handler = logging.FileHandler("run.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
logging.getLogger().addHandler(file_handler)

@logging.LoggerAdapter
class SafeLogger(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return msg.encode('ascii', 'replace').decode('ascii'), kwargs

logger = logging.getLogger(__name__)

# -- Constants ------------------------------------------------------------------
MAX_SAMPLE_ARTICLES = 5     # User confirmed: cap sample runs at 5
DEFAULT_WORKERS     = 3     # User confirmed: default concurrency
BORDER              = "-" * 60


# --------------------------------------------------------------
#  DISPLAY HELPERS
# --------------------------------------------------------------

def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def _header():
    print(f"\n+{BORDER}+")
    print(f"|{'  AI BLOG GENERATOR - CONTROL PANEL':^60}|")
    print(f"|{'  Rishikesh Adventure Tourism Pipeline':^60}|")
    print(f"|{'-' * 60}|")
    print(f"+{BORDER}+\n")


def _section(title: str):
    print(f"  -- {title} {'-' * (54 - len(title))}")


def _ok(msg: str):   print(f"  OK: {msg}")
def _warn(msg: str): print(f"  WARN: {msg}")
def _err(msg: str):  print(f"  ERR: {msg}")
def _info(msg: str): print(f"  INFO: {msg}")


def _platform_status():
    """Show a quick credential status line for each platform."""
    from src.publishers import WordPressPublisher, BloggerPublisher, TumblrPublisher
    wp = WordPressPublisher()
    bl = BloggerPublisher()
    tu = TumblrPublisher()
    icons = {True: "[OK]", False: "[OFF]"}
    print(
        f"  Platform status: "
        f"WordPress {icons[wp.is_configured()]}  "
        f"Blogger {icons[bl.is_configured()]}  "
        f"Tumblr {icons[tu.is_configured()]}\n"
    )


def _print_menu():
    _header()
    _platform_status()

    _section("ARTICLE GENERATION")
    print("  [1]  Generate sample articles         (no publish, max 5)")
    print("  [2]  Generate + Publish -> WordPress")
    print("  [3]  Generate + Publish -> Blogger")
    print("  [4]  Generate + Publish -> Tumblr")
    print("  [5]  Generate + Publish -> ALL platforms")
    print()

    _section("SOCIAL MEDIA EXPORTS  (reads from CSV)")
    print("  [6]  Export LinkedIn JSONs")
    print("  [7]  Export Medium JSONs")
    print("  [8]  Export LinkedIn + Medium JSONs")
    print()

    _section("UTILITIES")
    print("  [9]  Run competitor scraper")
    print("  [10] View CSV database summary")
    print("  [11] !! RESET CSV DATABASE !! (DANGER -- deletes all records)")
    print()
    print("  [0]  Exit")
    print()


# --------------------------------------------------------------
#  INPUT HELPERS
# --------------------------------------------------------------

def _ask_int(prompt: str, min_val: int, max_val: int, default: int) -> int:
    while True:
        raw = input(f"  {prompt} [{default}]: ").strip()
        if raw == "":
            return default
        try:
            val = int(raw)
            if min_val <= val <= max_val:
                return val
            print(f"  Please enter a number between {min_val} and {max_val}.")
        except ValueError:
            print("  Please enter a valid integer.")


def _ask_workers() -> int:
    return _ask_int(
        f"  Max concurrent workers (1-10)",
        min_val=1, max_val=10, default=DEFAULT_WORKERS
    )


def _ask_article_count(label: str = "How many articles to generate", max_val: int = 500) -> int:
    return _ask_int(label, min_val=1, max_val=max_val, default=10)


def _confirm(prompt: str) -> bool:
    return input(f"\n  {prompt} (y/n): ").strip().lower() == "y"


# --------------------------------------------------------------
#  ORCHESTRATOR + CAMPAIGN MANAGER (lazy init)
# --------------------------------------------------------------

_orchestrator = None
_campaign_manager = None


def _get_engine():
    """Lazy-initialise the orchestrator and campaign manager on first use."""
    global _orchestrator, _campaign_manager
    if _orchestrator is None:
        print("\n  [INFO] Initialising pipeline (first time may take a few seconds)...")
        from src.services import BlogGeneratorOrchestrator
        from src.concurrent_manager import ConcurrentCampaignManager
        Config.ensure_directories()
        _orchestrator = BlogGeneratorOrchestrator()
        _campaign_manager = ConcurrentCampaignManager(_orchestrator)
        _ok("Pipeline ready.")
    return _orchestrator, _campaign_manager


# --------------------------------------------------------------
#  OPTION HANDLERS
# --------------------------------------------------------------

def _opt_1_sample():
    """Generate 1-5 sample articles (no publish)."""
    print()
    _info(f"Sample mode - articles are saved locally only (max {MAX_SAMPLE_ARTICLES}).")
    n = _ask_int(
        f"How many sample articles to generate (1-{MAX_SAMPLE_ARTICLES})",
        min_val=1, max_val=MAX_SAMPLE_ARTICLES, default=1
    )
    orch, _ = _get_engine()
    print(f"\n  Generating {n} sample article(s)...\n")
    orch.generate_batch_articles(
        num_articles=n,
        publish_to_wordpress=False,
        publish_to_blogger=False,
        publish_to_tumblr=False,
    )
    _ok(f"Done. Check data/output/json/ for the generated files.")


def _opt_publish(
    label: str,
    publish_wordpress: bool = False,
    publish_blogger: bool = False,
    publish_tumblr: bool = False,
):
    """Shared handler for options 2-5 (generate + publish)."""
    print()
    platforms = []
    if publish_wordpress: platforms.append("WordPress")
    if publish_blogger:   platforms.append("Blogger")
    if publish_tumblr:    platforms.append("Tumblr")
    platform_str = " + ".join(platforms) if platforms else "no platform"

    _info(f"This will generate articles and publish to: {platform_str}")

    # Check credentials
    orch, mgr = _get_engine()
    if publish_wordpress and not orch.wp_publisher.is_configured():
        _warn("WordPress credentials are not configured in .env - skipping WP publish.")
        publish_wordpress = False
    if publish_blogger and not orch.blogger_publisher.is_configured():
        _warn("Blogger credentials are not configured in .env - skipping Blogger publish.")
        publish_blogger = False
    if publish_tumblr and not orch.tumblr_publisher.is_configured():
        _warn("Tumblr credentials are not configured in .env - skipping Tumblr publish.")
        publish_tumblr = False

    n       = _ask_article_count()
    workers = _ask_workers()

    print(f"\n  STARTING campaign: {n} articles | {workers} workers | {platform_str}\n")

    mgr.run_campaign(
        total_articles=n,
        max_workers=workers,
        publish_to_wordpress=publish_wordpress,
        publish_to_blogger=publish_blogger,
        publish_to_tumblr=publish_tumblr,
    )
    _ok("Campaign complete. Check run.log and data/output/ for details.")


def _opt_social_export(do_linkedin: bool, do_medium: bool):
    """Options 6-8: generate social JSON files from CSV."""
    print()
    if do_linkedin and do_medium:
        label = "LinkedIn + Medium"
    elif do_linkedin:
        label = "LinkedIn"
    else:
        label = "Medium"

    _info(f"Reading published articles from CSV and generating {label} JSON files...")

    if not os.path.exists(Config.CSV_PATH):
        _err("articles.csv not found. Run some articles first.")
        return

    # Load published rows
    published = []
    with open(Config.CSV_PATH, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            url = (row.get("wp_published_url") or row.get("url") or "").strip()
            if url:
                published.append(row)

    if not published:
        _warn("No published articles found in CSV. Publish to WordPress first.")
        return

    print(f"  Found {len(published)} published article(s).\n")

    # Load exporters
    Config.ensure_directories()
    exporter = SocialExporter()
    finder   = RelatedArticleFinder(Config.CSV_PATH)
    finder.reload()

    # Import Metadata + ArticleDraft here (heavy, lazy)
    from src.models import ArticleDraft, Metadata

    success = 0
    for i, row in enumerate(published, 1):
        title   = row.get("title", "untitled").strip()
        wp_url  = (row.get("wp_published_url") or row.get("url", "")).strip()
        slug    = row.get("wp_published_slug", "").strip()
        desc    = row.get("short_description", "").strip()
        kw_raw  = row.get("keywords", "")
        keywords = [k.strip() for k in kw_raw.split(",") if k.strip()]

        print(f"  [{i}/{len(published)}] {title[:55]}...")

        try:
            meta = Metadata(
                title=title, description=desc,
                focus_keyword=keywords[0] if keywords else "",
                url_slug=slug, canonical_url=wp_url,
                keywords=keywords, json_ld_schema={},
            )
            article = ArticleDraft(
                title=title,
                content_html=f"<h1>{title}</h1><p>{desc}</p>",
                word_count=0, metadata=meta, faq_section="",
            )
            article.is_published = True
            related = finder.find(title=title, short_description=desc, top_k=3)

            if do_linkedin and do_medium:
                exporter.export(article=article, wp_url=wp_url, wp_slug=slug, related_articles=related)
            elif do_linkedin:
                exporter._export_linkedin(article, wp_url, related, f"export_{slug or str(i)}")
            else:
                exporter._export_medium(article, wp_url, slug, related, f"export_{slug or str(i)}")
            success += 1
        except Exception as exc:
            _err(f"Failed for '{title[:40]}': {exc}")

    print()
    _ok(f"Exported {success}/{len(published)} articles.")
    if do_linkedin:
        _info(f"LinkedIn JSONs -> {Config.SOCIAL_LINKEDIN_DIR}")
    if do_medium:
        _info(f"Medium JSONs   -> {Config.SOCIAL_MEDIUM_DIR}")


def _opt_9_scraper():
    """Run competitor blog scraper."""
    print()
    _info("Starting competitor scraper...")
    orch, _ = _get_engine()
    try:
        orch.run_scraping()
        _ok("Scraping complete. Check data/database/scraped_articles.json.")
    except Exception as exc:
        _err(f"Scraper failed: {exc}")


def _opt_10_csv_summary():
    """Print a human-readable summary of the CSV database."""
    print()
    if not os.path.exists(Config.CSV_PATH):
        _warn("articles.csv not found. Generate some articles first.")
        return

    rows = []
    with open(Config.CSV_PATH, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    if not rows:
        _warn("articles.csv is empty.")
        return

    total       = len(rows)
    published   = sum(1 for r in rows if r.get("article_published") == "yes")
    on_wp       = sum(1 for r in rows if r.get("wp_published_url", "").strip())
    on_blogger  = sum(1 for r in rows if r.get("blogger_published_url", "").strip())
    on_tumblr   = sum(1 for r in rows if r.get("tumblr_published_url", "").strip())

    print(f"\n  {'-'*54}")
    print(f"  {'CSV DATABASE SUMMARY':^54}")
    print(f"  {'-'*54}")
    print(f"  {'Total articles':<30} {total:>10}")
    print(f"  {'Published (any platform)':<30} {published:>10}")
    print(f"  {'Published on WordPress':<30} {on_wp:>10}")
    print(f"  {'Published on Blogger':<30} {on_blogger:>10}")
    print(f"  {'Published on Tumblr':<30} {on_tumblr:>10}")
    print(f"  {'-'*54}")

    # Show last 5 rows
    print(f"\n  Last {min(5, total)} article(s):")
    for row in rows[-5:]:
        platforms = row.get("platforms_published", "-") or "-"
        print(f"    - {row.get('title','')[:45]:<45} [{platforms}]")
    print()


def _opt_11_reset():
    """Reset CSV with double confirmation."""
    print()
    _warn("This will DELETE ALL article records from the CSV database.")
    _warn("This action CANNOT be undone.")
    print()

    c1 = input("  First confirmation  - type  YES  to continue: ").strip()
    if c1 != "YES":
        _info("Reset cancelled.")
        return

    c2 = input("  Second confirmation - type  DELETE  to confirm: ").strip()
    if c2 != "DELETE":
        _info("Reset cancelled.")
        return

    from utils.utils import CSVManager
    mgr = CSVManager()
    mgr.reset_csv()
    _ok("CSV has been reset to headers only. All article records deleted.")


# --------------------------------------------------------------
#  MAIN LOOP
# --------------------------------------------------------------

def main():
    Config.ensure_directories()

    while True:
        _clear()
        _print_menu()

        choice = input("  Enter your choice: ").strip()

        if choice == "0":
            print("\n  Goodbye!\n")
            break

        elif choice == "1":
            _opt_1_sample()

        elif choice == "2":
            _opt_publish("WordPress", publish_wordpress=True)

        elif choice == "3":
            _opt_publish("Blogger", publish_blogger=True)

        elif choice == "4":
            _opt_publish("Tumblr", publish_tumblr=True)

        elif choice == "5":
            _opt_publish("ALL", publish_wordpress=True, publish_blogger=True, publish_tumblr=True)

        elif choice == "6":
            _opt_social_export(do_linkedin=True, do_medium=False)

        elif choice == "7":
            _opt_social_export(do_linkedin=False, do_medium=True)

        elif choice == "8":
            _opt_social_export(do_linkedin=True, do_medium=True)

        elif choice == "9":
            _opt_9_scraper()

        elif choice == "10":
            _opt_10_csv_summary()

        elif choice == "11":
            _opt_11_reset()

        else:
            _err("Invalid choice. Please enter a number from the menu.")

        input("\n  Press Enter to return to the menu...")


if __name__ == "__main__":
    main()
