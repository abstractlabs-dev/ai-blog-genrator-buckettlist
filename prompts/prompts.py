"""
Prompts Module
This module contains functions that generate the structured prompts
used to guide the Language Model's output for both title and content generation.
"""
from prompts.title_prompts import create_title_prompt, create_location_sanitizer_prompt
from prompts.content_prompts import (
    create_content_prompt,
    create_keyword_extraction_prompt,
    create_keyword_generation_prompt,
    create_raw_content_prompt,
    create_html_conversion_prompt,
)
from prompts.social_prompts import create_linkedin_prompt

# Re-exports
__all__ = [
    "create_title_prompt",
    "create_location_sanitizer_prompt",
    "create_content_prompt",
    "create_keyword_extraction_prompt",
    "create_keyword_generation_prompt",
    "create_raw_content_prompt",
    "create_html_conversion_prompt",
    "create_linkedin_prompt",
]
