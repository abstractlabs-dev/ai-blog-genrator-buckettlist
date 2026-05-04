# Operations Guide: Running the AI Blog Generator

This guide covers everything you need to go from zero to publishing articles on WordPress, LinkedIn, and Medium.

---

## Quick Reference: All Commands

| What you want to do | Command |
|---|---|
| Generate 1 test article (no publish) | `python -m uvicorn api.main:app --reload` → POST `/article/batch` |
| Generate & publish to WordPress | POST `/campaign/publish` |
| Generate only (no publish) | POST `/campaign/run` |
| Publish to Blogger | POST `/campaign/publish/blogger` |
| Publish to Tumblr | POST `/campaign/publish/tumblr` |
| Generate LinkedIn + Medium JSONs from existing CSV | `python generate_social_exports.py` |
| Generate Blogger token (first time) | `python src/generate_token.py` |

---

## Step 1: Set Up Your `.env` File

Copy `example.env` to `.env` and fill in:

```bash
# Minimum required for article generation:
GOOGLE_AI_STUDIO_API_KEY=your_gemini_api_key_here

# Brand identity (used in every article):
BRAND_NAME=Bucketlist
INDUSTRY_NAME=adventure sports and tourism
TARGET_CITY=Rishikesh
TARGET_STATE=Uttarakhand
DEFAULT_LINK_URL=https://bucketlist.com

# For WordPress publishing:
WORDPRESS_BASE_URL=https://yourdomain.com
WORDPRESS_USERNAME=your_wp_username
WORDPRESS_TOKEN=xxxx xxxx xxxx xxxx xxxx xxxx

# Article quality settings:
MIN_WORD_COUNT=1200
MAX_WORD_COUNT=2000
IMAGE_GENERATION_RATIO=0.0     # Set to 1.0 to generate images (uses Imagen API)
```

> **Note:** Get your Google AI Studio key at [aistudio.google.com](https://aistudio.google.com) → API Keys.  
> Get your WordPress Token from: Dashboard → Users → Profile → Application Passwords.

---

## Step 2: Install Dependencies

```bash
pip install -r requirements.txt

# Optional: for semantic related-article linking in social exports
pip install sentence-transformers
```

---

## Step 3: Start the API Server

```bash
python -m uvicorn api.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs at `http://localhost:8000/docs`.

---

## Step 4: Generate a Sample Article (Test Run)

### Option A — Via Browser (Swagger UI)
1. Open `http://localhost:8000/docs`
2. Click **POST `/article/batch`** → Try it out
3. Set `num_articles: 1`
4. Click **Execute**

### Option B — Via curl
```bash
curl -X POST http://localhost:8000/article/batch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{"num_articles": 1}'
```

### Option C — Via Python (direct, no server needed)
```python
from src.config import Config
from src.services import BlogGeneratorOrchestrator

Config.ensure_directories()
orchestrator = BlogGeneratorOrchestrator()

# Generate 1 article — saves to data/database/articles.csv + data/output/json/
orchestrator.generate_batch_articles(num_articles=1, publish_to_wordpress=False)
```

**Where to find output:**
- Article JSON: `data/output/json/<article-title>.json`
- Article record: `data/database/articles.csv`
- Logs: in your terminal

---

## Step 5: Batch Processing

### Generate 50 articles, no publishing:
```bash
curl -X POST http://localhost:8000/campaign/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{"total_articles": 50, "max_workers": 3}'
```

### Generate AND publish to WordPress (recommended production flow):
```bash
curl -X POST http://localhost:8000/campaign/publish \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{"total_articles": 50, "max_workers": 3}'
```

> **`max_workers`**: Number of articles generated in parallel.  
> Start with `3` to be safe. Go up to `5` if your Gemini API tier supports it.  
> Higher = faster, but can hit API rate limits.

### Via Python directly:
```python
from src.config import Config
from src.services import BlogGeneratorOrchestrator
from src.concurrent_manager import ConcurrentCampaignManager

Config.ensure_directories()
orchestrator = BlogGeneratorOrchestrator()
manager = ConcurrentCampaignManager(orchestrator)

# Generate + publish to WordPress in parallel
manager.run_campaign(
    total_articles=50,
    max_workers=3,
    publish_to_wordpress=True,
    publish_to_blogger=False,
    publish_to_tumblr=False,
)
```

---

## Step 6: LinkedIn + Medium Exports

### Automatic (happens after every WordPress publish)
Every time an article is published to WordPress, the system **automatically** creates:
```
data/output/social/linkedin/YYYY-MM-DD_<slug>.json
data/output/social/medium/YYYY-MM-DD_<slug>.json
```
No extra step needed.

---

### Retroactive Export (for articles already in the CSV)
If you already have published articles in `articles.csv` and want to generate social exports for all of them at once:

```bash
python generate_social_exports.py
```

This reads all rows from `articles.csv` that have a `wp_published_url`, finds semantically related articles, and writes JSON files for every one.

---

### Manual Export (for a single article via Python)
```python
from src.publishers.social_exporter import SocialExporter
from src.publishers.related_article_finder import RelatedArticleFinder
from src.config import Config

# Find related articles
finder = RelatedArticleFinder(Config.CSV_PATH)
related = finder.find(
    title="Best Bungee Jumping in Rishikesh",
    short_description="Complete guide to bungee jumping in Rishikesh",
    top_k=3
)

# Generate JSON files
exporter = SocialExporter()
paths = exporter.export(
    article=article,           # your ArticleDraft object
    wp_url="https://yourdomain.com/blog/best-bungee-jumping-rishikesh",
    wp_slug="best-bungee-jumping-rishikesh",
    related_articles=related,
)
print("LinkedIn JSON:", paths["linkedin_path"])
print("Medium JSON:",   paths["medium_path"])
```

---

## Step 7: Using the Social Export JSONs

### LinkedIn
1. Open `data/output/social/linkedin/<filename>.json`
2. Copy the `"commentary"` field text
3. Paste it directly into LinkedIn's post composer
4. The article link card will auto-appear from the URL in the text
5. *(Optional)* Use the full JSON with LinkedIn's `/rest/posts` API by replacing `YOUR_MEMBER_ID`

### Medium
1. Open `data/output/social/medium/<filename>.json`
2. Go to medium.com → Write a story
3. Copy the `"content"` field HTML, paste into Medium editor
4. Set the title from the `"title"` field
5. Click `...` → More Settings → Advanced Settings
6. Check **"This story was originally published elsewhere"**
7. Paste the `"canonicalUrl"` value → Save canonical link
8. Add tags from the `"tags"` array (max 5)
9. Publish!

> The `_meta.instructions` field inside every JSON also contains these steps as a reminder.

---

## Recommended Full Workflow

```
Day 1 — Setup:
  1. Fill .env with keys
  2. pip install -r requirements.txt
  3. python src/generate_token.py  (Blogger only)
  4. python -m uvicorn api.main:app --reload

Day 2 — First Run:
  5. POST /article/batch  (1 article, no publish — verify output)
  6. Review data/output/json/<article>.json
  7. POST /campaign/publish  (5 articles, max_workers=2)
  8. Check data/output/social/ for LinkedIn + Medium JSONs

Production:
  9. POST /campaign/publish  (50–100 articles, max_workers=3–5)
  10. After each batch, run: python generate_social_exports.py
  11. Copy-paste JSONs to LinkedIn + Medium
```

---

## API Endpoint Summary

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/` | GET | No | Lists all endpoints |
| `/health` | GET | No | Health check |
| `/article/batch` | POST | Yes | Generate N articles (no publish) |
| `/campaign/run` | POST | Yes | Concurrent generate only |
| `/campaign/publish` | POST | Yes | Concurrent generate + WP publish |
| `/campaign/publish/blogger` | POST | Yes | Concurrent generate + Blogger |
| `/campaign/publish/tumblr` | POST | Yes | Concurrent generate + Tumblr |
| `/scraper/run` | POST | No | Run competitor scraper |

**Authentication:** Pass `X-API-Key: <your_key>` header. Set `API_KEY=` in `.env`.  
If `API_KEY` is empty, all endpoints work without a key.

---

## Output File Locations

| What | Where |
|---|---|
| Article database | `data/database/articles.csv` |
| Article JSON exports | `data/output/json/` |
| Generated images | `data/output/images/` |
| LinkedIn JSONs | `data/output/social/linkedin/` |
| Medium JSONs | `data/output/social/medium/` |
