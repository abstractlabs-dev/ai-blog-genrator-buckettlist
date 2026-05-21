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

from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
import uvicorn

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.config import Config
from src.services import BlogGeneratorOrchestrator
from src.concurrent_manager import ConcurrentCampaignManager
from .models import (
    ScrapeResponse, 
    CampaignRequest, 
    CampaignResponse,
    BatchArticleRequest,
    BatchArticleResponse,
    verify_api_key
)


logger = logging.getLogger(__name__)

# Load environment variables from .env before reading Config
load_dotenv()

try:
    Config.ensure_directories()
    Config.validate_api_key()
    _orchestrator = BlogGeneratorOrchestrator()
    _campaign_manager = ConcurrentCampaignManager(_orchestrator)
except Exception as e:
    logger.error("Failed to initialize blog services: %s", e, exc_info=True)
    _orchestrator = None
    _campaign_manager = None


app = FastAPI(
    title="Blog Generator API",
    description="API for generating blog articles, running campaigns, and scraping competitor blogs.",
    version="2.1.0"
)

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
            "/campaign/publish/blogger": "Run concurrent generation & Publish to Blogger (No Images) - requires API key",
            "/campaign/publish/tumblr": "Run concurrent generation & Publish to Tumblr (No Images) - requires API key",
            "/campaign/publish/linkedin": "Run concurrent generation & Generate LinkedIn payloads (Auto-emails in sets of 3) - requires API key",
            "/campaign/publish/medium": "Run concurrent generation & Generate Medium payloads (Auto-emails in sets of 3) - requires API key",
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
        # Send initial status
        await websocket.send_json({
            "status": "connected",
            "timestamp": datetime.now().isoformat(),
            "message": "WebSocket connection established"
        })
        
        # Keep connection alive and send periodic updates
        while True:
            try:
                # Wait for any client message (ping/pong)
                data = await websocket.receive_text()
                # Echo back a status update
                await websocket.send_json({
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat()
                })
            except WebSocketDisconnect:
                break
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.post("/article/batch", response_model=BatchArticleResponse)
async def generate_batch_articles(
    request: BatchArticleRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Generate a batch of articles with automatic 25% brand / 75% generic split.
    Does NOT auto-publish to WordPress.
    
    - **num_articles**: Total number of articles to generate
    """
    if _orchestrator is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    
    if request.num_articles <= 0:
        raise HTTPException(status_code=400, detail="num_articles must be positive")
    
    try:
        # Track categories used
        categories_used = []
        
        # Store original generate_blog to capture categories
        original_generate = _orchestrator.generate_blog
        
        def tracked_generate(*args, **kwargs):
            article, report, project = original_generate(*args, **kwargs)
            if article.category:
                categories_used.append(article.category)
            return article, report, project
        
        # Temporarily replace generate_blog
        _orchestrator.generate_blog = tracked_generate
        
        try:
            _orchestrator.generate_batch_articles(num_articles=request.num_articles, publish_to_wordpress=False)
            successful = len(categories_used)
        finally:
            # Restore original method
            _orchestrator.generate_blog = original_generate
        
        return BatchArticleResponse(
            message=f"Batch generation completed. {successful}/{request.num_articles} articles generated successfully.",
            total_articles=request.num_articles,
            successful=successful,
            categories_used=list(set(categories_used))  # Unique categories
        )
    
    except Exception as e:
        logger.error("Batch generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch generation failed: {e}")


@app.post("/scraper/run", response_model=ScrapeResponse)
async def run_scraper():
    """Run the competitor blog scraper (former CLI option 3)."""
    if _orchestrator is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    try:
        _orchestrator.run_scraping()
        return ScrapeResponse(
            message="Scraping completed. Check logs and scraped_articles.json for details."
        )
    except Exception as e:
        logger.error("Scraper run failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scraper failed: {e}")


@app.post("/campaign/run", response_model=CampaignResponse)
async def run_campaign(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign with 25% brand / 75% generic split.
    This endpoint ONLY generates articles; it does NOT publish them.
    
    - **total_articles**: Total number of articles to generate
    - **max_workers**: Maximum number of concurrent workers
    """
    if _campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400, 
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        _campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False
        )
        return CampaignResponse(
            message=f"Campaign completed for {request.total_articles} articles. See logs and output files for details."
        )
    except Exception as e:
        logger.error("Campaign run failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}")


@app.post("/campaign/publish", response_model=CampaignResponse)
async def run_campaign_and_publish(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign AND automatically Publish to WordPress.
    
    - **total_articles**: Total number of articles to generate and publish
    - **max_workers**: Maximum number of concurrent workers
    """
    if _campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400, 
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        _campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=True,
            publish_to_blogger=False,
            publish_to_tumblr=False
        )
        return CampaignResponse(
            message=f"Campaign completed and published to WordPress for {request.total_articles} articles. See logs for details."
        )
    except Exception as e:
        logger.error("Campaign run-publish failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}")


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
    
    - **total_articles**: Total number of articles to generate and publish
    - **max_workers**: Maximum number of concurrent workers
    """
    if _campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400, 
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        _campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False,
            publish_to_blogger=True,
            publish_to_tumblr=False
        )
        return CampaignResponse(
            message=f"Campaign completed and published to Blogger (no images) for {request.total_articles} articles. See logs for details."
        )
    except Exception as e:
        logger.error("Campaign run-publish-blogger failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}")


@app.post("/campaign/publish/tumblr", response_model=CampaignResponse)
async def run_campaign_and_publish_tumblr(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign AND automatically Publish to Tumblr.
    
    - **total_articles**: Total number of articles to generate and publish
    - **max_workers**: Maximum number of concurrent workers
    """
    if _campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400, 
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        _campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False,
            publish_to_blogger=False,
            publish_to_tumblr=True
        )
        return CampaignResponse(
            message=f"Campaign completed and published to Tumblr (no images) for {request.total_articles} articles. See logs for details."
        )
    except Exception as e:
        logger.error("Campaign run-publish-tumblr failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}")


import threading

# Thread lock for database writes
_db_write_lock = threading.Lock()

def _commit_article_to_db(art: dict, platform: str):
    """
    Helper to append article to articles.csv, articles_external.csv and increment stats
    thread-safely, only called when SMTP email is successfully sent.
    """
    import csv
    import re
    import json
    import hashlib
    from datetime import datetime
    from src.stats_manager import StatsManager

    title = art.get("title", "")
    if not title:
        logger.warning("Empty title, skipping DB commit.")
        return

    with _db_write_lock:
        # 1. Calculate safe_filename and load JSON metadata
        safe_filename = re.sub(r'[^a-zA-Z0-9 ]', '', title).replace(' ', '_')[:50]
        json_path = os.path.join(Config.JSON_OUTPUT_DIR, f"{safe_filename}.json")
        
        meta_description = ""
        keywords = []
        generated_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        category = ""
        
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
                    meta_description = meta_data.get("meta_description", "")
                    keywords = meta_data.get("keywords", [])
                    if "generated_time" in meta_data:
                        generated_time = meta_data["generated_time"]
                    category = meta_data.get("category", "")
            except Exception as e:
                logger.error("Failed to read consolidated JSON at %s: %s", json_path, e)
        else:
            logger.warning("Consolidated JSON not found at %s", json_path)

        # 2. Get unique slug and canonical URL
        slug = ""
        if _orchestrator and _orchestrator.content_generator and hasattr(_orchestrator.content_generator, 'slug_registry'):
            slug = _orchestrator.content_generator.slug_registry.generate_unique_slug(title, category=category)
        else:
            # Fallback slug generation
            slug = re.sub(r'[^a-z0-9-]', '', title.lower().replace(' ', '-'))[:60].rstrip('-')
            
        canonical_url = f"{Config.DEFAULT_LINK_URL}/{slug}"

        # 3. Read existing articles to compute next article_no
        existing_articles = _orchestrator.csv_manager.get_all_articles()
        article_no = len(existing_articles) + 1
        
        # Get article ID
        article_id = art.get("article_id") or hashlib.md5(title.encode()).hexdigest()[:8]
        
        linkedin_path = art.get("linkedin_path", "")
        medium_path = art.get("medium_path", "")
        
        # 4. Save to articles.csv
        try:
            with open(Config.CSV_PATH, 'a', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([
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
                    linkedin_path,
                    medium_path,
                    platform,  # platforms_published (e.g. "linkedin" or "medium")
                    meta_description,
                    ','.join(keywords) if isinstance(keywords, list) else str(keywords),
                    art.get("product", ""),  # project_name
                    "yes"  # article_published
                ])
            logger.info("Successfully appended article #%d '%s' to articles.csv", article_no, title)
        except Exception as e:
            logger.error("Failed to write to articles.csv: %s", e)

        # 5. Save to articles_external.csv
        try:
            _orchestrator.csv_manager.add_external_article(title, platform)
        except Exception as e:
            logger.error("Failed to log external article to articles_external.csv: %s", e)

        # 6. Update stats.json
        try:
            # Increment generated count
            StatsManager.increment_generated()
            # Increment platform published count
            StatsManager.increment_published(platform)
            logger.info("Successfully updated generation and publication stats in stats.json")
        except Exception as e:
            logger.error("Failed to update stats.json: %s", e)


@app.post("/campaign/publish/linkedin", response_model=CampaignResponse)
async def run_campaign_and_publish_linkedin(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign AND generate LinkedIn copy-paste JSON payloads.
    Automatically emails the generated articles in sets of 3.
    
    - **total_articles**: Total number of articles to generate and export to LinkedIn JSON payload
    - **max_workers**: Maximum number of concurrent workers
    """
    if _campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400, 
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        successful_articles = _campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False,
            publish_to_blogger=False,
            publish_to_tumblr=False,
            publish_to_linkedin=True,
            publish_to_medium=False
        )
        
        # Automatically chunk successful articles in sets of 3 and email them
        from src.services.email_service import EmailService
        email_service = EmailService()
        
        sets_sent = 0
        committed_count = 0
        for i in range(0, len(successful_articles), 3):
            article_set = successful_articles[i:i+3]
            if len(article_set) > 0:
                logger.info("Dispatching set of %d articles to email service...", len(article_set))
                email_result = email_service.send_articles_set(article_set)
                if email_result == "sent":
                    sets_sent += 1
                    # Commit to database and stats ONLY when email sent via remote SMTP
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
    except Exception as e:
        logger.error("Campaign run-publish-linkedin failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}")


@app.post("/campaign/publish/medium", response_model=CampaignResponse)
async def run_campaign_and_publish_medium(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign AND generate Medium copy-paste JSON payloads.
    Automatically emails the generated articles in sets of 3.
    
    - **total_articles**: Total number of articles to generate and export to Medium JSON payload
    - **max_workers**: Maximum number of concurrent workers
    """
    if _campaign_manager is None:
        raise HTTPException(status_code=500, detail="Blog services are not initialized")
    if request.total_articles <= 0 or request.max_workers <= 0:
        raise HTTPException(
            status_code=400, 
            detail="total_articles and max_workers must be positive integers"
        )

    try:
        successful_articles = _campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False,
            publish_to_blogger=False,
            publish_to_tumblr=False,
            publish_to_linkedin=False,
            publish_to_medium=True
        )
        
        # Automatically chunk successful articles in sets of 3 and email them
        from src.services.email_service import EmailService
        email_service = EmailService()
        
        sets_sent = 0
        committed_count = 0
        for i in range(0, len(successful_articles), 3):
            article_set = successful_articles[i:i+3]
            if len(article_set) > 0:
                logger.info("Dispatching set of %d articles to email service...", len(article_set))
                email_result = email_service.send_articles_set(article_set)
                if email_result == "sent":
                    sets_sent += 1
                    # Commit to database and stats ONLY when email sent via remote SMTP
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
    except Exception as e:
        logger.error("Campaign run-publish-medium failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
