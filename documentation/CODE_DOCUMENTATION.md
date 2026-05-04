# AI Blog Generator - Comprehensive Dictionary of Functions

This documentation serves as a detailed dictionary for every function in the codebase. It explains **WHAT** the function does, **HOW** it does it, and **WHERE** it is called (its usage context).

---

## 1. File: `src/config.py`
**Role:** Central control room. Stores all settings and ensures the environment is ready.

### Class: `Config`

#### `ensure_directories()`
-   **Functionality:** Checks if essential folders (`data/`, `data/logs/`, `data/output/`, etc.) exist. If they don't, it creates them using `os.makedirs`.
-   **Why:** Prevents the program from crashing with "File Not Found" errors when it tries to save a log or an article.
-   **Called By:** `api/main.py` (at startup).

#### `validate_api_key()`
-   **Functionality:** Looks for `GOOGLE_AI_STUDIO_API_KEY` in the environment variables. Logs a warning if missing and the app runs in fallback mode.
-   **Why:** The app cannot function without the LLM key, so it's better to crash early with a clear message than fail randomly later.
-   **Called By:** `api/main.py` (at startup).

#### `get_random_category(article_type: str)`
-   **Functionality:** Returns a random category string. If `article_type` is "brand", it picks from `PRODUCT_CATEGORIES` (e.g., "dummy_category_1"). If "generic", it picks from `INDUSTRY_CATEGORIES` (e.g., "dummy_category_2").
-   **Why:** When the user doesn't specify a category, we need to pick a relevant one to guide the AI.
-   **Called By:** `api/main.py` (in `/article/generate` endpoint when category is missing).

---

## 2. File: `src/utils/utils.py`
**Role:** The handyman. Handles file input/output and database updates.

### Class: `CSVManager`

#### `__init__(csv_path)`
-   **Functionality:** Checks if `articles.csv` exists. If not, creates it and writes the headers (`article_no`, `title`, etc.).
-   **Called By:** `src/services.py` (when initializing `BlogGeneratorOrchestrator`).

#### `save_article(article, short_description, product_name)`
-   **Functionality:**
    1.  Calculates the next `article_no` by counting existing rows.
    2.  Generates a unique 8-character ID hash from the title.
    3.  Appends a new row to `articles.csv` with the article's core details.
-   **Called By:** `src/services.py` -> `generate_blog` (after an article successfully passes SEO checks).

#### `get_all_articles()`
-   **Functionality:** Reads `articles.csv` and returns a list of dictionaries, one for each row.
-   **Called By:**
    -   `save_article` (to count rows).
    -   `src/services.py` -> `generate_blog` (to check for duplicate titles).

#### `get_covered_products()`
-   **Functionality:** Scans `articles.csv` and compiles a list of all "project_names" that have already been written about.
-   **Why:** To help the generator avoid writing about the same product multiple times in a row.
-   **Called By:** `src/services.py` (to pass exclusion lists to the generator).

### Class: `VectorStoreManager` (Optional)
*Handles connection to Weaviate for advanced search. If Weaviate isn't running, these functions do nothing safely.*

#### `add_article(article, article_id)`
-   **Functionality:** Splits the article text into chunks of 1000 characters and saves them to the vector database.
-   **Called By:** `src/services.py` -> `generate_blog` (after saving to CSV).

#### `find_similar_articles(query_text)`
-   **Functionality:** Asks the vector DB "What past articles define concepts similar to this text?".
-   **Called By:** `src/services.py` (potentially for duplicate content checks).

---

## 3. File: `src/llm_client.py`
**Role:** The Telephone. Handles all communication with OpenAI / DeepSeek.

#### `call_llm(model, prompt, max_tokens, temperature, ...)`
-   **Functionality:**
    1.  **Rate Limiting:** Checks a token bucket. If we are sending requests too fast, it sleeps for a few seconds.
    2.  **API Call:** Sends the prompt to OpenAI (using `litellm` library).
    3.  **Retries:** If OpenAI says "Server Error" or "Timeout", it waits and tries again (exponential backoff).
    4.  **Logging:** Records exactly how many tokens were used and the estimated cost.
-   **Why:** This is the *single* point of failure for AI calls, so it must be robust.
-   **Called By:**
    -   `src/agents.py` -> `ContentGeneratorAgent.generate_titles`
    -   `src/agents.py` -> `ContentGeneratorAgent.generate_article`
    -   `src/agents.py` -> `SEOEvaluatorAgent` (if using LLM for eval)

---


## 4. File: `src/image_client.py`
**Role:** The Artist. Handles communication with Google Gemini for images.

#### `generate_blog_image(prompt)`
-   **Functionality:**
    1.  Receives a highly detailed prompt from `services.py` (which includes negative constraints like "No logos", "Consistent Fonts").
    2.  Constructs a request for the `gemini-2.5-flash-image` (or `imagen-4.0-fast`) model.
    3.  Sends the prompt ("Generate a blog banner showing...") to Google.
    4.  Decodes the Base64 image data from the response.
-   **Called By:** `src/services.py` -> `_postprocess_article`.

#### `_generate_placeholder_image(prompt)`
-   **Functionality:** Uses the `PIL` (Python Imaging Library) to create a plain blue/grey rectangle (`1200x630`) and writes the article title on it in white text.
-   **Why:** Fallback ensures the pipeline *never* fails just because the image generator is down.
-   **Called By:** `generate_blog_image` (if the API fails).

---

## 5. File: `src/scraper.py`
**Role:** The Researcher. Browses the web to find data.

### Class: `RobustScraper`

#### `_init_driver()`
-   **Functionality:** Launches a headless Chrome browser with special flags (no-sandbox, disable-gpu) to run smoothly on servers. Can use `undetected-chromedriver` or standard Selenium based on config.
-   **Called By:** `__init__`.

#### `run_scraping_campaign()`
-   **Functionality:**
    1.  Reads target URLs from `Config.SCRAPED_TARGETS`.
    2.  Loops through them and calls `_scrape_site_with_browser`.
    3.  Matches titles against configured categories.
    4.  If not in "RAW" mode, it may use LLM to clean titles.
    5.  Saves the results to `scraped_articles.json`.
-   **Called By:** `src/services.py` -> `run_scraping`.

#### `run_scraping_campaign_raw()`
-   **Functionality:** Runs a scraping campaign using purely DOM-based extraction (h1, meta keywords) without ANY LLM processing.
-   **Why:** Cost-saving mode for high-volume scraping.
-   **Called By:** `src/services.py` -> `run_scraping` (if `SCRAPER_RAW_MODE=1`).

#### `_scrape_via_sitemap(sitemap_url)`
-   **Functionality:**
    1.  Downloads the XML sitemap.
    2.  Extracts all `<loc>` URLs (blog post links).
    3.  Visits URLs to better extract meaningful titles if sitemap data is sparse.
-   **Called By:** `run_scraping_campaign` (fallback).

---

## 6. File: `src/agents.py`
**Role:** The Core "Brains".

### Class: `TitleManager`

#### `_load_used_titles()`
-   **Functionality:** Loads existing titles from TWO sources to ensure zero duplicates:
    1.  The dedicated tracking CSV (`used_titles.csv`).
    2.  The main database CSV (`articles.csv`).
-   **Called By:** `__init__`.

#### `is_title_used(title)`
-   **Functionality:** Checks if `title` is in loaded titles OR if it is >90% similar to an existing title (using `difflib.SequenceMatcher`).
-   **Called By:** `ContentGeneratorAgent.generate_titles`.

### Class: `ContentGeneratorAgent`

#### `generate_titles(num, article_type, ...)`
-   **Functionality:**
    1.  Selects a product if `article_type` is "brand".
    2.  Selects scraper keywords if `article_type` is "generic".
    3.  Sends a prompt to `call_llm` asking for `num` catchy titles.
    4.  Filters out duplicates using `TitleManager`.
-   **Called By:**
    -   `src/services.py` (via Concurrent Manager workers).
    -   `src/concurrent_manager.py` (worker loop).

#### `generate_article(title, target_keywords, ...)`
-   **Functionality:**
    1.  Builds a massive "Writer Prompt" (Tone: Professional, Goal: SEO, Context: Brand info).
    2.  Calls `call_llm` (GPT-4).
    3.  Request includes specific HTML tags (`<h1>`, `<h2>`, `FAQ_SECTION`).
    4.  Calls `_parse_article_response` to convert the raw text into an `ArticleDraft` object.
-   **Called By:** `src/services.py` -> `generate_blog`.

### Class: `SEOEvaluatorAgent`

#### `evaluate_article(article)`
-   **Functionality:** Measures the article against a rubric.
-   **Sub-functions called:**
    -   `_evaluate_keyword_integration`: Counts exact keyword matches using regex.
    -   `_evaluate_location_keywords`: Checks if the target location (from `.env`) appears 3-15 times.
    -   `_evaluate_heading_structure`: Checks if `<h1>` exists and `<h2>` count > 2.
-   **Returns:** An `SEOReport` object with a score (e.g., 85/100) and specific feedback strings.
-   **Called By:** `src/services.py` -> `generate_blog` (inside the improvement loop).

---

## 7. File: `src/services.py`
**Role:** The Manager/Orchestrator. Coordinates the Agents.

### Class: `BlogGeneratorOrchestrator`

#### `generate_blog(title, article_type, ...)`
**THE MOST IMPORTANT FUNCTION.**
-   **Functionality:**
    1.  **Global Limit Check:** Checks `data/database/articles.csv`. If `count >= 5000`, raises `BlogGenerationError`.
    2.  **Duplicate Check:** Checks if `title` exists.
    3.  **Draft:** Calls `content_generator.generate_article`.
    4.  **Loop (Max 5 Iterations):**
        -   Calls `seo_evaluator.evaluate_article`.
        -   If `score >= 80`: Breaks loop (Success).
        -   If `score < 80`: Creates a "Feedback Prompt" (e.g., "Previous score 70. Fix: Use more keywords.") and calls `content_generator.generate_article` again with this context.
    5.  **Finalize:**
        -   Calls `image_client.generate_blog_image`.
        -   Calls `csv_manager.save_article`.
        -   Calls `vector_manager.add_article`.
-   **Called By:**
    -   `api/main.py` -> `/article/generate`
    -   `src/concurrent_manager.py` -> `_generate_article_worker`

---

## 8. File: `src/concurrent_manager.py`
**Role:** The Factory Floor Supervisor. Manages scale.

### Class: `ConcurrentCampaignManager`

#### `_generate_article_worker(article_type, index)`
-   **Functionality:** The isolated task for a single thread.
    1.  Asks Writer specifically for **1 Title** of the given type.
    2.  Passes that title to `orchestrator.generate_blog`.
    3.  Returns a dictionary with Status (Success/Fail) and Token Usage.
-   **Called By:** `run_campaign` (inside the ThreadPool).

#### `run_campaign(total_articles, max_workers)`
-   **Functionality:**
    1.  Calculates target breakdown (e.g., 250 Brand / 750 Generic).
    2.  Starts a `ThreadPoolExecutor` with `max_workers` (e.g., 6).
    3.  **Queue System:** Initially fills the queue with `total_articles` tasks.
    4.  **Monitoring Loop:**
        -   Waits for any worker to finish.
        -   If the result is **FAILURE** or **SKIPPED**: Immediately submits a **NEW** task to the queue to replace it.
        -   Keeps going until `success_count == total_articles`.
    5.  **Safety:** Stops if `attempts > total * 5`.
    6.  **Summary:** detailed printout of Wasted vs Useful tokens.
-   **Called By:** `api/main.py` -> `/campaign/run`.

---

## 9. File: `api/main.py`
**Role:** The Receptionist. Accepts HTTP requests from the outside world.

#### `@app.post("/article/generate")`
-   **Functionality:** Validates API Key -> Calls `orchestrator.generate_blog` -> Returns JSON response to user.

#### `@app.post("/campaign/run")`
-   **Functionality:** Validates inputs -> Calls `campaign_manager.run_campaign` -> Returns "Campaign Started" message.

---

## 10. Customizing for a New Company
The AI Blog Generator is designed to be highly generic. To adapt it for a specific brand or industry, follow these steps:

### Phase 1: Environment Setup (`.env`)
Update the following variables in your `.env` file:
- `BRAND_NAME`: Your company name.
- `INDUSTRY_NAME`: Your primary industry (e.g., "Solar Energy").
- `TARGET_CITY`: Primary city for local SEO.
- `TARGET_STATE`: Primary state/region.
- `DEFAULT_LINK_URL`: Your website's blog URL.
- `WORDPRESS_*`, `BLOGGER_*`, or `TUMBLR_*`: Credentials for your destination platform.

### Phase 2: Configuration Files (`data/config/`)
Modify these JSON files to refine the AI's behavior and targeting:

1.  **`categories.json`**: Update `product_categories` and `industry_categories` with terms relevant to your niche.
2.  **`categories_mapping.json`**: Map your category names to specific WordPress Category IDs.
3.  **`competitors.json`**: Add URLs of established blogs in your industry for topic inspiration.
4.  **`keywords.json`**: Provide seed keywords (`primary`, `curated`, `location`) for research.
5.  **`schema_map.json`**: Map product CSV column headers to logical labels (e.g., `feature_1` -> `Capacity`).
6.  **`templates.json`**: Customize HTML snippets to match your brand's voice.

### Phase 3: Product Data (`data/products.csv`)
If you want to generate "Brand-Focused" articles, populate this file with your product catalog.
- **Required Column:** `product_name`.
- **Custom Columns:** Add any columns defined in your `schema_map.json` (e.g., `price`, `material`).

### Phase 4: Branding Assets
- Update `src/image_client.py` if you have specific style requirements for your brand's imagery.
- Ensure your `open_graph` or Favicon settings on the target website are configured.
