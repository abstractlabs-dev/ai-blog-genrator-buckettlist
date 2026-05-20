"""
Database Reset Script
Clears ALL generated content databases (articles.csv, used_titles.csv, Weaviate vector store,
output JSON, output images) while preserving stats.json.

Run inside the container:
  docker exec blog-generator-api python /app/api/reset_database.py
"""
import os
import sys
import csv
import shutil
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = "/app/data"
DATABASE_DIR = os.path.join(BASE_DIR, "database")
OUTPUT_JSON_DIR = os.path.join(BASE_DIR, "output", "json")
OUTPUT_IMAGES_DIR = os.path.join(BASE_DIR, "output", "images")
OUTPUT_BRAND_DIR = os.path.join(BASE_DIR, "output", "brand")
OUTPUT_SOCIAL_DIR = os.path.join(BASE_DIR, "output", "social")

ARTICLES_CSV   = os.path.join(DATABASE_DIR, "articles.csv")
USED_TITLES_CSV = os.path.join(DATABASE_DIR, "used_titles.csv")
STATS_JSON      = os.path.join(DATABASE_DIR, "stats.json")  # PRESERVE THIS

# ── Weaviate ───────────────────────────────────────────────────────────────────
WEAVIATE_URL = "http://weaviate:8080"
WEAVIATE_COLLECTION = "ArticleChunk"


def reset_articles_csv():
    """Reset articles.csv to header-only (no data rows)."""
    headers = [
        "id", "article_id", "date", "title", "url", "wp_post_id",
        "wp_published_slug", "wp_published_url", "blogger_url",
        "tumblr_url", "description", "keywords", "product_name", "published"
    ]
    with open(ARTICLES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
    logger.info("✅ articles.csv reset to header-only.")


def reset_used_titles_csv():
    """Reset used_titles.csv to an empty file."""
    with open(USED_TITLES_CSV, "w", encoding="utf-8") as f:
        f.write("")
    logger.info("✅ used_titles.csv cleared.")


def clear_output_directory(directory: str, label: str):
    """Remove all files inside a directory but keep the directory itself."""
    if not os.path.exists(directory):
        logger.info("⚠️  %s directory not found, skipping.", label)
        return
    removed = 0
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
                removed += 1
            elif os.path.isdir(filepath):
                shutil.rmtree(filepath)
                removed += 1
        except Exception as e:
            logger.warning("Could not remove %s: %s", filepath, e)
    logger.info("✅ %s cleared — removed %d items.", label, removed)


def reset_weaviate():
    """Delete and recreate the ArticleChunk collection in Weaviate."""
    # Step 1: Check if collection exists
    try:
        resp = requests.get(f"{WEAVIATE_URL}/v1/schema/{WEAVIATE_COLLECTION}", timeout=10)
        if resp.status_code == 404:
            logger.info("⚠️  Weaviate collection '%s' does not exist — nothing to delete.", WEAVIATE_COLLECTION)
            return
        elif resp.status_code != 200:
            logger.warning("Weaviate schema check returned %s — skipping vector reset.", resp.status_code)
            return
    except Exception as e:
        logger.warning("Could not reach Weaviate at %s: %s — skipping vector reset.", WEAVIATE_URL, e)
        return

    # Step 2: Delete the collection
    try:
        del_resp = requests.delete(f"{WEAVIATE_URL}/v1/schema/{WEAVIATE_COLLECTION}", timeout=15)
        if del_resp.status_code in (200, 204):
            logger.info("✅ Weaviate collection '%s' deleted.", WEAVIATE_COLLECTION)
        else:
            logger.warning("Weaviate delete returned %s: %s", del_resp.status_code, del_resp.text[:200])
            return
    except Exception as e:
        logger.error("Failed to delete Weaviate collection: %s", e)
        return

    # Step 3: Recreate the collection with the same schema
    schema = {
        "class": WEAVIATE_COLLECTION,
        "vectorizer": "none",
        "properties": [
            {"name": "article_id",   "dataType": ["text"]},
            {"name": "chunk_index",  "dataType": ["int"]},
            {"name": "content",      "dataType": ["text"]},
            {"name": "title",        "dataType": ["text"]},
            {"name": "keywords",     "dataType": ["text"]},
        ]
    }
    try:
        create_resp = requests.post(
            f"{WEAVIATE_URL}/v1/schema",
            json=schema,
            timeout=15
        )
        if create_resp.status_code in (200, 201):
            logger.info("✅ Weaviate collection '%s' recreated (empty).", WEAVIATE_COLLECTION)
        else:
            logger.warning("Weaviate recreate returned %s: %s", create_resp.status_code, create_resp.text[:300])
    except Exception as e:
        logger.error("Failed to recreate Weaviate collection: %s", e)


def verify_stats_preserved():
    """Confirm stats.json was NOT touched."""
    if os.path.exists(STATS_JSON):
        import json
        with open(STATS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("✅ stats.json preserved: %s", data)
    else:
        logger.warning("⚠️  stats.json not found — it was never created or was accidentally removed.")


def main():
    print("\n" + "=" * 60)
    print("  DATABASE RESET — Cleaning all article data")
    print("  stats.json will be PRESERVED")
    print("=" * 60 + "\n")

    # 1. Reset CSV databases
    reset_articles_csv()
    reset_used_titles_csv()

    # 2. Clear output directories
    clear_output_directory(OUTPUT_JSON_DIR,   "Output JSON")
    clear_output_directory(OUTPUT_IMAGES_DIR, "Output Images")
    clear_output_directory(OUTPUT_BRAND_DIR,  "Output Brand")
    clear_output_directory(OUTPUT_SOCIAL_DIR, "Output Social")

    # 3. Reset Weaviate vector store
    reset_weaviate()

    # 4. Verify stats.json is intact
    verify_stats_preserved()

    print("\n" + "=" * 60)
    print("  ✅ DATABASE RESET COMPLETE")
    print("  All article data cleared. stats.json preserved.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
