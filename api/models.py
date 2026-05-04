from typing import List, Optional

from pydantic import BaseModel
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from src.config import Config

# API Key authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    """Verify the API key from request header."""
    if not Config.API_KEY:
        # If no API key is configured, allow all requests
        return True
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key"
        )
    if api_key != Config.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key"
        )
    return True





class BatchArticleRequest(BaseModel):
    """Request model for generating a batch of articles."""
    num_articles: int = 5


class BatchArticleResponse(BaseModel):
    """Response model for batch article generation."""
    message: str
    total_articles: int
    successful: int
    categories_used: List[str]


class ScrapeResponse(BaseModel):
    """Response model for running the scraper (option 3)."""

    message: str


class CampaignRequest(BaseModel):
    """Request model for running a concurrent campaign (option 4)."""

    total_articles: int
    max_workers: int = 6


class CampaignResponse(BaseModel):
    """Response model for concurrent campaign execution."""

    message: str
