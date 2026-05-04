# AI-Powered SEO Blog Generator

This project is a high-performance content generation engine designed to scrape competitor insights and produce thousands of high-quality, SEO-optimized blog articles autonomously.

## 📚 Documentation

- **[Code Documentation](documentation/CODE_DOCUMENTATION.md)** - Detailed, function-by-function explanation of the codebase
- **[Article Generation Process](documentation/ARTICLE_GENERATION_PROCESS.md)** - Complete guide to the two-step LLM workflow
- **[Environment Configuration](documentation/ENV_CONFIGURATION.md)** - Comprehensive `.env` variable reference

## 🚀 Quick Start (Docker)

1.  **Configure Environment**:
    Copy `example.env` to `.env` and fill in your API keys:
    ```bash
    cp example.env .env
    ```
    Ensure you set `GOOGLE_AI_STUDIO_API_KEY` and review the new settings like `MAX_TOTAL_ARTICLES`.

2.  **Start the System**:
    ```bash
    docker compose up -d --build
    ```

3.  **Check Status**:
    ```bash
    docker compose ps
    ```

4.  **Access API**:
    Open your browser to: `http://localhost:8000/docs`

---

## ⭐ Key Features

*   **Two-Step LLM Process**: 
    *   **Step 1**: AI generates creative, engaging content in plain text (configurable temperature)
    *   **Step 2**: AI converts to perfectly formatted HTML (fixed low temperature for consistency)
    *   Result: Publication-ready articles with zero HTML errors
*   **Dual-Agent Workflow**: One AI "Writer" and one AI "Editor" working in a loop to refine content until it scores 80/100+.
*   **Robust Campaign Mode**:
    *   **Auto-Replenish Queue**: If you ask for 1000 articles, the system ensures you get 1000 *successful* ones. If an article fails or is skipped, it automatically queues a replacement.
    *   **Safeguards**: Prevents infinite loops and infinite billing with smart retry limits.
*   **Detailed Analytics**:
    *   Tracks "Useful" tokens (what you published) vs "Wasted" tokens (failed retries).
    *   Provides a financial cost breakdown per campaign.
*   **Global Limits**: Set a hard cap (e.g., 5000 articles) in `.env` to prevent the database from growing indefinitely.
*   **Competitor Scraping**: Intelligent scraper that learns from competitor blogs to generate relevant titles.
*   **Multi-Platform Publishing**: Automatically publish to WordPress, Blogger, and Tumblr.

---

## ⚙️ Configuration Guide

The `.env` file is like the "control panel" of your blog generator. Here is what you need to change to make it work for your business:

### 1. Essential API Keys
*   **`GOOGLE_AI_STUDIO_API_KEY`**: This is your "Writer's Brain". You need a Google AI Studio (Gemini) API key to generate articles.
*   **`GOOGLE_AI_STUDIO_API_KEY`**: This is also your "Artist's Brain" for image generation (if enabled).
*   **`API_KEY`**: This is a security password you create for your own API server to prevent unauthorized access.

### 2. Branding (Tell the AI who you are)
*   **`BRAND_NAME`**: Your company name (e.g., "Generic Solutions").
*   **`INDUSTRY_NAME`**: What industry you are in (e.g., "Software Development").
*   **`BRAND_MENTION_RATIO`**: How often should the AI talk about your specific products vs. general advice? `0.25` means 25% of articles will be about your brand.
*   **`TARGET_CITY` & `TARGET_STATE`**: If you are a local business, tell the AI your location so it can mention it in the articles.
*   **`DEFAULT_LINK_URL` & `DEFAULT_LINK_TEXT`**: Where should the "Visit our website" buttons link to?

### 3. Campaign & SEO Settings
*   **`MAX_TOTAL_ARTICLES`**: A safety limit. The system will stop after reaching this many articles so you don't spend too much on API costs.
*   **`MIN_WORD_COUNT` & `MAX_WORD_COUNT`**: How long should each article be?
*   **`SEO_THRESHOLD`**: A quality score (0-100). The AI "Editor" will keep asking the "Writer" to improve the article until it reaches this score.
*   **`MAX_ARTICLE_RETRIES`**: How many times the AI should try to fix an article if it fails the SEO score.

### 4. Publishing
*   **`WORDPRESS_BASE_URL`, `WORDPRESS_USERNAME`, `WORDPRESS_TOKEN`**: Enter these to automatically publish the generated articles to your WordPress blog.

---

## 🛠️ How to Make This Work (Step-by-Step)

1.  **Key Setup**: Paste your OpenAI and Gemini keys into `.env`.
2.  **Product List**: Add your products to `data/products.csv` (one per line). These will be used for "Brand" articles.
3.  **Categories**: Update `data/config/categories.json` with the topics you want to write about.
4.  **Keywords**: Update `data/config/keywords.json` with words people search for in your industry.
5.  **Run**: Launch with Docker (`docker compose up -d`) and start a campaign via the API docs at `http://localhost:8000/docs`.

---

## 🛠️ Tech Stack

*   **Core**: Python 3.9+
*   **AI**: LiteLLM (OpenAI GPT-4), Google Gemini (Images)
*   **Web**: FastAPI
*   **Scraping**: Undetected Chromedriver, Selenium
*   **Vector DB**: Weaviate (Optional)

---

## 📈 How It Works

The orchestrator manages the entire workflow using a **revolutionary two-step LLM process**:

### 🎨 Article Generation Process (Two-Step LLM)

**Step 1: Creative Content Generation**
- The AI generates engaging, SEO-optimized content in plain text
- Uses configurable temperature from `.env` (default: 0.3) for creative writing
- Focuses purely on content quality without worrying about HTML formatting
- Keywords are naturally integrated, not stuffed

**Step 2: HTML Conversion**
- The AI converts plain text to perfectly formatted HTML
- Uses a fixed low temperature (0.05) for consistent, deterministic formatting
- Ensures all tags are properly closed and syntax is perfect
- No malformed HTML tags (e.g., `< b>` or `<h2 >`)

> **Why Two Steps?** This approach separates creative writing from technical formatting, resulting in:
> - ✅ Better content quality and engagement
> - ✅ Consistent, error-free HTML every time
> - ✅ Easier debugging and customization
> - ✅ Professional, publication-ready articles
>
> **Cost**: ~$0.024 per article (50% more than single-step, but worth it!)

📖 **For detailed information**, see [Article Generation Process Documentation](documentation/ARTICLE_GENERATION_PROCESS.md)

### 🔄 Complete Workflow

1.  **Initiation**: You start a campaign via the API (`POST /campaign/run`).
2.  **Scraping**: The system scrapes competitor blogs to learn trending topics and keywords.
3.  **Workers**: Use a thread pool to run multiple "Writers" at once.
4.  **Two-Step Drafting**:
    - **Step 1**: `ContentGeneratorAgent` generates creative plain text content
    - **Step 2**: Same agent converts it to perfectly formatted HTML
5.  **Review Loop**:
    - `SEOEvaluatorAgent` scores the article (0-100).
    - If score < `SEO_THRESHOLD`, it sends specific feedback back to the Writer.
    - This repeats until the score is high enough or max retries reached.
6.  **Tracking**: If a worker fails, the `ConcurrentCampaignManager` immediately spawns a new one to ensure your target count is met.
7.  **Publication**: Final articles are saved to `data/output/json`, logged in `data/database/articles.csv`, and optionally published to WordPress/Blogger/Tumblr.

### 📊 Quality Metrics

- **Word Count**: 1200-2000 words per article
- **SEO Score**: Minimum 80/100 (configurable)
- **HTML Quality**: 100% valid tags, proper hierarchy
- **Keyword Integration**: Natural placement in title, headings, body
- **Meta Data**: Optimized title (60 chars), description (155 chars)

---
