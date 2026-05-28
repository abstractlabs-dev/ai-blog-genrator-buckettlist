"""
Title Prompts Module
Contains prompt generation functions for titles and location sanitization.
"""
import random
from typing import List

from src.config import Config


def create_title_prompt(
    num: int,
    project_context: str,
    *,
    article_type: str = "generic",
    scraped_keywords: List[str] = None,
    category: str = "",
    seed_title: str = ""
) -> str:
    """
    Creates a prompt for generating SEO-optimized blog titles.
    """
    is_brand_article = article_type.lower() == "brand"

    # Add category context if present
    category_instruction = ""
    if category:
        if is_brand_article:
            category_instruction = (
                f"- **Product Category Focus:** The title MUST be about the specific product '{category}'.\n"
                "- **Angle:** Focus on 'how-to-use', 'where-to-apply', "
                "'optimal usage scenarios', and 'product-specific features'.\n"
                f"    - **Example Style:** 'The Ultimate Guide to Using {category} for [Need]', "
                f"'Top Features of {category}'."
            )
        else:
            category_instruction = (
                f"- **Industry Category Focus:** The title MUST be SPECIFICALLY about the '{category}' sector.\n"
                f"    - **Angle:** Focus on 'industrial applications', 'sector-wide benefits/drawbacks', "
                "'proper industrial usage', and 'high-level industry trends'.\n"
                f"    - **Mandatory Term:** The title **MUST** contain the word/phrase '{category}' "
                "or a direct synonym to ensure topic clarity.\n"
                f"    - **Hierarchy:** The CATEGORY ({category}) is the MASTER TOPIC. Keywords are just modifiers.\n"
                "- **DYNAMIC TOPICAL ISOLATION:** \n"
                f"        - The title MUST stay exclusively within the specific universe of '{category}'.\n"
                "        - Identify the relevant industry sector and FORBID context-mixing from unrelated sectors.\n"
                f"        - If '{category}' is a technical or professional topic, do NOT mention unrelated "
                "residential or consumer contexts unless they are the target.\n"
                "        - Ensure the title remains focused on the primary utility and value of "
                f"'{category}' within its specific industry."
            )

    # Include scraped keywords if available (for generic articles)
    keywords_instruction = ""
    if scraped_keywords and not is_brand_article:
        # Pick 8 random keywords to ensure variety across batches
        keyword_sample = random.sample(scraped_keywords, min(len(scraped_keywords), 8))
        sample_keywords = ", ".join(keyword_sample)
        keywords_instruction = f"- **Secondary Keywords (Use ONLY as modifiers):** {sample_keywords}"

    brand_instruction = ""
    if is_brand_article:
        brand_instruction = f"""
        - **Brand Focus:** Titles MUST mention "{Config.BRAND_NAME}".
        - **Format:** Focus on high-value benefits, specific product durability, or solving maintenance problems.
        - **NO LOCATION:** Do NOT mention specific cities like "{Config.TARGET_CITY}" in the TITLE.
        """
    else:
        brand_instruction = f"""
        - **Industry Focus:** Educational, technical, and broad. 
        - **Brand Exclusion:** Do NOT mention specific brands like "{Config.BRAND_NAME}".
        - **No City:** Do NOT mention specific cities like "{Config.TARGET_CITY}".
        - **Styles:** Use "The Science of...", "Comparison", "Ultimate Guide", or "Future Trends".
        """

    seed_instruction = ""
    if seed_title:
        seed_instruction = f"- **Seed Title:** Use this as a base and REPHRASE it: '{seed_title}'"

    prompt = f"""
    You are an SEO expert for the {Config.INDUSTRY_NAME}. Generate {num} distinct, unique, and high-CTR blog post titles.

    **CONTEXT:**
    {project_context}
    
    **REQUIREMENTS:**
    - **LANGUAGE: MUST be in English ONLY.** Failure to comply will result in immediate rejection.
    - **Article Type:** {'Brand-Specific' if is_brand_article else 'Industry-Generic'}
    {category_instruction}
    {brand_instruction}
    {keywords_instruction}
    {seed_instruction}
    - **Length:** 40-65 characters.
    - **SEO:** Title MUST contain a relevant industry keyword naturally.
    
    - **VARIETY CHECKLIST (MANDATORY - FAILURE TO COMPLY WILL RESULT IN REJECTION):**
        1. **NO REPETITIVE STARTING WORDS:** Each title MUST start with a COMPLETELY DIFFERENT word.
            BAD EXAMPLE:
           - "How to Improve Your Workflow"
           - "How to Boost Team Productivity"
           - "How to Optimize Business Operations"
            GOOD EXAMPLE:
           - "Practical Ways to Improve Your Workflow"
           - "Boost Team Productivity with These Tools"
           - "Optimize Business Operations Effectively"
        
        2. **NO COLON OVERUSE:** Avoid repetitive "[Topic]: [Benefit]" structures.
        
        3. **LINGUISTIC DIVERSITY:** Use a mix of:
            - Action Verbs (Achieve, Protect, Enhance, Transform, Optimize)
            - Questions (How do..., What are..., Why is... necessary?)
            - Guides (Practical Handbook for..., Strategies for..., Technical Analysis of...)
            - Benefits (Sustainable Methods, Cost-Savings in..., Long-Term Performance)
            - Lists (X Essential Steps, X Key Factors, X Innovative Approaches)
        
        4. **ANGLE MIX:** Use different angles like:
            - Technical/Deep-Dive
            - Economic/ROI-focused
            - Safety & Compliance
            - Innovation/Modern Trends
            - Problem/Solution
        
        5. **FORBIDDEN PATTERNS:**
            - DO NOT start more than 10% of titles with "The".
            - DO NOT use the words "Mastering", "Unlocking", "Unveiling", "Discover", or "Ultimate" unless necessary.
            - DO NOT use repetitive "[Word]: [Phrase]" structures.
    
    - **Tone:** Professional, authoritative, and helpful.
    - **Output:** Return ONLY a numbered list.

    **OUTPUT FORMAT:**
    1. [Title 1]
    2. [Title 2]
    ...
    {num}. [Title {num}]
    
    Return ONLY the numbered list of titles. EVERY title must start with a different word.
    """
    return prompt


def create_location_sanitizer_prompt(
    sample_titles: List[str],
    sample_keywords: List[str],
    need_titles: int,
    need_keywords: int,
    allowed_localities: List[str],
) -> str:
    """Creates a prompt that forces titles/keywords to be strictly specific to the target city."""
    allowed = ", ".join(allowed_localities)
    sample_titles_block = "\n".join(sample_titles)
    sample_keywords_block = ", ".join(sample_keywords)
    city = Config.TARGET_CITY

    prompt = (
        f"You will SANITIZE and TOP UP {Config.INDUSTRY_NAME} blog TITLES and KEYWORDS to be strictly {city}-only.\n\n"
        "STRICT LOCATION POLICY:\n"
        f"- All outputs must be about {city}.\n"
        f"- Treat allowed localities as {city} (allowed).\n"
        f"- If any item mentions a non-{city} city/locality, rewrite it to '{city}' or an allowed locality.\n"
        f"- Allowed localities: [{allowed}]\n"
        "- Any locality not in this list is forbidden; rewrite or replace.\n"
        f"- If an item cannot be localized, DROP it and create an {city}-only alternative.\n\n"
        f"NEEDS: +{need_titles} TITLES and +{need_keywords} KEYWORDS after sanitizing and deduping.\n\n"
        f"INPUT (examples):\n"
        f"Current Titles:\n{sample_titles_block}\n\n"
        f"Current Keywords:\n{sample_keywords_block}\n\n"
        "OUTPUT FORMAT (CRITICAL — EXACTLY THIS):\n"
        "TITLES:\n"
        f"1. <{city}-only title>\n"
        f"2. <{city}-only title>\n"
        "...\n"
        "KEYWORDS:\n"
        "keyword 1, keyword 2, keyword 3, ...\n"
    )
    return prompt
