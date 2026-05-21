"""
Pydantic Models Module
This module defines the data structures and custom exceptions used throughout the application.
Using Pydantic ensures data is validated and structured correctly.
"""
import logging
from datetime import datetime
from typing import List, Dict

from pydantic import BaseModel, Field, field_validator

from src.config import Config

# --- Pydantic Models for Data Structuring ---
class LLMConfig(BaseModel):
    """Configuration for LLM generation parameters."""
    model_name: str
    max_tokens: int = 2000
    temperature: float = 0.1
    fallback_models: List[str] = Field(default_factory=list)
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    timeout: int = 60
    max_retries: int = 2
    include_usage: bool = False
    task_name: str = "LLM Generation"

class Metadata(BaseModel):
    title: str = Field(..., max_length=60, description="Meta title under 60 characters")
    description: str = Field(..., max_length=156, description="Meta description under 156 characters")
    focus_keyword: str = Field("", description="Primary focus keyword for SEO")
    url_slug: str = Field(..., description="SEO-friendly URL slug")
    canonical_url: str = Field(..., description="Canonical URL")
    keywords: List[str] = Field(..., description="Target keywords for the article")
    json_ld_schema: Dict = Field(..., description="JSON-LD structured data for rich snippets")

class InternalLink(BaseModel):
    anchor_text: str
    target_url: str
    relevance_score: float

class ArticleDraft(BaseModel):
    title: str
    content_html: str
    word_count: int
    metadata: Metadata
    internal_links: List[InternalLink] = Field(default_factory=list)
    category: str = ""  # Category of the article (Product or Industry)
    parent_category: str = ""  # Parent category type (Product Categories or Industry Categories)
    faq_section: str
    token_usage: Dict[str, int] = Field(default_factory=dict)
    cost: float = 0.0
    useful_tokens: Dict[str, int] = Field(default_factory=dict)
    useful_cost: float = 0.0
    image_path: str = ""
    image_description: str = ""
    is_published: bool = False
    generated_at: datetime = Field(default_factory=datetime.now)
    article_id: str = ""
    linkedin_path: str = ""
    medium_path: str = ""
    wp_link: str = ""
    wp_slug: str = ""

    @field_validator('word_count')
    @classmethod
    def validate_word_count(cls, value):
        if not Config.MIN_WORD_COUNT <= value <= Config.MAX_WORD_COUNT:
            logging.warning(
                "Word count %d is outside the optimal range of %d-%d",
                value, Config.MIN_WORD_COUNT, Config.MAX_WORD_COUNT
            )
        return value

class SEOMetric(BaseModel):
    name: str
    score: int
    weight: int
    max_score: int
    feedback: str

class SEOReport(BaseModel):
    overall_score: int
    metrics: List[SEOMetric]
    passed: bool = Field(default=False)
    improvement_suggestions: List[str]
    iteration_number: int
    evaluated_at: datetime = Field(default_factory=datetime.now)

    @field_validator('overall_score')
    @classmethod
    def validate_score(cls, value):
        return max(0, min(100, value))

# --- Custom Exceptions ---
class NoAvailableProductError(Exception):
    """Raised when no unique product is available for a brand article."""


class DuplicateArticleError(Exception):
    """Raised when an article with the same title already exists."""


class BlogGenerationError(Exception):
    """Raised when blog generation fails to meet requirements."""
    def __init__(self, message, total_tokens=None, total_cost=None):
        super().__init__(message)
        self.total_tokens = total_tokens or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.total_cost = total_cost or 0.0
