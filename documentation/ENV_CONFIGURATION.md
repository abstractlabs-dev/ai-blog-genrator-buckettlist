# Environment Configuration Guide

This document provides a detailed explanation of the `.env` configuration file, which governs the behavior of the AI Blog Generator. Each variable controls specific aspects of the application, from API keys to content strategy and scraping behavior.

## API Keys

These keys authenticate the application with external AI providers.

| Variable | Description | Impact |
| :--- | :--- | :--- |
| `GOOGLE_AI_STUDIO_API_KEY` | Your secret API key from Google AI Studio (Gemini). | **Critical**. Required for generating article content, SEO evaluation, and title generation. If missing, the app runs in "fallback mode" and cannot generate new content. |
| `GEMINI_API_KEY` | Deprecated alias for `GOOGLE_AI_STUDIO_API_KEY`. | Kept for backward compatibility with older `.env` files. |
| `API_KEY` | Internal API key for the application itself. | Used to secure the application's own API endpoints (if the API server is started). |

## Model Selection

Controls which specific AI models are used for generation.

| Variable | Description | Impact |
| :--- | :--- | :--- |
| `GEMINI_MODEL` | The Gemini model ID to use (e.g., `gemini-2.0-flash`, `gemini-1.5-flash`). | Determines the quality and cost of text generation. `gemini-2.0-flash` is the default in this codebase. |
| `IMAGE_MODEL` | The Google Imagen model ID to use. | The codebase defaults to `imagen-4.0-generate-001` and has image-model fallback logic. |

## Brand Details

These variables inject your specific brand identity into the generated content.

| Variable | Description | Impact |
| :--- | :--- | :--- |
| `BRAND_NAME` | Name of your company or brand. | Used extensively in "Brand" type articles, inserted into introductions, conclusions, and meta descriptions. |
| `INDUSTRY_NAME` | The industry you operate in (e.g., "Paint Manufacturing"). | Used to provide context to the AI for "Generic" articles and to guide the scraper's relevance filtering. |
| `BRAND_MENTION_RATIO` | A number between 0.0 and 1.0 (Default: `0.25`). | **Governing Logic**: Controls the mix of content types. A value of `0.25` means roughly 25% of generated articles will be "Brand-Focused" (promoting `BRAND_NAME`), while 75% will be "Generic" (neutral industry advice). |
| `TARGET_CITY` | Primary target city for local SEO. | Inserted into keywords (e.g., "best painters in [City]") and content to boost local search rankings. |
| `TARGET_STATE` | Target state/region. | Used for broader local SEO context. |
| `DEFAULT_LINK_URL` | The URL users should visit. | Used as the canonical URL base and in JSON-LD schema markup. |
| `DEFAULT_LINK_TEXT` | Anchor text for links. | Used when creating call-to-action links. |
| `BRAND_PROMOTION_ENABLED` | `True` or `False`. | If `True`, enables specific promotional sections in articles. |

## Generation Settings

Controls the "creativity" and constraints of the AI.

| Variable | Description | Impact |
| :--- | :--- | :--- |
| `TEMPERATURE` | A value between 0.0 and 2.0 (Default: `0.3`). | Controls randomness. Lower values (e.g., 0.3) make the output more focused and deterministic. Higher values make it more creative but less predictable. |
| `WEBSITE_START_DATE` | Date string (YYYY-MM-DD). | Used to simulate a realistic publishing history. Generated articles are assigned random dates between this start date and "now". |

## Scraper Settings

Configures the `RobustScraper` which finds topics from competitor sites.

| Variable | Description | Impact |
| :--- | :--- | :--- |
| `SCRAPER_RAW_MODE` | `0` (False) or `1` (True). | **Important**. If `1`, the scraper runs in "Raw" mode, extracting text without using the LLM to clean or structure it. If `0`, it uses the LLM to process scraped titles, which is slower but cleaner. |
| `SCRAPER_PAGE_LOAD_TIMEOUT` | Seconds (Default: 30). | How long to wait for a page to load before retrying. |
| `SCRAPER_ELEMENT_WAIT_TIMEOUT`| Seconds (Default: 20). | How long to wait for specific elements (like article titles) to appear. |
| `SCRAPER_MAX_RETRIES` | Integer (Default: 2). | Number of times to retry scraping a failed URL. |
| `SCRAPER_RETRY_DELAY` | Seconds (Default: 5). | Time to wait between retries. |
| `SCRAPER_SITE_GAP` | Seconds (Default: 10). | **Politeness Delay**. Time to wait between requests to the *same* site to avoid getting banned. |

## SEO & Article Settings

Governs limits and quality thresholds for the content pipeline.

| Variable | Description | Impact |
| :--- | :--- | :--- |
| `MAX_ARTICLE_RETRIES` | Integer (Default: 5). | Maximum number of "iterations" the AI attempts to improve an article to meet the `SEO_THRESHOLD` score. |
| `MIN_WORD_COUNT` | Integer (Default: 1200). | Minimum required word count. The AI receives negative feedback if the article is too short. |
| `MAX_WORD_COUNT` | Integer (Default: 2000). | Maximum word count target. |
| `SEO_THRESHOLD` | Integer 0-100 (Default: 80). | **Quality Gate**. An article is ONLY saved and published if it achieves an internal SEO score higher than this value. If it fails this score after `MAX_ARTICLE_RETRIES`, the generation is considered failed. |
| `MAX_TOTAL_ARTICLES` | Integer (Default: 5000). | Hard limit on the database size. Generation stops if this limit is reached. |
| `IMAGE_GENERATION_RATIO` | A number between 0.0 and 1.0 (Default: 0.8). | **Cost Control**. Controls the probability of generating an image for an article. `0.8` means ~80% of articles will get an AI-generated image, saving costs on the other 20%. |

## Publishing Configuration

Credentials for auto-publishing to various platforms.

| Variable | Description | Impact |
| :--- | :--- | :--- |
| `WORDPRESS_BASE_URL` | URL to your WordPress XML-RPC endpoint (usually `domain.com/xmlrpc.php`). | Destination for publishing. |
| `WORDPRESS_USERNAME` | Admin username. | Authentication. |
| `WORDPRESS_TOKEN` | Application Password (NOT your login password). | Authentication. |
| `BLOGGER_BLOG_ID` | Google Blogger Blog ID. | Target blog for Blogger publishing. |
| `TUMBLR_*` | various keys. | OAuth credentials for Tumblr API publishing. |

## Summary of Critical Controls

- To **reduce AI costs**, lower `IMAGE_GENERATION_RATIO` or use a cheaper `GEMINI_MODEL`.
- To **increase quality**, raise `SEO_THRESHOLD` (may consume more tokens per article due to retries).
- To **change content mix**, adjust `BRAND_MENTION_RATIO` (Higher = more salesy, Lower = more informational).
- To **fix scraping issues**, increase `SCRAPER_PAGE_LOAD_TIMEOUT` or `SCRAPER_SITE_GAP`.
