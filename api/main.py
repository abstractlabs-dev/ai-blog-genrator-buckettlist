"""FastAPI application for the Blog Generator system.

This app exposes endpoints for:
- Batch article generation with 25/75 brand/generic split
- Concurrent campaign generation
- Concurrent campaign generation with Auto-Publish to WordPress
- Competitor blog scraping
"""
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
import faulthandler
import csv
import re
import json
import hashlib
import threading

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv

from src.config import Config
from src.services import BlogGeneratorOrchestrator
from src.concurrent_manager import ConcurrentCampaignManager
from src.stats_manager import StatsManager
from src.services.email_service import EmailService
from api.models import (
    ScrapeResponse,
    CampaignRequest,
    CampaignResponse,
    BatchArticleRequest,
    BatchArticleResponse,
    verify_api_key
)

# Enable crash reporting for C-level errors (segfaults, aborts)
faulthandler.enable()

# Add the project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# Load environment variables from .env before reading Config
load_dotenv()


class AppState:
    """Application state container to avoid global variables."""
    orchestrator = None
    campaign_manager = None


app = FastAPI(
    title="Blog Generator API",
    description="API for generating blog articles, running campaigns, and scraping competitor blogs.",
    version="2.1.0"
)


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    try:
        Config.ensure_directories()
        Config.validate_api_key()
        AppState.orchestrator = BlogGeneratorOrchestrator()
        AppState.campaign_manager = ConcurrentCampaignManager(AppState.orchestrator)
        logger.info("[STARTUP] Blog services successfully initialized in worker process.")
    except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
        logger.error("[STARTUP_FAILED] Failed to initialize blog services: %s", e, exc_info=True)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Blog Generator API",
        "version": "2.1.0",
        "endpoints": {
            "/health": "Health check endpoint",
            "/article/batch": "Generate batch of articles with 25/75 brand/generic split - requires API key",
            "/campaign/run": "Run concurrent article generation campaign (Generate Only) - requires API key",
            "/campaign/publish": "Run concurrent generation & Publish to WordPress - requires API key",
            "/campaign/publish/blogger": (
                "Run concurrent generation & Publish to Blogger (No Images) - requires API key"
            ),
            "/campaign/publish/tumblr": "Run concurrent generation & Publish to Tumblr (No Images) - requires API key",
            "/campaign/publish/linkedin": (
                "Run concurrent generation & Generate LinkedIn payloads (Auto-emails in sets of 3) - requires API key"
            ),
            "/campaign/publish/medium": (
                "Run concurrent generation & Generate Medium payloads (Auto-emails in sets of 3) - requires API key"
            ),
            "/scraper/run": "Run competitor blog scraper",
        },
        "authentication": "Use X-API-Key header for protected endpoints"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.websocket("/api/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket endpoint for real-time status updates."""
    await websocket.accept()
    try:
        await websocket.send_json({
            "status": "connected",
            "timestamp": datetime.now().isoformat(),
            "message": "WebSocket connection established"
        })

        while True:
            try:
                _ = await websocket.receive_text()
                await websocket.send_json({
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat()
                })
            except WebSocketDisconnect:
                break
    except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
        logger.error("WebSocket error: %s", e)
    finally:
        try:
            await websocket.close()
        except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError):
            pass


@app.post("/article/batch", response_model=BatchArticleResponse)
async def generate_batch_articles(
    request: BatchArticleRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Generate a batch of articles with automatic 25% brand / 75% generic split.
    Does NOT auto-publish to WordPress.
    """
    _ = authenticated
    if AppState.orchestrator is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")

    if request.num_articles <= 0:
        raise HTTPException(status_code=400, detail="num_articles must be positive")

    try:
        categories_used = []
        original_generate = AppState.orchestrator.generate_blog

        def tracked_generate(*args, **kwargs):
            article, report, project = original_generate(*args, **kwargs)
            if article.category:
                categories_used.append(article.category)
            return article, report, project

        AppState.orchestrator.generate_blog = tracked_generate

        try:
            AppState.orchestrator.generate_batch_articles(
                num_articles=request.num_articles, publish_to_wordpress=False
            )
            successful = len(categories_used)
        finally:
            AppState.orchestrator.generate_blog = original_generate

        return BatchArticleResponse(
            message=f"Batch generation completed. {successful}/{request.num_articles} articles generated successfully.",
            total_articles=request.num_articles,
            successful=successful,
            categories_used=list(set(categories_used))
        )

    except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
        logger.error("Batch generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch generation failed: {e}") from e


@app.post("/scraper/run", response_model=ScrapeResponse)
async def run_scraper():
    """Run the competitor blog scraper (former CLI option 3)."""
    if AppState.orchestrator is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    try:
        AppState.orchestrator.run_scraping()
        return ScrapeResponse(
            message="Scraping completed. Check logs and scraped_articles.json for details."
        )
    except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
        logger.error("Scraper run failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scraper failed: {e}") from e


@app.post("/campaign/run", response_model=CampaignResponse)
async def run_campaign(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign with 25% brand / 75% generic split.
    This endpoint ONLY generates articles; it does NOT publish them.
    """
    _ = authenticated
    if AppState.campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400,
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        AppState.campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False
        )
        return CampaignResponse(
            message=f"Campaign completed for {request.total_articles} articles. See logs for details."
        )
    except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
        logger.error("Campaign run failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}") from e


@app.post("/campaign/publish", response_model=CampaignResponse)
async def run_campaign_and_publish(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign AND automatically Publish to WordPress.
    """
    _ = authenticated
    if AppState.campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400,
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        AppState.campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=True,
            publish_to_blogger=False,
            publish_to_tumblr=False
        )
        return CampaignResponse(
            message=(
                f"Campaign completed and published to WordPress for "
                f"{request.total_articles} articles. See logs for details."
            )
        )
    except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
        logger.error("Campaign run-publish failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}") from e


@app.post("/campaign/publish-wordpress", response_model=CampaignResponse, include_in_schema=False)
async def run_campaign_and_publish_wordpress_alias(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Deprecated alias for /campaign/publish.
    """
    return await run_campaign_and_publish(request, authenticated)


@app.post("/campaign/publish/blogger", response_model=CampaignResponse)
async def run_campaign_and_publish_blogger(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign AND automatically Publish to Blogger.
    """
    _ = authenticated
    if AppState.campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400,
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        AppState.campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False,
            publish_to_blogger=True,
            publish_to_tumblr=False
        )
        return CampaignResponse(
            message=(
                f"Campaign completed and published to Blogger (no images) for "
                f"{request.total_articles} articles. See logs for details."
            )
        )
    except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
        logger.error("Campaign run-publish-blogger failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}") from e


@app.post("/campaign/publish/tumblr", response_model=CampaignResponse)
async def run_campaign_and_publish_tumblr(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign AND automatically Publish to Tumblr.
    """
    _ = authenticated
    if AppState.campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400,
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        AppState.campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False,
            publish_to_blogger=False,
            publish_to_tumblr=True
        )
        return CampaignResponse(
            message=(
                f"Campaign completed and published to Tumblr (no images) for "
                f"{request.total_articles} articles. See logs for details."
            )
        )
    except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
        logger.error("Campaign run-publish-tumblr failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}") from e


# Thread lock for database writes
_db_write_lock = threading.Lock()


def _load_article_meta(title: str) -> tuple[str, list, str]:
    """Load meta description, keywords, and generated time from json."""
    safe_filename = re.sub(r'[^a-zA-Z0-9 ]', '', title).replace(' ', '_')[:50]
    json_path = os.path.join(Config.JSON_OUTPUT_DIR, f"{safe_filename}.json")

    meta_description = ""
    keywords = []
    generated_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f_handle:
                meta_data = json.load(f_handle)
                meta_description = meta_data.get("meta_description", "")
                keywords = meta_data.get("keywords", [])
                if "generated_time" in meta_data:
                    generated_time = meta_data["generated_time"]
        except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
            logger.error("Failed to read consolidated JSON at %s: %s", json_path, e)
    else:
        logger.warning("Consolidated JSON not found at %s", json_path)

    return meta_description, keywords, generated_time


def _generate_article_slug_url(title: str, category: str) -> tuple[str, str]:
    """Generate unique slug and canonical URL."""
    if (AppState.orchestrator and AppState.orchestrator.content_generator
            and hasattr(AppState.orchestrator.content_generator, 'slug_registry')):
        slug = AppState.orchestrator.content_generator.slug_registry.generate_unique_slug(title, category=category)
    else:
        slug = re.sub(r'[^a-z0-9-]', '', title.lower().replace(' ', '-'))[:60].rstrip('-')
    canonical_url = f"{Config.DEFAULT_LINK_URL}/{slug}"
    return slug, canonical_url


def _write_article_csv(row_data: list):
    """Append article row to articles.csv."""
    with open(Config.CSV_PATH, 'a', newline='', encoding='utf-8') as f_handle:
        csv.writer(f_handle).writerow(row_data)


def _commit_article_to_db(art: dict, platform: str):
    """
    Helper to append article to articles.csv, articles_external.csv and increment stats
    thread-safely, called when article is successfully generated.
    """
    title = art.get("title", "")
    if not title:
        logger.warning("Empty title, skipping DB commit.")
        return

    meta_description, keywords, generated_time = _load_article_meta(title)
    category = art.get("category", "")
    _, canonical_url = _generate_article_slug_url(title, category)

    with _db_write_lock:
        existing_articles = AppState.orchestrator.csv_manager.get_all_articles()
        article_no = len(existing_articles) + 1
        article_id = art.get("article_id") or hashlib.md5(title.encode()).hexdigest()[:8]

        row_data = [
            article_no,
            article_id,
            generated_time,
            title,
            canonical_url,
            "",  # wp_published_url
            "",  # wp_published_slug
            "",  # wp_published_title
            "",  # blogger_published_url
            "",  # tumblr_published_url
            art.get("linkedin_path", ""),
            art.get("medium_path", ""),
            platform,  # platforms_published
            meta_description,
            ','.join(keywords) if isinstance(keywords, list) else str(keywords),
            art.get("product", ""),  # project_name
            "yes"  # article_published
        ]

        try:
            _write_article_csv(row_data)
            logger.info("Successfully appended article #%d '%s' to articles.csv", article_no, title)
        except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
            logger.error("Failed to write to articles.csv: %s", e)

        try:
            AppState.orchestrator.csv_manager.add_external_article(title, platform)
        except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
            logger.error("Failed to log external article to articles_external.csv: %s", e)

        try:
            StatsManager.increment_generated()
            StatsManager.increment_published(platform)
            logger.info("Successfully updated stats.json")
        except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
            logger.error("Failed to update stats.json: %s", e)


@app.post("/campaign/publish/linkedin", response_model=CampaignResponse)
async def run_campaign_and_publish_linkedin(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign AND generate LinkedIn copy-paste JSON payloads.
    Automatically emails the generated articles in sets of 3.
    """
    _ = authenticated
    if AppState.campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400,
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        successful_articles = AppState.campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False,
            publish_to_blogger=False,
            publish_to_tumblr=False,
            publish_to_linkedin=True,
            publish_to_medium=False
        )

        email_service = EmailService()
        sets_sent = 0
        committed_count = 0
        for i in range(0, len(successful_articles), 3):
            article_set = successful_articles[i:i+3]
            if len(article_set) > 0:
                logger.info("Dispatching set of %d articles to email service...", len(article_set))
                email_result = email_service.send_articles_set(article_set)
                if email_result in ("sent", "fallback"):
                    if email_result == "sent":
                        sets_sent += 1
                    for art in article_set:
                        _commit_article_to_db(art, "linkedin")
                        committed_count += 1

        return CampaignResponse(
            message=(
                f"Campaign completed. Generated {len(successful_articles)} LinkedIn payloads. "
                f"Successfully dispatched {sets_sent} sets via email. "
                f"Committed {committed_count} articles to database."
            )
        )
    except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
        logger.error("Campaign run-publish-linkedin failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}") from e


@app.post("/campaign/publish/medium", response_model=CampaignResponse)
async def run_campaign_and_publish_medium(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign AND generate Medium copy-paste JSON payloads.
    Automatically emails the generated articles in sets of 3.
    """
    _ = authenticated
    if AppState.campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400,
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        successful_articles = AppState.campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False,
            publish_to_blogger=False,
            publish_to_tumblr=False,
            publish_to_linkedin=False,
            publish_to_medium=True
        )

        email_service = EmailService()
        sets_sent = 0
        committed_count = 0
        for i in range(0, len(successful_articles), 3):
            article_set = successful_articles[i:i+3]
            if len(article_set) > 0:
                logger.info("Dispatching set of %d articles to email service...", len(article_set))
                email_result = email_service.send_articles_set(article_set)
                if email_result in ("sent", "fallback"):
                    if email_result == "sent":
                        sets_sent += 1
                    for art in article_set:
                        _commit_article_to_db(art, "medium")
                        committed_count += 1

        return CampaignResponse(
            message=(
                f"Campaign completed. Generated {len(successful_articles)} Medium payloads. "
                f"Successfully dispatched {sets_sent} sets via email. "
                f"Committed {committed_count} articles to database."
            )
        )
    except (RuntimeError, ValueError, KeyError, AttributeError, TypeError, OSError) as e:
        logger.error("Campaign run-publish-medium failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}") from e


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
