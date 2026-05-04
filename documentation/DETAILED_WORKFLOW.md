# AI Blog Generator: Detailed End-to-End Workflow

This document provides a technical deep-dive into the end-to-end lifecycle of an article within the AI Blog Generator system.

---

## 🏗️ Phase 1: Initialization & Environment Safeguards
**Core File:** [config.py](file:///home/harsh/Downloads/Darsh/ai-blog-generator-generic/src/config.py)  
**Entry Point:** `api/main.py`

Before any processing occurs, the system performs a multi-point reliability check:
1.  **Environment Validation**: Ensures all critical API keys (OpenAI/DeepSeek, Google Imagen, WordPress/Blogger) and brand configurations (Brand Name, Industry, Target City) are present in `.env`.
2.  **Breadcrumb Check**: `ensure_directories()` creates the hierarchical data structure (`data/logs`, `data/output/json`, `data/images`, `weaviate_data`) to prevent I/O errors.
3.  **State Recovery**: Initializes `CSVManager` and `VectorStoreManager` to reload existing history, ensuring the system can resume or prevent duplicates.

---

## 🔍 Phase 2: Autonomous Research & Competitive Intelligence
**Core File:** [scraper.py](file:///home/harsh/Downloads/Darsh/ai-blog-generator-generic/src/scraper.py)  
**Agents involved:** `RobustScraper`

The system doesn't just "write"—it researches.
1.  **Stealth Browsing**: Uses `undetected-chromedriver` and `BeautifulSoup` to bypass bot-detection on competitor sites defined in `data/config/competitors.json`.
2.  **Semantic Filtering**: Scraped titles are passed through `_filter_titles_by_category()`. Only titles aligning with categories in `data/config/categories.json` are kept.
3.  **AI Keyword Expansion**: Each valid scraped title is sent to the LLM to generate a rich set of 15+ related SEO keywords, which are then saved to `scraped_articles.json`.
4.  **Sanitization Loop**: A dedicated LLM call removes competitor brand names and localizes content to the `TARGET_CITY` defined in the configuration.

---

## 🧠 Phase 3: Intelligent Orchestration & Quality Generation
**Core File:** [orchestrator.py](file:///home/harsh/Downloads/Darsh/ai-blog-generator-generic/src/services/orchestrator.py)  
**Agents involved:** `ContentGeneratorAgent`, `TitleManager`

The `BlogGeneratorOrchestrator` manages the logic flow:
1.  **Title Guard**: `TitleManager` uses `SequenceMatcher` to ensure the new title is not only unique in the database but also not "semantically too similar" to previous posts (similarity < 90%).
2.  **The Two-Step LLM Process**:
    *   **Step 1 (Creative)**: LLM generates the article in plain text with structural markers (`SECTION:`, `LIST:`). This maximizes narrative flow.
    *   **Step 2 (Structural)**: A high-precision (Temperature 0.05) LLM call converts the plain text into perfect semantic HTML, ensuring all tags are closed and valid.
3.  **Entity Injection**: If the article is "Brand Focused", it pulls data from `data/products.csv` using a rotation-based selection to ensure even coverage across all product categories.

---

## 🎨 Phase 4: Multimedia Enrichment & SEO Iteration
**Core Files:** [image_client.py](file:///home/harsh/Downloads/Darsh/ai-blog-generator-generic/src/image_client.py), [agents.py](file:///home/harsh/Downloads/Darsh/ai-blog-generator-generic/src/agents.py)  
**Agents involved:** `SEOEvaluatorAgent`, `InternalLinkingService`

1.  **AI Image Crafting**: Uses Google Imagen. The title is converted into a *visual description* (omitting letters) to prevent the AI from generating gibberish text in the banner.
2.  **SEO Loop (The Grading System)**: The `SEOEvaluatorAgent` scores the draft (0-100).
    *   If score < `SEO_THRESHOLD` (usually 80), the system re-runs Phase 3 with specific feedback (e.g., "Add more H2 headings", "Include keyword X 3 more times").
3.  **Internal Linking**: `InternalLinkingService` uses vector search to find contextually relevant past articles and injects exactly 3 links (2 internal, 1 external) to boost SEO authority.

---

## 🚀 Phase 5: Persistence & Deployment
**Core Files:** [publishers/](file:///home/harsh/Downloads/Darsh/ai-blog-generator-generic/src/publishers/), [utils.py](file:///home/harsh/Downloads/Darsh/ai-blog-generator-generic/utils/utils.py)

1.  **Dual Persistence**:
    *   **Structured Data**: Saved to `articles.csv`.
    *   **Unstructured Data**: Content is chunked and indexed into the Weaviate Vector DB for future internal linking.
2.  **Remote Deployment**:
    *   **WordPress**: Fetches the Category ID via `categories_mapping.json`, uploads the image to the media library, and publishes the post with Meta Descriptions (Yoast/RankMath compatible).
    *   **Blogger/Tumblr**: Parallel publishing via OAuth2/REST APIs.
3.  **Telemetry**: Final stats (token usage, cost, and success status) are logged to the console and `data/logs/`.

---
*Created by the AI Blog Generator System*
