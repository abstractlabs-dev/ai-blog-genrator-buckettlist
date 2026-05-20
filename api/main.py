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
            "/campaign/publish/linkedin": "Run concurrent generation & Generate LinkedIn payloads - requires API key",
            "/campaign/publish/medium": "Run concurrent generation & Generate Medium payloads - requires API key",
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


@app.post("/campaign/publish/linkedin", response_model=CampaignResponse)
async def run_campaign_and_publish_linkedin(
    request: CampaignRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a concurrent article generation campaign AND generate LinkedIn copy-paste JSON payloads.
    
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
        _campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False,
            publish_to_blogger=False,
            publish_to_tumblr=False,
            publish_to_linkedin=True,
            publish_to_medium=False
        )
        return CampaignResponse(
            message=f"Campaign completed and LinkedIn payloads generated for {request.total_articles} articles. See logs for details."
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
        _campaign_manager.run_campaign(
            total_articles=request.total_articles,
            max_workers=request.max_workers,
            publish_to_wordpress=False,
            publish_to_blogger=False,
            publish_to_tumblr=False,
            publish_to_linkedin=False,
            publish_to_medium=True
        )
        return CampaignResponse(
            message=f"Campaign completed and Medium payloads generated for {request.total_articles} articles. See logs for details."
        )
    except Exception as e:
        logger.error("Campaign run-publish-medium failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Campaign failed: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
