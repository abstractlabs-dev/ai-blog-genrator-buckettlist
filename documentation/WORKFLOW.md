# AI Blog Generator - Complete Updated Workflow

This document provides a comprehensive technical walkthrough of the end-to-end operation of the AI Blog Generator.

---

## 🏗️ Phase 1: Preparation & Initialization

Before any generation begins, the system ensures the environment is correctly configured.

1.  **Environment Check**: The `Config` class (`src/config.py`) validates the presence of `.env` variables (API keys, brand info, etc.).
2.  **Directory Setup**: Essential directories (`data/`, `data/logs/`, `data/output/`, `data/images/`, etc.) are created if missing.
3.  **Database Sync**: The `CSVManager` (`utils/utils.py`) initializes `articles.csv` and `scraped_keywords.csv` with appropriate headers.
4.  **Category Mapping**: The system loads `categories_mapping.json` to map human-readable category names to internal IDs for publishing.

## 🔍 Phase 2: Research & Scraping

The generator doesn't work in a vacuum; it researches the competition and extracts localized context.

1.  **Target Selection**: The `RobustScraper` (`src/scraper.py`) reads target competitor URLs from the configuration.
2.  **Autonomous Browsing**: Uses Selenium (or `undetected-chromedriver`) to visit sites, bypassing bot detection.
3.  **Data Extraction**:
    *   **Titles**: Extracted from H1 tags and meta titles.
    *   **Keywords**: Extracted from meta keywords and analyzed from content.
4.  **Localization & Sanitization**:
    *   Scraped data is filtered to ensure matches with the `TARGET_CITY` and `INDUSTRY_NAME` configured in `.env`.
    *   LLM-based sanitization ensures no competitor brand names leak into the local dataset.
5.  **Keyword Expansion**: An AI worker expands raw titles into sets of SEO-optimized keywords.
6.  **Persistence**: All researched data is saved to `scraped_articles.json` for future seed generation.

## ✍️ Phase 3: Generation & Orchestration

The `BlogGeneratorOrchestrator` (`src/services/orchestrator.py`) manages the core intelligence loop.

### 3.1 Title Selection
*   **Brand Articles**: Selects a product from `products_inventory.json` and creates a catchy, brand-focused title.
*   **Generic Articles**: Uses scraped keywords to create industry-relevant informative titles.
*   **Duplicate Prevention**: `TitleManager` verifies the title isn't already in the database and isn't too similar to existing posts.

### 3.2 The Two-Step LLM Process
To ensure high quality and valid formatting, generation is split into two distinct steps:
1.  **Step 1 (Creative Writing)**: Content is generated as plain text with structural markers (e.g., `SECTION:`, `FAQ_SECTION:`). This allows the LLM to focus purely on storytelling and SEO without being bogged down by HTML syntax.
2.  **Step 2 (HTML Formatting)**: A low-temperature (0.05) LLM call converts the plain text into perfect, semantic HTML (`<h1>`, `<h2>`, `<ul>`, etc.), ensuring all tags are closed and valid.

### 3.3 SEO Iteration Loop
The article is graded by the `SEOEvaluatorAgent`:
*   **Score Calculation**: Checks for keyword density, heading hierarchy, word count, and localization.
*   **Feedback Loop**: If the score is below `SEO_THRESHOLD`, the system provides specific improvement suggestions and re-generates the article (up to 5 iterations).

### 3.4 Internal Linking
The `InternalLinkingService` (`src/services/internal_linking.py`) scans the newly generated content and injects **exactly 3 links**:
*   **2 links** to existing internal blog posts or product pages (based on contextual relevance via vector search).
*   **1 direct link** to the main website using the configured default link and anchor text.
The system automatically distributes these 3 links evenly throughout the article content.

## 🎨 Phase 4: Enrichment & Multimedia

1.  **Image Generation**: Uses Google Imagen (`gemini-2.0-flash`) via `image_client.py`.
    *   **Visual Prompts**: The title is converted into a purely visual description to prevent the AI from trying (and failing) to render text on the image.
    *   **Style Randomization**: Styles are picked randomly (e.g., "Luxury Professional", "Modern Aesthetic") to ensure visual variety.
2.  **Metadata Synchronization**: The system cleans titles of Markdown artifacts and generates a compelling meta description.
3.  **Dating**: A random generation date is assigned between the `WEBSITE_START_DATE` and the current time to create a natural-looking publication history.

## 💾 Phase 5: Persistence & Publishing

1.  **Local Storage**:
    *   **CSV**: Core metadata is saved to `articles.csv`.
    *   **JSON**: A complete, portable version of the article (content + metadata) is saved to `data/output/json/`.
2.  **Vector Store**: The article text is chunked and indexed in a vector database (default: `weaviate_data/`) for semantic search capabilities.
3.  **Multi-Platform Publishing**:
    *   **WordPress**: Published via REST API, including featured images and category/tag assignment.
    *   **Blogger/Tumblr**: Published via their respective APIs if configured.
    *   **Status Update**: The local database is updated (`is_published="yes"`) once the remote platform confirms receipt.

---
*Generated by the AI Blog Generator Orchestrator*
