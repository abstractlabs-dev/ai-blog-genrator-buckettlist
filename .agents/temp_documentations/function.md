# Core Codebase Functionality Directory

This document lists the critical components, modules, and functions of the AI Blog Generator and describes their purposes in simple terms.

---

## 1. Concurrent Campaign Components (`src/concurrent_manager.py`)

- **`ConcurrentCampaignManager`**: The top-level class orchestrating the multi-threaded concurrent publishing queue. It coordinates workers, manages exceptions, tracks global progress, and performs automated replacements for rejected articles.
- **`_generate_article_worker`**: A self-contained execution loop representing a single worker thread. It handles title generation, triggers the single-article pipeline, and returns execution metrics.
- **`_handle_worker_result`**: A callback executed upon completion of each worker task. It tracks overall successes, parses exceptions, logs campaign metrics, and schedules replenishment tasks with the rotation helper when a worker task skips or fails.

---

## 2. Agent Components (`src/agents.py`)

- **`ContentGeneratorAgent`**: The main interface for communicating with Google Gemini LLMs to write articles, create metadata (such as titles, slugs, excerpts, and meta descriptions), and generate FAQ sections. Now includes Yoast SEO guardrails: the meta description is automatically enforced to 120–155 characters (Yoast's green-light range), and the focus keyword is guaranteed to be non-empty by deriving a fallback from the article title when the LLM omits it.
- **`SEOEvaluator`**: Validates generated article HTML against a suite of 8 rigorous SEO metrics. It calculates sub-scores and aggregates them into a final 100-point score.
- **`normalize_for_kw_match`**: Sanitizes both target keywords and article text during evaluation (e.g. replacing `&` with `and`, stripping redundant whitespace, and converting characters to lowercase) to prevent false-negative score drops due to slight stylistic formatting differences.

---

## 3. Orchestration & Services (`src/services/`)

- **`BlogGeneratorOrchestrator.generate_blog` (`src/services/orchestrator.py`)**: The central pipeline governing a single article's lifecycle. It extracts keywords, manages duplicate-checking checks, runs the generation and SEO-evaluation feedback loop, applies anchor linking, writes to WordPress, and updates database records. Incorporates the new auto-healer to optimize draft quality before evaluation.
- **`SEOAutoHealer.heal` (`src/services/seo_auto_healer.py`)**: A pure Python utility class that programmatically processes generated HTML and metadata to correct minor SEO defects (word count, headers, bolding, lists, meta tags, and city-mention/booster keyword frequencies) to guarantee passing scores under strict quality guardrails without high-cost API retries.
- **`_extract_keywords_from_scraped_titles` (`src/services/orchestrator.py`)**: Extracts high-intent search terms based on active categories. Incorporates advanced deduplication and city-keyword matching to prevent redundant combinations such as `"in rishikesh in rishikesh"`.
- **`LinkingManager` (`src/services/linking_manager.py`)**: Matches anchors and inserts appropriate internal links based on sitemap mappings to ensure natural internal SEO optimization.

---

## 4. Client & Rate Limiting Components (`src/llm_client.py` & `src/image_client.py`)

- **`TokenBucketLimiter`**: A thread-safe, blocking token bucket rate limiter class that refuels lazily during access. Threads calling `acquire()` block safely if the rate limit is exceeded.
- **`get_limiter_for_model`**: A registry function that dynamically initializes and caches model-specific token buckets with safe defaults (e.g. 15 RPM for Flash, 2 RPM for Pro models on free-tier API Keys) or custom overrides from configuration.
- **`call_llm`**: Wraps the Google GenAI `generate_content` SDK method. Enforces proactive client-side rate limiting via model-specific token buckets and wraps requests in a highly resilient retry loop featuring exponential backoff and randomized jitter to smooth transient quota exhaustion errors.
- **`get_imagen_limiter` & `generate_blog_image`**: Applies client-side token bucket rate limiting and a retry loop with exponential backoff specifically to Imagen banner image generation.

---

## 5. Publishing Components (`src/publishers/`)

- **`TumblrPublisher`**: Connects to the Tumblr API and handles markdown-to-HTML conversion, tags generation from keywords, and publishing text posts.
- **`TumblrAccountSelector`**: Dynamically discovers and loads all configured Tumblr accounts from the environment by scanning `os.environ` dynamically (finding all `TUMBLR_BLOG_HOSTNAME{n}` indices), facilitating round-robin multi-account rotation without hardcoded limits.
