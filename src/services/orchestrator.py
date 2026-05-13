"""
Orchestrator Module
This module orchestrates the entire blog generation process, managing dependencies,
scraper invocation, LLM content generation, and database storage.
"""
import os
import re
import json
import logging
import random
import math
import io
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from PIL import Image
from src.config import Config
from src.image_client import generate_blog_image
from src.models import ArticleDraft, SEOReport, NoAvailableProductError, DuplicateArticleError, BlogGenerationError
from src.agents import ContentGeneratorAgent, SEOEvaluatorAgent  
from src.scraper import RobustScraper, SCRAPING_AVAILABLE
from src.llm_client import call_llm, LLM_AVAILABLE
from src.publishers import WordPressPublisher, BloggerPublisher, TumblrPublisher
from src.stats_manager import StatsManager
from utils.utils import CSVManager, VectorStoreManager
from .internal_linking import InternalLinkingService

logger = logging.getLogger(__name__)

class BlogGeneratorOrchestrator:
    def __init__(self):
        self.csv_manager = CSVManager()
        self.vector_store = VectorStoreManager(Config.VECTOR_STORE_PATH)
        self.content_generator = ContentGeneratorAgent()
        self.seo_evaluator = SEOEvaluatorAgent()
        self.internal_linking = InternalLinkingService(self.csv_manager, self.vector_store)
        self.covered_services = self.csv_manager.get_covered_products()
        self._industry_rotation = []
        self._service_category_rotation = []
        self.total_accumulated_cost = 0.0
        # Initialize publishers but don't force usage yet unless needed
        self.wp_publisher = WordPressPublisher()
        self.blogger_publisher = BloggerPublisher()
        self.tumblr_publisher = TumblrPublisher()

    def _create_safe_filename(self, title: str, max_length: int = 50) -> str:
        """Creates a safe filename from a title."""
        return re.sub(r'[^a-zA-Z0-9 ]', '', title).replace(' ', '_')[:max_length]

    def _extract_text_from_html(self, html_content: str) -> str:
        """Extracts plain text from HTML content."""
        return re.sub(r'<[^>]+>', ' ', html_content)

    def _contains_blocked_brand(self, text: str) -> bool:
        if not text or not isinstance(text, str):
            return False
        lowered = text.lower()
        for token in getattr(Config, "SCRAPER_BRAND_BLACKLIST", []):
            if token and token in lowered:
                return True
        return False

    def _sanitize_scraped_articles_location(self, articles_data: list[dict]) -> list[dict]:
        """Ensure scraped titles/keywords are strictly specific to the target city using LLM, with fallback.

        This takes the collected scraped titles/keywords, sends a compact sample to the
        LLM with strict location-only localization instructions, and rebuilds a sanitized
        list of article objects. If the LLM is unavailable or parsing fails, it falls back
        to a simple rule-based filter that drops obvious non-target-city mentions.
        """
        if not articles_data:
            return articles_data

        # Flatten sample titles/keywords
        sanitizer_ctx = {
            "titles": [
                a.get("title", "").strip()
                for a in articles_data
                if isinstance(a.get("title"), str) and a.get("title").strip()
            ],
            "kw_flat": []
        }
        for article_data in articles_data:
            kws = article_data.get("keywords") or []
            if isinstance(kws, list):
                for k in kws:
                    if isinstance(k, str) and k.strip():
                        sanitizer_ctx["kw_flat"].append(k.strip())

        # Rule-based fallback if LLM is not available
        if not LLM_AVAILABLE or not Config.GOOGLE_AI_STUDIO_API_KEY:
            logger.warning("LLM not available. Applying basic location filter for scraped keywords.")
            fallback_data = {
                "drop_tokens": Config.FORBIDDEN_KEYWORDS,
                "allowed_localities": [l.lower() for l in Config.LOCATION_KEYWORDS] + [
                    Config.TARGET_CITY.lower(), Config.TARGET_CITY.lower() + " " + Config.INDUSTRY_NAME.lower()
                ],
                "sanitized": []
            }

            def ok_token(token: str) -> bool:
                token_lower = token.lower()
                if any(dt in token_lower for dt in fallback_data["drop_tokens"]):
                    return False
                if any(al in token_lower for al in fallback_data["allowed_localities"]):
                    return True
                return Config.TARGET_CITY.lower() in token_lower

            for article_data in articles_data:
                title = article_data.get("title", "")
                kw_list = [k for k in (article_data.get("keywords") or []) if isinstance(k, str) and ok_token(k)]
                if title and isinstance(title, str) and ok_token(title):
                    fallback_data["sanitized"].append({"title": title, "keywords": kw_list})
            return fallback_data["sanitized"] or articles_data

        try:
            # Prepare inputs for the sanitizer prompt
            sanitizer_ctx["sample_titles"] = sanitizer_ctx["titles"][:30]
            # Limit keywords to a manageable but rich sample
            seen_kw = set()
            sanitizer_ctx["sample_keywords"] = []
            for k in sanitizer_ctx["kw_flat"]:
                keyword_lower = k.lower()
                if keyword_lower in seen_kw:
                    continue
                seen_kw.add(keyword_lower)
                sanitizer_ctx["sample_keywords"].append(k)
                if len(sanitizer_ctx["sample_keywords"]) >= 100:
                    break

            # Configure a broad sanitization prompt that specifically targets competitor brand removal
            # and ensures educational value, without over-restricting locations.

            prompt = f"""
            You are an SEO Strategist for the {Config.INDUSTRY_NAME}.
            I have a list of blog TITLES and KEYWORDS scraped from competitors.

            **TASK:**
            1. Clean the TITLES. Remove competitor brand names. Make them SIMPLE, DIRECT, and EASY TO UNDERSTAND for a general customer. Avoid complex jargon or overly long phrasing. Keep them broad (not tied to a specific city unless it's a brand-specific context).
            2. Clean the KEYWORDS. Remove brand names. Keep high-value industry terms.

            **INPUT:**
            Titles: {", ".join(sanitizer_ctx["sample_titles"])}
            Keywords: {", ".join(sanitizer_ctx["sample_keywords"])}

            **OUTPUT FORMAT:**
            TITLES:
            1. [Cleaned Title]
            2. [Cleaned Title]
            ...
            KEYWORDS:
            [keyword 1], [keyword 2], ...
            """

            logger.info("Calling LLM to clean and generalize scraped content.")
            content = call_llm(
                Config.MODEL_NAME,
                prompt,
                max_tokens=1800,
                temperature=Config.TEMPERATURE,
                presence_penalty=Config.PRESENCE_PENALTY,
                frequency_penalty=Config.FREQUENCY_PENALTY
            )

            # Parse response
            lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
            titles_start = None
            keywords_start = None
            for idx, line in enumerate(lines):
                if line.upper().startswith("TITLES"):
                    titles_start = idx + 1
                if line.upper().startswith("KEYWORDS"):
                    keywords_start = idx + 1
                    break

            sanitizer_ctx["new_titles"] = []
            if titles_start is not None:
                for line in lines[titles_start:keywords_start - 1 if keywords_start else len(lines)]:
                    cleaned = re.sub(r"^\d+\.\s*", "", line).strip()
                    if cleaned:
                        sanitizer_ctx["new_titles"].append(cleaned)

            sanitizer_ctx["new_keywords"] = []
            if keywords_start is not None and keywords_start < len(lines):
                kw_line = lines[keywords_start]
                for part in kw_line.split(","):
                    token = part.strip().strip("[]")
                    if token:
                        sanitizer_ctx["new_keywords"].append(token)

            if not sanitizer_ctx["new_titles"]:
                logger.warning("Sanitizer returned no titles; using original.")
                return articles_data

            sanitized_articles: list[dict] = []
            # We'll just create a pool of these cleaned titles and a shared keyword list
            # to be used as seeds later.
            for title_item in sanitizer_ctx["new_titles"]:
                sanitized_articles.append({"title": title_item, "keywords": sanitizer_ctx["new_keywords"]})

            return sanitized_articles
        except Exception as error:
            logger.warning("Sanitization failed: %s", error)
            return articles_data

    def _extract_keywords_from_scraped_titles(self, num_keywords: int = 15, category: Optional[str] = None) -> list:
        """Load keywords from both scraped data and the rich keywords.json configuration.

        This method combines keywords explicitly scraped from pages with high-intent
        keywords from the project's master keywords.json file based on the category.
        """
        try:
            keyword_list: list[str] = []

            # 1. Load from keywords.json (Priority)
            if hasattr(Config, "KEYWORDS_ALL") and Config.KEYWORDS_ALL:
                # Try to find a matching cluster in keywords.json
                cat_key = (category or "").lower().replace(" ", "_")
                # Handle common aliases/mappings
                mappings = {
                    "travel_tips": "spiritual_cultural",
                    "trekking": "trekking_hiking",
                    "hiking": "trekking_hiking",
                    "rafting": "river_rafting",
                    "bungee": "bungee_jumping"
                }
                mapped_key = mappings.get(cat_key, cat_key)
                
                cluster = Config.KEYWORDS_ALL.get(mapped_key)
                if cluster:
                    logger.info("Found keyword cluster for category: %s (mapped to %s)", category, mapped_key)
                    if isinstance(cluster, dict):
                        # Combine head terms, informational, and transactional keywords
                        keyword_list.extend(cluster.get("head_terms", []))
                        keyword_list.extend(cluster.get("informational", []))
                        keyword_list.extend(cluster.get("transactional", []))
                        # If it has a generic 'keywords' list
                        keyword_list.extend(cluster.get("keywords", []))
                    elif isinstance(cluster, list):
                        keyword_list.extend(cluster)

            # 2. Load from scraped_articles.json (Discovery)
            if os.path.exists(Config.SCRAPED_ARTICLES_JSON):
                with open(Config.SCRAPED_ARTICLES_JSON, 'r', encoding='utf-8') as file:
                    data = json.load(file)

                for obj in data:
                    kws = obj.get("keywords") or []
                    if isinstance(kws, str):
                        parts = [p.strip() for p in kws.split(",")]
                    else:
                        parts = [p.strip() for p in kws if isinstance(p, str)]
                    for part in parts:
                        if part:
                            keyword_list.append(part)

            # 3. Add mandatory/branded keywords
            if category:
                keyword_list.insert(0, category.lower())
                keyword_list.insert(1, f"{category.lower()} in {Config.TARGET_CITY.lower()}")
                keyword_list.insert(2, f"best {category.lower()} in rishikesh")
            
            keyword_list.append(Config.BRAND_NAME.lower())
            keyword_list.append("bucketlistt")

            # Remove duplicates and limit
            seen = set()
            unique_kws = []
            for kw in keyword_list:
                kw_low = kw.lower().strip()
                if kw_low and kw_low not in seen:
                    seen.add(kw_low)
                    unique_kws.append(kw)
            
            # Shuffle the middle part for variety, keep mandatory ones at start
            mandatory_count = 3 if category else 0
            mandatory = unique_kws[:mandatory_count]
            rest = unique_kws[mandatory_count:]
            random.shuffle(rest)
            
            final_keywords = (mandatory + rest)[:num_keywords]
            
            if not final_keywords:
                logger.warning("No keywords found. Using fallback.")
                return ["adventure sports", "rishikesh tourism", "things to do in rishikesh"]
                
            return final_keywords
                    "latest trends", Config.BRAND_NAME.lower(), "professional services"
                ]

            final_keywords = mandatory_keywords + [kw for kw in keyword_list if kw not in mandatory_keywords]

            # Optional: If category is strictly set, you might want to filter 'final_keywords' roughly
            # but that might be too aggressive. For now, prioritising the category in mandatory keywords helps.

            logger.info("Extracted %s keywords from scraped keyword data (Category: %s)", len(final_keywords), category)
            return final_keywords[:num_keywords]

        except Exception as error:
            logger.warning("Failed to extract keywords from scraped articles JSON: %s", error)

            # Fallback that respects category
            if category:
                base_kw = {category.lower(), f"{category.lower()} services", Config.TARGET_CITY.lower()}
            else:
                sample_size = min(8, len(Config.CURATED_KEYWORDS))
                base_kw = set(random.sample(Config.CURATED_KEYWORDS, sample_size))
                professional_services = f"professional services in {Config.TARGET_CITY.lower()}"
                base_kw.update({Config.TARGET_CITY.lower(), "industry", professional_services})

            return list(base_kw)

    def run_scraping(self):
        """Initializes and runs the robust web scraper, then saves the data."""
        if not SCRAPING_AVAILABLE:
            logger.error(
                "Scraping libraries not installed. Please run: pip install undetected-chromedriver beautifulsoup4"
            )
            return

        logger.info("Starting web scraping process with robust browser automation...")
        scraper = RobustScraper()
        scrape_state = {
            "raw_mode_enabled": getattr(Config, "RAW_SCRAPING_MODE", False),
            "site_stats": {},
            "articles_data": [],
            "titles_needing_ai": [],
            "title_to_site_map": {},
            "batch": {"tokens": 0, "cost": 0.0, "gen_count": 0},
            "titles": ([], []), # (raw_titles, site_keywords_map)
            "seen_titles": set(),
            "all_flattened_keywords": [],
            "seen_k": set(),
            "unique_scraped_keywords": [],
            "total_scraping_cost": 0.0
        }

        try:
            # Check for RAW mode override in .env
            try:
                if "RAW_SCRAPING_MODE" in os.environ:
                    scrape_state["raw_mode_enabled"] = os.environ.get("RAW_SCRAPING_MODE", "false").lower() == "true"
            except Exception:
                pass

            if scrape_state["raw_mode_enabled"]:
                logger.info("Using RAW mode scraping - no LLM calls")
                try:
                    scrape_state["titles"], keywords, scrape_state["site_stats"] = scraper.run_scraping_campaign_raw()
                except (AttributeError, ValueError):
                    logger.warning("RAW mode method error, using normal campaign fallback")
                    scrape_state["titles"], keywords, scrape_state["site_stats"] = scraper.run_scraping_campaign()
                    keywords = []  # Force empty keywords in RAW mode fallback
            else:
                logger.info("Using normal scraping with LLM calls")
                scrape_state["titles"], keywords, scrape_state["site_stats"] = scraper.run_scraping_campaign()

            if scrape_state["titles"]:
                # Build a mapping from source site -> list of keywords
                site_keywords_map = {site: kws for site, kws in keywords if kws}
                for keyword_item, source_site in (keywords or []):
                    src = (source_site or "").strip()
                    if not src:
                        continue
                    if self._contains_blocked_brand(keyword_item):
                        continue
                    if src not in site_keywords_map:
                        site_keywords_map[src] = []
                    site_keywords_map[src].append(keyword_item)

                # Build final articles data using a smart fallback for keywords
                # deduplicate and store
                for title, site in scrape_state["titles"]:
                    if title not in scrape_state["seen_titles"]:
                        scrape_state["articles_data"].append({
                            "title": title,
                            "keywords": site_keywords_map.get(site, []),
                            "site": site
                        })
                        scrape_state["titles_needing_ai"].append(title)
                        scrape_state["title_to_site_map"][title] = site
                        scrape_state["seen_titles"].add(title)

                logger.info("Scraping complete. Collected %d unique titles.", len(scrape_state["articles_data"]))

                # Step 2: Sanitize and localize (Only if not in RAW mode)
                if not scrape_state["raw_mode_enabled"]:
                    scrape_state["articles_data"] = self._sanitize_scraped_articles_location(
                        scrape_state["articles_data"]
                    )
                    scrape_state["titles_needing_ai"] = [a["title"] for a in scrape_state["articles_data"]]

                # Final check if we have any data
                if not scrape_state["articles_data"]:
                    logger.warning(
                        "No scraped articles found or all were filtered out. Scraping campaign unsuccessful."
                    )
                    scraper.close()
                    return

                # Step 3: Global keyword deduplication and aggregation
                # Ensure all scraped keywords across all sites are properly attributed and filtered
                for article in scrape_state["articles_data"]:
                    kws = article.get("keywords", [])
                    if isinstance(kws, list):
                        scrape_state["all_flattened_keywords"].extend(
                            [k.strip() for k in kws if isinstance(k, str) and k.strip()]
                        )

                # Remove duplicates, keeping order of discovery
                for keyword_str in scrape_state["all_flattened_keywords"]:
                    keyword_low = keyword_str.lower()
                    if keyword_low not in scrape_state["seen_k"]:
                        scrape_state["seen_k"].add(keyword_low)
                        scrape_state["unique_scraped_keywords"].append(keyword_str)

                logger.info(
                    "Aggregated %d unique scraped keywords from all campaigns.",
                    len(scrape_state["unique_scraped_keywords"])
                )

                # Update global stats from this run
                scrape_state["total_scraping_cost"] = sum(
                    s.get("cost", 0.0) for s in scrape_state["site_stats"].values()
                )
                self.total_accumulated_cost += scrape_state["total_scraping_cost"]
                # Save scraped keywords
                self.csv_manager.save_scraped_data(
                    Config.SCRAPED_KEYWORDS_CSV,
                    ["keyword"],
                    [[kw_item] for kw_item in scrape_state["unique_scraped_keywords"]]
                )
                # Save scraped articles summary (CSV)
                self.csv_manager.save_scraped_data(
                    Config.SCRAPED_ARTICLES_JSON.replace(".json", ".csv"), # Fallback to CSV for CSVManager
                    ["title", "site"],
                    [[a["title"], a["site"]] for a in scrape_state["articles_data"]]
                )

                logger.info(
                    "Starting AI keyword expansion batch for %d titles...",
                    len(scrape_state["titles_needing_ai"])
                )

                # AI keyword expansion batch - process titles sequentially as there's no batch method
                scrape_state["batch"] = {"articles": [], "cost": 0.0, "gen_count": 0}
                for title_to_expand in scrape_state["titles_needing_ai"]:
                    source_site = scrape_state["title_to_site_map"].get(title_to_expand, "Unknown")
                    expanded_kws = scraper.generate_keywords_from_title(title_to_expand, site_name=source_site)
                    scrape_state["batch"]["articles"].append({"title": title_to_expand, "keywords": expanded_kws})
                    scrape_state["batch"]["gen_count"] += 1

                logger.info(
                    "AI keyword expansion complete. Generated data for %d titles.",
                    len(scrape_state["batch"]["articles"])
                )
                scrape_state["batch"]["tokens"] = scraper.total_tokens
                scrape_state["batch"]["cost"] = scraper.total_cost

                # Merge AI-generated data (specifically keywords) back into our articles_data
                for ai_article in scrape_state["batch"]["articles"]:
                    for original in scrape_state["articles_data"]:
                        if ai_article["title"] == original["title"]:
                            original["keywords"] = ai_article.get("keywords", [])
                            break

                # Save articles with merged AI keywords as JSON for seed loading
                with open(Config.SCRAPED_ARTICLES_JSON, 'w', encoding='utf-8') as json_file:
                    json.dump(scrape_state["articles_data"], json_file, indent=4)

                logger.info(
                    "run_scraping complete. Costs: Scraping $%.4f, AI Expansion $%.4f. Total Generation: %d",
                    scrape_state["total_scraping_cost"],
                    scrape_state["batch"]["cost"],
                    scrape_state["batch"]["gen_count"]
                )
                scraper.close()
                # Prepare Consolidated Statistics Summary
                summary = [
                    f"\n{'='*110}",
                    f"{'SCRAPING CAMPAIGN SUMMARY':^110}",
                    f"{'='*110}",
                    (
                        f"{'SITE NAME':<30} | {'TITLES':<8} | {'KWS (EXT)':<10} | "
                        f"{'KWS (GEN)':<10} | {'AI TITLES':<10} | {'TOKENS':<10} | {'COST ($)':<10}"
                    ),
                    f"{'-'*110}"
                ]

                totals = {"titles": 0, "kws_ext": 0, "kws_gen": 0, "ai_titles": 0, "tokens": 0, "cost": 0.0}

                for site, stats in scrape_state["site_stats"].items():
                    summary.append(
                        f"{site:<30} | {stats.get('titles', 0):<8} | {'-':<10} | "
                        f"{stats.get('kws_generated', 0):<10} | {stats.get('titles_processed', 0):<10} | "
                        f"{stats.get('tokens', 0):<10} | ${stats.get('cost', 0.0):<9.4f}"
                    )
                    totals["titles"] += stats.get('titles', 0)
                    totals["kws_gen"] += stats.get('kws_generated', 0)
                    totals["ai_titles"] += stats.get('titles_processed', 0)
                    totals["tokens"] += stats.get('tokens', 0)
                    totals["cost"] += stats.get('cost', 0.0)

                if scrape_state["titles_needing_ai"]:
                    summary.append(
                        f"{'AI Batch (Fallback)':<30} | {'-':<8} | {'-':<10} | "
                        f"{scrape_state['batch']['gen_count']:<10} | {len(scrape_state['titles_needing_ai']):<10} | "
                        f"{scrape_state['batch']['tokens']:<10} | ${scrape_state['batch']['cost']:<9.4f}"
                    )
                    totals["kws_gen"] += scrape_state['batch']['gen_count']
                    totals["ai_titles"] += len(scrape_state['titles_needing_ai'])
                    totals["tokens"] += scrape_state['batch']['tokens']
                    totals["cost"] += scrape_state['batch']['cost']

                summary.append(f"{'-'*110}")
                summary.append(
                    f"{'GRAND TOTAL':<30} | {totals['titles']:<8} | {'-':<10} | "
                    f"{totals['kws_gen']:<10} | {totals['ai_titles']:<10} | "
                    f"{totals['tokens']:<10} | ${totals['cost']:<9.4f}"
                )
                summary.append(f"{'='*110}\n")

                # Log the entire summary at once
                for line in summary:
                    logger.info(line)
            else:
                logger.warning("No titles were scraped across all targets. Check logs for scraping failure details.")

            logger.info("Scraping process complete.")

        except Exception as error:
            print(f"An error occurred during the scraping campaign: {error}")
            logger.error("Scraping campaign failed: %s", error, exc_info=True)
        finally:
            if scraper:
                scraper.close()

    def generate_blog(self, title: str, reference_text: str = "", article_type: str = "generic",
                      override_keywords: Optional[list[str]] = None, category: Optional[str] = None,
                      publish_to_wordpress: bool = False,
                      publish_to_blogger: bool = False,
                      publish_to_tumblr: bool = False,
                      **kwargs) -> Tuple[ArticleDraft, SEOReport, Optional[Dict]]:
        if not title or not isinstance(title, str) or not title.strip():
            raise ValueError("Title must be a non-empty string.")

        logger.info("Starting blog generation for title: '%s' (Type: %s)", title, article_type)

        # Prepare blog generation context
        blog_ctx = {
            "category": category or Config.get_random_category(article_type),
            "target_keywords": [],
            "dupe_check": {"all": self.csv_manager.get_all_articles(), "existing_titles": set()},
            "best": {"article": None, "score": -1, "report": None, "product": None},
            "acc_stats": {
                "cost": 0.0,
                "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            }
        }

        logger.info("Category: %s", blog_ctx["category"])

        # Determine target keywords
        if override_keywords and isinstance(override_keywords, list) and override_keywords:
            blog_ctx["target_keywords"] = override_keywords[:15]
        else:
            blog_ctx["target_keywords"] = self._extract_keywords_from_scraped_titles(
                num_keywords=15,
                category=blog_ctx["category"]
            )

        logger.info("Target Keywords: %s", ', '.join(blog_ctx["target_keywords"]))

        # CRITICAL: For GENERIC articles, remove brand keywords to avoid -10 penalty
        if article_type == "generic":
            original_count = len(blog_ctx["target_keywords"])
            blog_ctx["target_keywords"] = [
                kw for kw in blog_ctx["target_keywords"]
                if Config.BRAND_NAME.lower() not in kw.lower()
            ]
            filtered_count = original_count - len(blog_ctx["target_keywords"])
            if filtered_count > 0:
                logger.info("Filtered %s brand/city keywords from generic article keywords", filtered_count)

        # STRICT DUPLICATE CHECK: Drop if title already exists in our database
        logger.info("Loaded %s existing articles for duplicate checking.", len(blog_ctx["dupe_check"]["all"]))

        # GLOBAL ARTICLE LIMIT CHECK
        if len(blog_ctx["dupe_check"]["all"]) >= Config.MAX_TOTAL_ARTICLES:
            error_msg = (
                f"Global Article Limit Reached: The total number of articles ({len(blog_ctx['dupe_check']['all'])}) "
                f"has reached the maximum configured limit of {Config.MAX_TOTAL_ARTICLES}. Generation stopped."
            )
            logger.error(error_msg)
            raise BlogGenerationError(error_msg)

        # Normalize titles for comparison (lowercase, strip, remove extra spaces)
        def normalize_title(text):
            return " ".join(text.strip().lower().split())

        blog_ctx["dupe_check"]["existing_titles"] = {
            normalize_title(a.get('title', ''))
            for a in blog_ctx["dupe_check"]["all"] if a.get('title')
        }

        current_normalized = normalize_title(title)
        if current_normalized in blog_ctx["dupe_check"]["existing_titles"]:
            error_msg = (
                f"Duplicate Title Detected: '{title}' (Normalized: '{current_normalized}') "
                "has already been generated. DROPPING request to prevent duplicates."
            )
            logger.warning(error_msg)
            raise DuplicateArticleError(error_msg)

        for iteration in range(1, Config.MAX_ITERATIONS + 1):
            logger.info("--- Iteration %s/%s ---", iteration, Config.MAX_ITERATIONS)

            temperature = Config.TEMPERATURE
            logger.info("Using fixed temperature=%.2f (from .env) for iteration %s", temperature, iteration)

            it_article, it_product = self.content_generator.generate_article(
                title=title,
                reference_text=reference_text,
                article_type=article_type,
                target_keywords=override_keywords or [],
                category=category,
                excluded_products=self.covered_services
            )

            # Accumulate cost/tokens from this generation attempt
            last_iteration_cost = 0.0
            last_iteration_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            if it_article.token_usage:
                last_iteration_cost = it_article.cost
                last_iteration_tokens = it_article.token_usage
                blog_ctx["acc_stats"]["cost"] += it_article.cost
                for key, value in it_article.token_usage.items():
                    if key in blog_ctx["acc_stats"]["tokens"]:
                        blog_ctx["acc_stats"]["tokens"][key] += value


            it_article = self._postprocess_article(it_article, blog_ctx["target_keywords"], article_type=article_type)
            it_article = self.internal_linking.add_internal_links(it_article)
            links_count = len(it_article.internal_links) if it_article.internal_links else 0
            logger.debug("Article internal links count: %d", links_count)
            it_report = self.seo_evaluator.evaluate_article(it_article, iteration, article_type=article_type)

            self._log_seo_metrics(it_report, it_article, iteration)

            if it_report.overall_score > blog_ctx["best"]["score"]:
                blog_ctx["best"].update({
                    "article": it_article,
                    "score": it_report.overall_score,
                    "report": it_report,
                    "product": it_product
                })

            word_count_ok = Config.MIN_WORD_COUNT <= it_article.word_count <= Config.MAX_WORD_COUNT
            if it_report.passed:
                # Update the article with the TOTAL accumulated cost/tokens before saving
                it_article.cost = blog_ctx["acc_stats"]["cost"]
                it_article.token_usage = blog_ctx["acc_stats"]["tokens"]

                # Also store "useful" vs "total" for campaign stats
                it_article.useful_cost = last_iteration_cost
                it_article.useful_tokens = last_iteration_tokens

                logger.info("SEO threshold reached. Saving and finalizing this article.")
                main_category = "Service Categories" if article_type == "brand" else "Industry Categories"
                # Set category attributes on article object for WordPress publishing
                it_article.category = blog_ctx["category"].strip() if blog_ctx["category"] else ""
                it_article.parent_category = main_category.strip() if main_category else ""
                self.save_artifacts(
                    it_article, it_report, article_type, blog_ctx["category"].strip(),
                    main_category.strip(), it_product,
                    publish_to_wordpress=publish_to_wordpress,
                    publish_to_blogger=publish_to_blogger,
                    publish_to_tumblr=publish_to_tumblr,
                    **kwargs
                )
                if it_product and it_product.get(Config.PRODUCT_ID_COL):
                    self.covered_services.append(it_product[Config.PRODUCT_ID_COL])

                # We return the best article which now has the accumulated total stats
                return it_article, it_report, it_product

            if iteration < Config.MAX_ITERATIONS:
                feedback = f"Previous attempt scored {it_report.overall_score}%. Key areas for improvement: "
                feedback += ". ".join(it_report.improvement_suggestions)
                if not word_count_ok:
                    feedback += (
                        f". CRITICAL: Adjust word count to be between {Config.MIN_WORD_COUNT}-{Config.MAX_WORD_COUNT}. "
                        f"Current is {it_article.word_count}."
                    )
                if article_type == "brand":
                    feedback += (
                        "\nFOLLOW THIS CHECKLIST STRICTLY: Use 1 <h1>, at least 3 <h2> and 2 <h3>, "
                        "10+ <p> paragraphs, at least one <ul>/<ol> with multiple <li>, use <strong> 3+ times, "
                        f"mention '{Config.TARGET_CITY}' 5+ times and include 2+ phrases like "
                        f"'best quality in {Config.TARGET_CITY}' or 'best service in {Config.TARGET_CITY}'."
                    )
                else:
                    feedback += (
                        "\nFOLLOW THIS CHECKLIST STRICTLY: Use 1 <h1>, at least 3 <h2> and 2 <h3>, "
                        "10+ <p> paragraphs, at least one <ul>/<ol> with multiple <li>, use <strong> 3+ times, "
                        "Maintain a COMPLETELY neutral industry focus. DO NOT mention specific cities or brands."
                    )
                prev_report_text = self._generate_seo_report_text(it_report, it_article)
                reference_text = (
                    f"{feedback}\n\n--- BEGIN PREVIOUS SEO REPORT ---\n{prev_report_text}\n"
                    f"--- END PREVIOUS SEO REPORT ---\n\n"
                    f"--- BEGIN PREVIOUS ARTICLE HTML ---\n{it_article.content_html}\n"
                    f"--- END PREVIOUS ARTICLE HTML ---\n"
                )

        if blog_ctx["best"]["article"] and blog_ctx["best"]["report"]:
            if not blog_ctx["best"]["report"].passed:
                error_msg = (
                    f"Article REJECTED: Did not meet SEO threshold of {Config.SEO_THRESHOLD}% "
                    f"(Best Score: {blog_ctx['best']['report'].overall_score}%). "
                    "This article will not be saved or published."
                )
                logger.error(error_msg)
                raise BlogGenerationError(error_msg)
            else:
                logger.info(
                    "Successfully generated article with score %s and word count %s.",
                    blog_ctx["best"]["report"].overall_score,
                    blog_ctx["best"]["article"].word_count
                )

            # Update best article with totals
            blog_ctx["best"]["article"].cost = blog_ctx["acc_stats"]["cost"]
            blog_ctx["best"]["article"].token_usage = blog_ctx["acc_stats"]["tokens"]
            blog_ctx["best"]["article"].useful_cost = last_iteration_cost
            blog_ctx["best"]["article"].useful_tokens = last_iteration_tokens

            main_category = "Product Categories" if article_type == "brand" else "Industry Categories"
            # Set category attributes on article object
            blog_ctx["best"]["article"].category = blog_ctx["category"].strip() if blog_ctx["category"] else ""
            blog_ctx["best"]["article"].parent_category = main_category.strip() if main_category else ""
            
            self.save_artifacts(
                blog_ctx["best"]["article"], blog_ctx["best"]["report"], article_type,
                blog_ctx["category"].strip(), main_category.strip(), blog_ctx["best"]["product"],
                publish_to_wordpress=publish_to_wordpress,
                publish_to_blogger=publish_to_blogger,
                publish_to_tumblr=publish_to_tumblr,
                **kwargs
            )
            return blog_ctx["best"]["article"], blog_ctx["best"]["report"], blog_ctx["best"]["product"]

        raise BlogGenerationError(
            "Failed to generate any valid article after all iterations.",
            total_tokens=blog_ctx["acc_stats"]["tokens"],
            total_cost=blog_ctx["acc_stats"]["cost"]
        )

        raise BlogGenerationError(
            "Failed to generate any valid article after all iterations.",
            total_tokens=blog_ctx["acc_stats"]["tokens"],
            total_cost=blog_ctx["acc_stats"]["cost"]
        )

    def save_artifacts(
        self, article: ArticleDraft, _report: SEOReport, article_type: str, parent_category: str,
        main_category: str, product: Optional[Dict] = None,
        publish_to_wordpress: bool = False,
        publish_to_blogger: bool = False,
        publish_to_tumblr: bool = False,
        **kwargs
    ):

        # --- CRITICAL FIX 1: Clean Markdown from Titles early ---
        def clean_markdown(text):
            if not text:
                return text
            # Remove edge Markdown symbols like ** or __ that LLMs sometimes include in titles
            return text.strip().strip('*').strip('_').strip()

        article.title = clean_markdown(article.title)
        if article.metadata:
            article.metadata.title = clean_markdown(article.metadata.title)

        # --- CRITICAL FIX 2: Generate and Sync Date early ---
        meta = {
            "start": datetime.strptime(Config.WEBSITE_START_DATE, "%Y-%m-%d"),
            "end": datetime.now(),
            "generated": None,
            "product_name": product.get(Config.PRODUCT_ID_COL) if product else None,
            "short_desc": article.metadata.description if article.metadata else "",
            "id": None
        }

        try:
            if meta["start"] < meta["end"]:
                diff = meta["end"] - meta["start"]
                meta["generated"] = meta["start"] + timedelta(
                    days=random.randint(0, diff.days),
                    seconds=random.randint(0, diff.seconds)
                )
            else:
                meta["generated"] = meta["end"]
        except Exception as error:
            logger.warning("Failed to randomize date: %s. Using current time.", error)
            meta["generated"] = datetime.now()

        # Keep the article object in sync for WordPress publisher
        article.generated_at = meta["generated"]

        # Save to database (now with cleaned title and synced date)
        meta["id"] = self.csv_manager.save_article(article, meta["short_desc"], product_name=meta["product_name"])
        self.vector_store.add_article(article, meta["id"])

        # Track generation stats
        StatsManager.increment_generated()

        img_ctx = {
            "path": "",
            "should_generate": False,
            "safe_filename": self._create_safe_filename(article.title),
            "random_value": random.random()  # Use true random instead of hash
        }

        # Use random sampling for image generation ratio
        if img_ctx["random_value"] < Config.IMAGE_GENERATION_RATIO:
            img_ctx["should_generate"] = True
            logger.info("Image will be generated for this article (random=%.3f < ratio=%s)",
                        img_ctx["random_value"], Config.IMAGE_GENERATION_RATIO)
        else:
            logger.info("Skipping image generation (random=%.3f >= ratio=%s)",
                        img_ctx["random_value"], Config.IMAGE_GENERATION_RATIO)

        # IMAGE SKIP LOGIC for Blogger and Tumblr
        if publish_to_blogger or publish_to_tumblr:
            logger.info("Forcing image generation skip for Blogger/Tumblr as requested.")
            img_ctx["should_generate"] = False

        if img_ctx["should_generate"]:
            try:
                # Prepare a clean title for the image generation to avoid confusing symbols
                clean_title = article.title.replace(':', ' -').replace('"', "'")
                clean_title = clean_title.replace('...', ' ').replace('..', ' ').replace('*', '')
                clean_title = " ".join(clean_title.split()).strip()

                # Get deterministic Rishikesh travel scene (no LLM call needed)
                visual_description = self._generate_visual_description(
                    clean_title,
                    category=blog_ctx.get("category", "")
                )
                logger.info("Travel scene for image: %s", visual_description[:80])

                if article_type == "brand":
                    prompt_styles = [
                        {
                            "name": "Rishikesh Adventure Brand Photography",
                            "prompt": (
                                f"A stunning, high-resolution travel photograph for {Config.BRAND_NAME} "
                                f"in Rishikesh, India: {visual_description}. "
                                "ABSOLUTE RULE: NO TEXT, NO WORDS, NO LOGOS, NO TYPOGRAPHY on the image. "
                                "Style: cinematic adventure travel photography. "
                                "Lighting: golden hour. Setting: real Himalayan landscape, Ganges river. "
                                "Quality: 8K, photorealistic, National Geographic style."
                            )
                        },
                        {
                            "name": "Rishikesh Premium Travel Visual",
                            "prompt": (
                                f"Premium adventure travel photography in Rishikesh, India showing: {visual_description}. "
                                "STRICT MANDATE: ZERO TEXT, ZERO WORDS, ZERO LETTERS on image. "
                                "The scene is photorealistic, cinematic, shot on location in the Himalayas "
                                "near the sacred Ganges river. Style: luxury travel magazine cover. "
                                "Colors: lush greens, river blues, Himalayan golden hour."
                            )
                        }
                    ]
                else:
                    prompt_styles = [
                        {
                            "name": "Rishikesh Editorial Travel Photography",
                            "prompt": (
                                f"An editorial travel photograph for a tourism blog about Rishikesh, India: "
                                f"{visual_description}. "
                                "CRITICAL RULE: ABSOLUTELY NO TEXT, WORDS, SIGNS, OR TYPOGRAPHY. Pure visual only. "
                                "Style: documentary travel photography. Real location, real people (if any) in natural poses. "
                                "Lighting: natural golden hour or sunrise. Quality: 8K, photorealistic."
                            )
                        },
                        {
                            "name": "Rishikesh Lifestyle Travel Scene",
                            "prompt": (
                                f"A breathtaking travel lifestyle photograph from Rishikesh, India: "
                                f"{visual_description}. "
                                "WARNING: NO TEXT, NO WORDS, NO OVERLAYS. Purely visual imagery. "
                                "Capture the authentic spirit of Rishikesh — adventure, spirituality, nature. "
                                "Colors: vibrant Himalayan greens, turquoise Ganges, golden light. "
                                "Quality: photorealistic, 8K, cinematic travel photography."
                            )
                        }
                    ]

                selected_style = random.choice(prompt_styles)
                logger.info("Selected Image Generation Style: %s", selected_style['name'])

                image_bytes, image_cost = generate_blog_image(selected_style["prompt"])

                # Update article cost with image generation cost
                article.cost += image_cost

                if image_bytes:
                    image_filename = f"{img_ctx['safe_filename']}.png"
                    image_full_path = os.path.join(Config.IMAGES_DIR, image_filename)

                    try:
                        # Open bytes as image and save as PNG to ensure correct format
                        img = Image.open(io.BytesIO(image_bytes))
                        img.save(image_full_path, format='PNG')
                        img_ctx["path"] = image_full_path
                        article.image_path = image_full_path  # Sync back to article object
                        logger.info("Generated and saved image to %s (Cost: $%.4f)", image_full_path, article.cost)
                    except Exception as error:
                        logger.error("Failed to convert image to PNG: %s. Saving raw bytes.", error)
                        with open(image_full_path, 'wb') as file_handle:
                            file_handle.write(image_bytes)
                        img_ctx["path"] = image_full_path
                        article.image_path = image_full_path  # Sync back to article object
                else:
                    logger.warning("Image generation returned no data.")

            except Exception as error:
                logger.error("Failed to generate/save image: %s", error)

        # 2. Save Consolidated JSON
        try:
            # Extract H1 title from article HTML to ensure consistency
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', article.content_html, re.IGNORECASE | re.DOTALL)
            consistent_title = h1_match.group(1).strip() if h1_match else article.title
            # Clean the title from any HTML tags that might be inside
            consistent_title = re.sub(r'<[^>]+>', '', consistent_title).strip()

            # Priority Swap: Prefer LLM-generated Meta Description for excerpt as it's more engaging
            excerpt = article.metadata.description or self._generate_excerpt_from_content(article.content_html)

            # Sync image description to article object for publication
            article.image_description = f"Image for the article '{consistent_title}' regarding {Config.INDUSTRY_NAME}."

            json_output = {
                "title": consistent_title,  # Use H1 from article content for consistency
                "generated_time": meta["generated"].strftime("%Y-%m-%d %H:%M:%S"),
                "meta_description": article.metadata.description,
                "article_content": article.content_html,
                "image_path": img_ctx["path"],
                "image_description": article.image_description,
                "excerpt": excerpt,
                "category": parent_category,
                "parent_category": main_category,
                "article_type": "Brand_specific" if article_type == "brand" else "Generic",
                "keywords": article.metadata.keywords,
                "faq_section": article.faq_section,
                "cost_usd": round(article.cost, 6)
            }


            json_path = os.path.join(Config.JSON_OUTPUT_DIR, f"{img_ctx['safe_filename']}.json")
            with open(json_path, 'w', encoding='utf-8') as file_handle:
                json.dump(json_output, file_handle, ensure_ascii=False, indent=2)

            logger.info("Saved article JSON to %s", json_path)

        except Exception as error:
            logger.warning("Failed to save consolidated JSON output: %s", error)

        # Pre-initialise WP tracking vars — used by social exporter below
        wp_link = ""
        wp_slug = ""

        # --- WORDPRESS PUBLISHING INTEGRATION ---
        if publish_to_wordpress:
            if self.wp_publisher.is_configured():
                try:
                    logger.info("Attempting to publish article with date %s to WordPress...", article.generated_at)
                    wp_result = self.wp_publisher.publish_article(article, image_path=img_ctx["path"])
                    if wp_result and wp_result.get('id'):
                        # Extract confirmed WP data from API response
                        wp_link  = wp_result.get('link', '')
                        wp_slug  = wp_result.get('slug', '')
                        wp_title = (wp_result.get('title') or {}).get('rendered', article.title)

                        article.is_published = True

                        # Write confirmed WP URL/slug/title back into CSV — this is the
                        # ground-truth record that prevents slug collisions in future runs
                        self.csv_manager.update_article_wp_data(
                            meta["id"], wp_link, wp_slug, wp_title
                        )

                        # Also register the confirmed WP slug into the in-memory registry
                        # so subsequent articles in THIS batch cannot collide with it
                        if hasattr(self.content_generator, 'slug_registry'):
                            self.content_generator.slug_registry.register(wp_slug)

                        # Warn if WordPress sanitized the title differently from ours
                        if wp_title and wp_title.strip() != article.title.strip():
                            logger.warning(
                                "WP TITLE MISMATCH: Expected '%s', WP rendered '%s'. "
                                "Check for special character stripping.",
                                article.title, wp_title
                            )

                        logger.info(
                            "Successfully published to WordPress! "
                            "Post ID: %s | Slug: %s | Link: %s",
                            wp_result.get('id'), wp_slug, wp_link
                        )
                    else:
                        logger.warning("WordPress publish returned no ID. Check logs.")
                except Exception as error:
                    logger.error("WordPress publishing failed: %s", error)
            else:
                logger.warning("Publishing requested but WordPress credentials are missing or incomplete in .env.")
        else:
            logger.info("Skipping WordPress publishing (publishing not requested).")

        # --- BLOGGER PUBLISHING INTEGRATION ---
        if publish_to_blogger:
            if self.blogger_publisher.is_configured():
                try:
                    logger.info("Attempting to publish article to Blogger...")
                    blogger_result = self.blogger_publisher.publish_article(
                        article,
                        _image_path=img_ctx["path"]
                    )
                    if blogger_result and blogger_result.get('id'):
                        blogger_url = blogger_result.get('url', '')
                        article.is_published = True
                        # Write confirmed Blogger URL + platform tag to CSV
                        self.csv_manager.update_article_blogger_data(meta["id"], blogger_url)
                        logger.info(
                            "Successfully published to Blogger! Post ID: %s | URL: %s",
                            blogger_result.get('id'), blogger_url
                        )
                    else:
                        logger.warning("Blogger publish returned no ID. Check logs.")
                except Exception as error:
                    logger.error("Blogger publishing failed: %s", error)
            else:
                logger.warning("Publishing requested but Blogger credentials are missing or incomplete in .env.")

        # --- TUMBLR PUBLISHING INTEGRATION ---
        if publish_to_tumblr:
            if self.tumblr_publisher.is_configured():
                try:
                    logger.info("Attempting to publish article to Tumblr...")
                    tumblr_result = self.tumblr_publisher.publish_article(
                        article,
                        _image_path=img_ctx["path"]
                    )
                    if tumblr_result and tumblr_result.get('id'):
                        tumblr_url = tumblr_result.get('url', '')
                        article.is_published = True
                        # Write confirmed Tumblr URL + platform tag to CSV
                        self.csv_manager.update_article_tumblr_data(meta["id"], tumblr_url)
                        logger.info(
                            "Successfully published to Tumblr! Post ID: %s | URL: %s",
                            tumblr_result.get('id'), tumblr_url
                        )
                    else:
                        logger.warning("Tumblr publish returned no ID. Check logs.")
                except Exception as error:
                    logger.error("Tumblr publishing failed: %s", error)
            else:
                logger.warning("Publishing requested but Tumblr credentials are missing or incomplete in .env.")

        logger.info("Artifacts processing complete for '%s'.", article.title)

    def _postprocess_article(
        self,
        article: ArticleDraft,
        target_keywords: list[str],
        article_type: str = "generic"
    ) -> ArticleDraft:
        try:
            # --- LAYER 1: NUCLEAR HTML & LEAKAGE REPAIR ---
            def strip_llm_artifacts(text: str) -> str:
                if not text:
                    return text

                text = re.sub(r"```[\s\S]*?```", "", text)
                text = re.sub(r"^\s*```.*$", "", text, flags=re.MULTILINE)
                text = text.replace("```", "")
                text = text.replace("`", "")

                text = re.sub(r"<\?php[\s\S]*?\?>", "", text, flags=re.IGNORECASE)
                text = re.sub(r"<\?[\s\S]*?\?>", "", text)

                text = re.sub(r";\s*echo\b[\s\S]*?(?:\n\s*\n|$)", "\n", text, flags=re.IGNORECASE)
                text = re.sub(r"^\s*['\"]\s*;\s*echo\b.*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
                text = re.sub(r"['\"]\s*;\s*echo\b.*", "", text, flags=re.IGNORECASE)

                text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
                text = re.sub(r"(?m)(?<!http:)(?<!https:)//.*$", "", text)

                text = text.replace("?>", "")

                return text.strip()

            def clean_nuclear_html(text: str) -> str:
                if not text:
                    return text

                text = strip_llm_artifacts(text)

                # 1. Leakage Stripper: Cut off any leaked instructions
                leak_marker = "### [!FINAL MANDATORY COMMAND]"
                if leak_marker in text:
                    text = text.split(leak_marker)[0]

                # 2. Bracket Fixer: Convert << into < and >> into >
                text = text.replace('<<', '<').replace('>>', '>')

                # 3. Nuclear Space and Character Stripper
                def strip_tag_junk(match):
                    raw = match.group(0)
                    # Strip all internal spaces and dots
                    clean = raw[1:-1].replace(' ', '').replace('.', '')
                    # Fix repeated characters inside the tag name: h33 -> h3
                    clean = re.sub(r'([hH][1-6])[1-6]+', r'\1', clean)
                    # Validate against known core tags
                    if re.match(r'^/?(h[1-6]|p|li|ul|ol|b|strong|blockquote|div)$', clean, re.I):
                        return f'<{clean}>'
                    return raw

                text = re.sub(r'<[^>]+>', strip_tag_junk, text)

                # 4. Strip Markdown bold artifacts (**)
                text = text.replace('**', '')

                # 5. Final fallback for h3. or p. hallucinations (outside brackets)
                text = re.sub(r'<(h[1-6]|p|li)\.', r'<\1>', text, flags=re.IGNORECASE)

                return text.strip()

            # --- LAYER 2: GLOBAL HEADER NORMALIZATION ---
            def normalize_headers(text: str) -> str:
                if not text:
                    return text
                # Force all deep headers (h4, h5, h6) to be <h3>
                text = re.sub(r'<(h[456])>(.*?)</\1>', r'<h3>\2</h3>', text, flags=re.IGNORECASE)
                text = re.sub(r'<(h[456])>', r'<h3>', text, flags=re.IGNORECASE)
                text = re.sub(r'</(h[456])>', r'</h3>', text, flags=re.IGNORECASE)
                return text

            article.content_html = normalize_headers(clean_nuclear_html(article.content_html))
            article.faq_section = normalize_headers(clean_nuclear_html(article.faq_section or ""))

            # Determine context for injections
            pp_ctx = {
                "content": article.content_html,
                "additions": [],
                "context_args": {
                    "brand_name": Config.BRAND_NAME if article_type == "brand" else "Professional Brand",
                    "target_city": Config.TARGET_CITY if article_type == "brand" else "your region"
                },
                "city_count": 0,
                "p_count": 0,
                "faq": article.faq_section or ""
            }

            # Inject generic industry insights if headers are missing
            if pp_ctx["content"].count('<h2>') < 3:
                tmpl = Config.TEMPLATES.get("missing_h2", "")
                pp_ctx["additions"].append(tmpl.format(**pp_ctx["context_args"]))
            if pp_ctx["content"].count('<h3>') < 2:
                tmpl = Config.TEMPLATES.get("missing_h3", "")
                pp_ctx["additions"].append(tmpl.format(**pp_ctx["context_args"]))

            pp_ctx["p_count"] = pp_ctx["content"].count('<p>')
            if pp_ctx["p_count"] < 10:
                needed = 10 - pp_ctx["p_count"]
                # Draw from a pool of varied Rishikesh paragraphs — never repeat the same one
                rishikesh_para_pool = [
                    f"<p>Rishikesh's position at the foothills of the Garhwal Himalayas gives it consistent river flow, reliable thermals for paragliding, and dramatic canyon geography for bungee jumping — all within a 20-kilometre radius of the city centre.</p>",
                    f"<p>Adventure activities in {Config.TARGET_CITY} are generally available year-round, with the peak seasons running September to November and March to May. Monsoon months (July–August) restrict water-based activities but do not halt all operations.</p>",
                    f"<p>Booking adventure activities in {Config.TARGET_CITY} at least 2–3 days in advance is strongly recommended during weekends and public holidays, when slots for bungee jumping, paragliding, and rafting fill up quickly.</p>",
                    f"<p>{Config.TARGET_CITY} has a well-developed adventure tourism infrastructure with certified operators, trained guides, and safety equipment maintained to international standards — making it one of India's safest adventure destinations.</p>",
                    f"<p>Whether you are travelling solo, as a couple, or with a group, {Config.TARGET_CITY} offers activity formats for every type of traveller. Combo packages that bundle multiple activities are a cost-effective way to maximise your experience in a single day.</p>",
                ]
                random.shuffle(rishikesh_para_pool)
                extra_ps = [rishikesh_para_pool[i % len(rishikesh_para_pool)] for i in range(needed)]
                pp_ctx["additions"].append("".join(extra_ps))

            if '<ul>' not in pp_ctx["content"] and '<ol>' not in pp_ctx["content"]:
                list_html = Config.TEMPLATES.get("missing_list", "").format(**pp_ctx["context_args"])
                pp_ctx["additions"].append(list_html)

            pp_ctx["strong_count"] = pp_ctx["content"].count('<strong>') + pp_ctx["content"].count('<b>')
            strong_needed = 3 - pp_ctx["strong_count"]
            if strong_needed > 0 and target_keywords:
                logger.info(
                    "Optimizing article content for %s with SEO feedback...",
                    pp_ctx.get("brand_name", Config.BRAND_NAME)
                )
                for keyword in target_keywords[:strong_needed]:
                    if isinstance(keyword, str) and keyword in pp_ctx["content"]:
                        pp_ctx["content"] = pp_ctx["content"].replace(keyword, f"<strong>{keyword}</strong>", 1)

            pp_ctx["city_count"] = pp_ctx["content"].lower().count(Config.TARGET_CITY.lower())

            if pp_ctx["city_count"] < 4:
                # Append standalone, grammatically complete Rishikesh sentences
                # as new <p> tags — never mutate inside existing paragraphs
                location_sentences = [
                    f"<p>{Config.TARGET_CITY}'s Himalayan foothills setting creates ideal conditions for adventure sports, with consistent river flow for rafting and stable thermals for paragliding available through most of the year.</p>",
                    f"<p>Getting to {Config.TARGET_CITY} is straightforward: the nearest airport is Jolly Grant (Dehradun), approximately 35 km away, and Haridwar railway station (25 km) connects to all major Indian cities via frequent services.</p>",
                    f"<p>The adventure sports zone in {Config.TARGET_CITY} runs from Tapovan to Shivpuri — a 15-km stretch along the Ganga that concentrates most activity operators, camps, and booking offices.</p>",
                    f"<p>For travellers planning their first visit to {Config.TARGET_CITY}, a 2-day itinerary is typically sufficient to experience the flagship activities: river rafting on the Shivpuri stretch and a bungee jump or paragliding session the following morning.</p>",
                ]
                needed_city = 4 - pp_ctx["city_count"]
                for i in range(min(needed_city, len(location_sentences))):
                    pp_ctx["additions"].append(location_sentences[i])

            if target_keywords:
                pp_ctx["infused"] = ", ".join(sorted({kw for kw in target_keywords if isinstance(kw, str)}))
                pp_ctx["tmpl"] = Config.TEMPLATES.get("summary_paragraph", "")

                # Context-aware summary paragraph
                pp_ctx["summary"] = pp_ctx["tmpl"].format(
                    infused_keywords=pp_ctx["infused"],
                    **pp_ctx["context_args"]
                )

                pp_ctx["additions"].append(pp_ctx["summary"])

            if pp_ctx["additions"]:
                pp_ctx["content"] += "".join(pp_ctx["additions"])

            pp_ctx["text_content"] = self._extract_text_from_html(pp_ctx["content"])
            pp_ctx["word_count"] = len(re.findall(r'\b\w+\b', pp_ctx["text_content"]))

            pp_ctx["h3_in_faq"] = pp_ctx["faq"].count('<h3>')
            if pp_ctx["h3_in_faq"] < 3:
                pp_ctx["missing"] = 3 - pp_ctx["h3_in_faq"]
                pp_ctx["extra"] = []
                for _ in range(pp_ctx["missing"]):
                    pp_ctx["tmpl"] = Config.TEMPLATES.get("faq_item", "")
                    pp_ctx["extra"].append(pp_ctx["tmpl"].format(**pp_ctx["context_args"]))
                pp_ctx["faq"] += "".join(pp_ctx["extra"])

            try:
                dedupe_ctx = {"faq": pp_ctx["faq"], "items": [], "seen": set()}
                match = re.search(r"^(.*?)(<h3[\s\S]*)$", dedupe_ctx["faq"], flags=re.IGNORECASE)
                dedupe_ctx["prefix"] = match.group(1) if match else ""
                dedupe_ctx["rest"] = match.group(2) if match else dedupe_ctx["faq"]

                pairs = re.findall(
                    r"<h3>(.*?)</h3>\s*<p>(.*?)</p>",
                    dedupe_ctx["rest"],
                    flags=re.IGNORECASE | re.DOTALL,
                )

                for question, answer in pairs:
                    key = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", question)).strip().lower()
                    if key and key not in dedupe_ctx["seen"]:
                        dedupe_ctx["seen"].add(key)
                        dedupe_ctx["items"].append((question.strip(), answer.strip()))

                if dedupe_ctx["items"]:
                    closing = "</div>" if re.search(r"</div>\s*$", dedupe_ctx["faq"], flags=re.IGNORECASE) else ""
                    pp_ctx["faq"] = (
                        dedupe_ctx["prefix"]
                        + "".join([f"<h3>{question}</h3><p>{answer}</p>" for question, answer in dedupe_ctx["items"]])
                        + closing
                    )
            except Exception as _:
                pass
            article.content_html = pp_ctx["content"]
            article.word_count = pp_ctx["word_count"]
            article.faq_section = pp_ctx["faq"]
            return article
        except Exception as error:
            logger.warning("Post-processing failed: %s", error)
            return article

    # ── Rishikesh Travel Scene Map ────────────────────────────────────────────
    # Deterministic category → visual scene lookup for image generation.
    # Eliminates the _generate_visual_description() LLM call (saves tokens).
    # Scenes are photorealistic, location-specific, and text-free.
    RISHIKESH_TRAVEL_SCENES: dict = {
        # Adventure — Product Categories
        "bungee":       "thrill-seeker mid-jump from a cliff bridge over the turquoise Ganges river gorge in Rishikesh, lush green Himalayan mountains in background, dramatic golden hour light, action photography",
        "bungy":        "thrill-seeker mid-jump from a cliff bridge over the turquoise Ganges river gorge in Rishikesh, lush green Himalayan mountains in background, dramatic golden hour light, action photography",
        "jump":         "adventure cliff jumper soaring over the crystal-clear Ganges river near Rishikesh, rocky canyon walls, blue sky, high altitude",
        "rafting":      "adventurers navigating wild white-water rapids on the sacred Ganges river in Rishikesh, surrounded by rocky cliffs and dense green jungle, action photography, water splashing",
        "river":        "scenic panoramic view of the Ganges river winding through rocky Himalayan terrain near Rishikesh, emerald green water, forested hills",
        "paragliding":  "paraglider soaring high above the lush Himalayan valleys near Rishikesh, river Ganges a silver ribbon far below, blue sky with white clouds, freedom",
        "camping":      "idyllic riverside campsite with orange tents and a warm bonfire on the Ganges riverbank near Rishikesh, Himalayan foothills silhouetted at dusk, golden light",
        "cycling":      "mountain biker on a misty forest trail through the Himalayan foothills near Rishikesh, dense green jungle, morning light filtering through trees",
        "kayaking":     "solo kayaker on calm emerald Ganges waters near Rishikesh, rocky forested riverbanks, peaceful morning atmosphere",
        "cliff":        "dramatic rocky cliff over the Ganges river near Rishikesh, clear turquoise pool below, lush green trees clinging to stone walls",
        "swing":        "adventure giant swing launching over a deep Himalayan river valley near Rishikesh, sunrise light, dramatic mountain backdrop",
        "zipline":      "zipline cable stretching over a jungle river valley near Rishikesh, adventurer flying through the air, green Himalayan hills",
        "trekking":     "trekkers on a winding mountain trail through misty Himalayan forest near Rishikesh, fog in the valley below, dramatic landscape",
        "trek":         "trekkers on a winding mountain trail through misty Himalayan forest near Rishikesh, fog in the valley below, dramatic landscape",
        "hiking":       "hikers ascending a lush green Himalayan ridge overlooking Rishikesh and the Ganges valley below, clear blue sky",
        # Lifestyle — Industry Categories
        "hotel":        "luxury boutique resort perched above the Ganges river with Himalayan mountain views, infinity pool, sunrise golden light, premium travel photography",
        "hostel":       "vibrant backpacker hostel rooftop terrace overlooking the Ganges river in Rishikesh, fairy lights, young travelers, warm dusk atmosphere",
        "restaurant":   "charming riverside outdoor cafe in Rishikesh at sunset, Indian food spread on wooden tables, golden light reflecting on the Ganges, mountain backdrop",
        "food":         "colorful spread of traditional Indian street food near the Ganges ghats in Rishikesh, vibrant spices, chai tea, warm evening light",
        "yoga":         "yoga practitioner in warrior pose on a wooden riverside deck above the Ganges in Rishikesh at sunrise, mist rising from the sacred river, Himalayan peaks",
        "meditation":   "peaceful meditation garden on a Ganges riverbank in Rishikesh at dawn, incense smoke curling in morning light, ancient stone ghats, spiritual tranquility",
        "ashram":       "ancient riverside ashram with stone architecture on the Ganges bank in Rishikesh, saffron-robed monks, incense smoke, timeless spiritual atmosphere",
        "spa":          "serene Ayurvedic spa with river view in Rishikesh, natural stone interior, candles, traditional Indian healing aesthetic",
        "waterfall":    "hidden waterfall cascading into a turquoise pool in lush Himalayan jungle near Rishikesh, crystal-clear water, dappled morning sunlight",
        "temple":       "ancient Hindu temple with marigold offerings on the Ganges ghats in Rishikesh, golden hour reflection on sacred water, devotees in distance",
        "market":       "vibrant local market in Rishikesh with colorful spices, handicrafts, prayer flags, traditional stalls, bustling street photography",
        "shopping":     "colorful handicraft and souvenir shops lining the streets near Lakshman Jhula bridge in Rishikesh, prayer flags overhead, warm sunlight",
        "places":       "aerial drone view of Rishikesh city nestled in Himalayan foothills, Lakshman Jhula suspension bridge over the emerald Ganges, lush green landscape",
        "things":       "vibrant photographic collage-style scene: white-water rafting, bungee jumping silhouette, yoga at sunrise, ancient temple, all set against Rishikesh Himalayan backdrop",
        "itinerary":    "aerial panoramic view of Rishikesh valley — river, mountains, temples, adventure activities — golden hour travel photography",
        "travel":       "dramatic aerial view of Rishikesh nestled in the Himalayan foothills with the sacred Ganges river curving through the valley, lush green hills, blue sky",
        "guide":        "traveler with backpack standing on Lakshman Jhula bridge in Rishikesh overlooking the Ganges river and mountains, adventure travel photography",
        "safety":       "adventure safety equipment — helmets, harnesses, life jackets — laid out on a rocky Ganges riverbank in Rishikesh, professional outdoor setting",
        "cost":         "traveler planning a budget trip in a cozy cafe overlooking the Ganges in Rishikesh, maps and notebooks, travel photography",
        "price":        "traveler planning a budget trip in a cozy cafe overlooking the Ganges in Rishikesh, maps and notebooks, travel photography",
        "budget":       "backpacker enjoying sunset views over the Ganges from a hostel rooftop in Rishikesh, simple authentic travel lifestyle",
        "weekend":      "friends enjoying a weekend adventure in Rishikesh — kayaking, yoga, river walk — golden hour Himalayan backdrop",
        # Default fallback
        "default":      "scenic aerial view of Rishikesh — India's adventure capital — nestled in the Himalayan foothills with the sacred Ganges river winding through, lush green landscape, golden hour",
    }

    def _get_travel_scene(self, title: str, category: str = "") -> str:
        """
        Returns a photorealistic Rishikesh travel scene description for image generation.
        No LLM call needed — purely deterministic keyword matching against RISHIKESH_TRAVEL_SCENES.
        """
        # Build a search string combining title + category (lowercased)
        search_str = f"{title} {category}".lower()

        # Find the best matching scene key (longest keyword match wins)
        best_key = "default"
        best_key_len = 0
        for key in self.RISHIKESH_TRAVEL_SCENES:
            if key != "default" and key in search_str and len(key) > best_key_len:
                best_key = key
                best_key_len = len(key)

        scene = self.RISHIKESH_TRAVEL_SCENES[best_key]
        logger.info("Travel scene selected: key='%s' for title='%s'", best_key, title[:50])
        return scene

    def _generate_visual_description(self, title: str, category: str = "") -> str:
        """
        Returns a Rishikesh travel scene for image generation.
        Uses the deterministic RISHIKESH_TRAVEL_SCENES lookup — no LLM call.
        This is faster, cheaper, and produces more consistent travel imagery
        than asking the LLM to 'describe a professional scene'.
        """
        return self._get_travel_scene(title, category)

    def _log_seo_metrics(self, report: SEOReport, article: ArticleDraft, iteration: int):
        status = "✅ PASSED" if report.passed else "❌ FAILED"
        logger.info("┌%s┐", '─'*60)
        logger.info(
            "│ ITERATION %s SEO REPORT - Score: %s/100 | Status: %s",
            iteration, report.overall_score, status
        )
        logger.info("│ Word Count: %s | Cost: $%.4f", article.word_count, article.cost)
        logger.info("├%s┤", '─'*60)
        for metric in report.metrics:
            symbol = "✓" if metric.score >= (metric.max_score * 0.7) else "!"
            logger.info(
                "│ %s %-25s | %2s/%-2s | %s...",
                symbol, metric.name, metric.score, metric.max_score, metric.feedback[:30]
            )
        logger.info("└%s┘", '─'*60)

    def _generate_seo_report_text(self, report: SEOReport, article: ArticleDraft) -> str:
        """Generate SEO report text for successful articles and iteration feedback."""
        text = f"SEO REPORT FOR: {article.title}\n{'='*50}\n"
        text += f"Final Score: {report.overall_score}/100 {'(PASSED)' if report.passed else '(FAILED)'}\n"
        text += f"Word Count: {article.word_count}\n"
        text += f"URL: {article.metadata.canonical_url}\n\n"
        text += "--- DETAILED METRICS ---\n"
        for metric in report.metrics:
            text += f"- {metric.name}: {metric.score}/{metric.max_score}\n  Feedback: {metric.feedback}\n\n"
        return text

    def generate_batch_articles(
        self,
        num_articles: int = 5,
        publish_to_wordpress: bool = False,
        publish_to_blogger: bool = False,
        publish_to_tumblr: bool = False,
    ):
        logger.info("Generating a batch of %s articles in Coverage Mode.", num_articles)

        # Determine how many brand-specific vs industry-generic articles to generate
        batch_plan = {
            "num_brand": math.ceil(num_articles * Config.BRAND_MENTION_RATIO),
            "num_generic": 0,
            "article_types": [],
            "metadata": []
        }
        batch_plan["num_generic"] = num_articles - batch_plan["num_brand"]
        batch_plan["article_types"] = ['brand'] * batch_plan["num_brand"] + ['generic'] * batch_plan["num_generic"]
        random.shuffle(batch_plan["article_types"])

        logger.info(
            "Batch plan: %s brand-specific, %s industry-generic articles.",
            batch_plan["num_brand"], batch_plan["num_generic"]
        )

        # Prepare Coverage Mode Rotations
        if not self._industry_rotation:
            self._industry_rotation = list(Config.INDUSTRY_CATEGORIES) or [Config.get_random_category("generic")]
            random.shuffle(self._industry_rotation)

        if not self._service_category_rotation:
            self._service_category_rotation = list(Config.PRODUCT_CATEGORIES) or [Config.get_random_category("brand")]
            random.shuffle(self._service_category_rotation)

        # Load scraped articles for seeds
        seeds = {"articles": [], "pool": []}
        try:
            if os.path.exists(Config.SCRAPED_ARTICLES_JSON):
                with open(Config.SCRAPED_ARTICLES_JSON, 'r', encoding='utf-8') as file_handle:
                    seeds["articles"] = json.load(file_handle)
        except Exception as error:
            logger.warning("Failed loading scraped articles for batch generation: %s", error)

        # Prepare unique seed articles to avoid repetitive topics
        seeds["pool"] = list(seeds["articles"])
        random.shuffle(seeds["pool"])

        for i, article_type in enumerate(batch_plan["article_types"], 1):
            print(f"\n--- Generating article {i}/{num_articles} (Type: {article_type}) ---")
            try:
                # Determine seed title, keywords, and category for generic articles
                seed_info = {
                    "title": "",
                    "keywords": None,
                    "category": None
                }
                if article_type == "generic" and seeds["pool"]:
                    # Pick a unique seed from the shuffled pool
                    seeds["obj"] = seeds["pool"].pop(0)
                    seed_info["title"] = seeds["obj"].get("title", "")

                    # For generic articles, let the seed's category (if available) drive the choice
                    # otherwise use a random industry category that fits the seed title
                    seeds["scraped_cat"] = seeds["obj"].get("category")
                    if seeds["scraped_cat"]:
                        seed_info["category"] = seeds["scraped_cat"]
                    else:
                        # If no category in seed, use the industry rotation but inform the AI to adapt it
                        if not self._industry_rotation:
                            self._industry_rotation = list(Config.INDUSTRY_CATEGORIES) or [Config.get_random_category("generic")]
                            random.shuffle(self._industry_rotation)
                        seed_info["category"] = self._industry_rotation.pop(0)

                    # Also use keywords from the seed if available
                    seeds["kws"] = seeds["obj"].get("keywords")
                    if seeds["kws"] and isinstance(seeds["kws"], list):
                        seed_info["keywords"] = seeds["kws"][:15]

                    logger.info("Using Seed: '%s' | Category: %s", seed_info["title"], seed_info["category"])

                    # Refill pool if empty
                    if not seeds["pool"]:
                        seeds["pool"] = list(seeds["articles"])
                        random.shuffle(seeds["pool"])
                elif article_type == "generic":
                    if not self._industry_rotation:
                        self._industry_rotation = list(Config.INDUSTRY_CATEGORIES) or [Config.get_random_category("generic")]
                        random.shuffle(self._industry_rotation)
                    seed_info["category"] = self._industry_rotation.pop(0)
                else:
                    # For Brand-specific, use the product category rotation
                    if not self._service_category_rotation:
                        self._service_category_rotation = list(Config.PRODUCT_CATEGORIES) or [Config.get_random_category("brand")]
                        random.shuffle(self._service_category_rotation)
                    seed_info["category"] = self._service_category_rotation.pop(0)

                # Generate the optimized title (rephrased if seed exists)
                batch_res = {
                    "titles": self.content_generator.generate_titles(
                        num=1,
                        article_type=article_type,
                        category=seed_info["category"],
                        seed_title=seed_info["title"]
                    ),
                    "article": None, "report": None, "product": None
                }

                if not batch_res["titles"]:
                    logger.error("Could not generate a title for a %s article. Skipping.", article_type)
                    continue

                batch_res["article"], batch_res["report"], batch_res["product"] = self.generate_blog(
                    batch_res["titles"][0],
                    article_type=article_type,
                    override_keywords=seed_info["keywords"],
                    category=seed_info["category"],
                    publish_to_wordpress=publish_to_wordpress,
                    publish_to_blogger=publish_to_blogger,
                    publish_to_tumblr=publish_to_tumblr,
                )

                batch_plan["metadata"].append({
                    "title": batch_res["article"].title,
                    "type": "Brand-Specific" if article_type == "brand" else "Industry-Generic",
                    "category": batch_res["article"].category,
                    "parent_category": "Service Categories" if article_type == "brand" else "Industry Categories",
                    "filename": self._create_safe_filename(batch_res["article"].title) + ".json",
                    "product": batch_res["product"].get(Config.PRODUCT_ID_COL) if batch_res["product"] else "N/A",
                    "date": batch_res["article"].generated_at.strftime("%Y-%m-%d %H:%M:%S")
                })
                print(f"Success! Final SEO Score: {batch_res['report'].overall_score}/100, "
                      f"Category: {batch_res['article'].category}")

            except NoAvailableProductError as error:
                print(f"Skipped {Config.BRAND_NAME}-centric article: {error}.")
                continue
            except DuplicateArticleError as error:
                print(f"SKIPPING DUPLICATE: {error}")
                continue
            except Exception as error:
                print(f"Failed to generate article for type '{article_type}': {error}")
                logger.error("Failed to generate article in batch: %s", error, exc_info=True)
                continue

        if batch_plan["metadata"]:
            logger.info("Batch generation complete. %s articles generated.", len(batch_plan["metadata"]))

    def _generate_excerpt_from_content(self, html_content: str, max_chars: int = 300) -> str:
        """Extract 2-3 sentences from the intro paragraph as excerpt."""
        try:
            # Remove HTML tags to get plain text
            text = re.sub(r'<[^>]+>', '', html_content)
            # Clean up extra whitespace
            text = re.sub(r'\s+', ' ', text).strip()

            # Split into sentences (simple approach)
            sentences = re.split(r'(?<=[.!?])\s+', text)

            # Filter out common generic introductory sentences
            generic_starters = [
                "introduction to", "welcome to", "in this article", "in this blog",
                "when it comes to", "in the world of", "today we will", "looking for"
            ]
            sentences = [
                s for s in sentences
                if not any(s.lower().strip().startswith(prefix) for prefix in generic_starters)
            ]

            # Take first 2-3 sentences
            excerpt_sentences = []
            char_count = 0
            for sentence in sentences[:5]:  # Check first 5 filtered sentences
                if char_count + len(sentence) <= max_chars:
                    excerpt_sentences.append(sentence)
                    char_count += len(sentence) + 1
                else:
                    break

                # Stop after 2-3 sentences
                if len(excerpt_sentences) >= 2 and char_count >= 150:
                    break

            excerpt = ' '.join(excerpt_sentences)

            # Fallback if excerpt is too short
            if len(excerpt) < 100:
                excerpt = text[:max_chars].rsplit(' ', 1)[0] + '...'

            return excerpt
        except Exception as error:
            logger.warning("Failed to generate excerpt from content: %s", error)
            return ""
