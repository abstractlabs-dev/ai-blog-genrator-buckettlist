"""
generate_social_exports.py
==========================
Standalone script to generate LinkedIn + Medium JSON files for ALL articles
that are already published in articles.csv (have a wp_published_url).

Use this if you:
  - Already have articles published on WordPress from a previous run
  - Want to retroactively create LinkedIn/Medium posts for them
  - Want to regenerate social exports after updating the SocialExporter

Usage
-----
    python generate_social_exports.py

Output
------
    data/output/social/linkedin/YYYY-MM-DD_<slug>.json
    data/output/social/medium/YYYY-MM-DD_<slug>.json

One JSON pair per published article in the CSV.
"""
import sys
import os
import csv
import logging
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.config import Config
from src.models import ArticleDraft, Metadata
from src.publishers.social_exporter import SocialExporter
from src.publishers.related_article_finder import RelatedArticleFinder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _load_published_articles() -> list[dict]:
    """Read all rows from articles.csv that have a wp_published_url."""
    path = Config.CSV_PATH
    if not os.path.exists(path):
        logger.error("articles.csv not found at %s", path)
        return []

    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            url = (row.get("wp_published_url") or row.get("url") or "").strip()
            if url:
                rows.append(row)

    logger.info("Found %d published article(s) in CSV.", len(rows))
    return rows


def _make_mock_article(row: dict) -> ArticleDraft:
    """
    Build a minimal ArticleDraft from a CSV row so we can feed it to SocialExporter.
    We don't have the full HTML anymore (it was already published), so we use the
    title + description to generate the LinkedIn commentary.
    """
    title       = row.get("title", "").strip()
    description = row.get("short_description", "").strip()
    keywords_raw = row.get("keywords", "")
    keywords    = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    slug        = (row.get("wp_published_slug") or row.get("url", "").rstrip("/").split("/")[-1]).strip()
    wp_url      = (row.get("wp_published_url") or row.get("url", "")).strip()

    meta = Metadata(
        title=title,
        description=description,
        focus_keyword=keywords[0] if keywords else "",
        url_slug=slug,
        canonical_url=wp_url,
        keywords=keywords,
        json_ld_schema={},
    )

    article = ArticleDraft(
        title=title,
        content_html=f"<h1>{title}</h1><p>{description}</p>",
        word_count=0,
        metadata=meta,
        faq_section="",
    )
    article.is_published = True
    return article


def main():
    Config.ensure_directories()

    rows = _load_published_articles()
    if not rows:
        print("\n⚠️  No published articles found in articles.csv.")
        print("   Run a campaign first to publish articles to WordPress.\n")
        return

    exporter = SocialExporter()
    finder   = RelatedArticleFinder(Config.CSV_PATH)
    finder.reload()  # Load full corpus once

    success = 0
    for i, row in enumerate(rows, 1):
        title  = row.get("title", "untitled")
        wp_url = (row.get("wp_published_url") or row.get("url", "")).strip()
        slug   = (row.get("wp_published_slug") or "").strip()

        logger.info("[%d/%d] Exporting: %s", i, len(rows), title)

        try:
            article = _make_mock_article(row)
            related = finder.find(
                title=title,
                short_description=row.get("short_description", ""),
                top_k=3,
            )
            paths = exporter.export(
                article=article,
                wp_url=wp_url,
                wp_slug=slug,
                related_articles=related,
            )
            logger.info(
                "  ✅ LinkedIn: %s",
                os.path.basename(paths["linkedin_path"])
            )
            logger.info(
                "  ✅ Medium:   %s",
                os.path.basename(paths["medium_path"])
            )
            success += 1
        except Exception as exc:
            logger.error("  ❌ Failed for '%s': %s", title, exc)

    print(f"\n{'='*55}")
    print(f"  Social Export Complete: {success}/{len(rows)} articles exported")
    print(f"  LinkedIn → {Config.SOCIAL_LINKEDIN_DIR}")
    print(f"  Medium   → {Config.SOCIAL_MEDIUM_DIR}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
