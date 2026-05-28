"""
Concurrent Campaign Manager Module
This module is responsible for running large-scale article generation campaigns
concurrently, using a thread pool to manage multiple generation tasks at once.
"""
import os
import json
import concurrent.futures
import logging
import math
import random
import threading
from typing import TYPE_CHECKING

from src.config import Config
from src.models import NoAvailableProductError, BlogGenerationError

# Use a forward reference for type hinting to avoid circular imports
if TYPE_CHECKING:
    from src.services import BlogGeneratorOrchestrator

logger = logging.getLogger(__name__)

class ConcurrentCampaignManager:
    """Orchestrates a concurrent article generation campaign."""

    def __init__(self, orchestrator: 'BlogGeneratorOrchestrator'):
        """
        Initializes the campaign manager.

        Args:
            orchestrator: An instance of BlogGeneratorOrchestrator, which handles
                          the logic for generating a single article.
        """
        self.orchestrator = orchestrator

    def _generate_article_worker(
        self,
        article_type: str,
        article_index: int,
        publish_to_wordpress: bool = False,
        publish_to_blogger: bool = False,
        publish_to_tumblr: bool = False,
        publish_to_linkedin: bool = False,
        publish_to_medium: bool = False,
        category: str = "",
        seed_title: str = "",
        override_keywords: list[str] = None
    ) -> dict:
        """
        A self-contained worker function for a single thread.
        It generates a title and then calls the main orchestrator's logic.
        """
        thread_name = threading.current_thread().name
        logger.info(
            "Worker %s (Task %s) starting job for type: %s",
            thread_name, article_index, article_type
        )
        try:
            # 1. Generate a unique title for this worker
            title_list = self.orchestrator.content_generator.generate_titles(
                num=1,
                article_type=article_type,
                category=category,
                seed_title=seed_title,
                scraped_keywords=override_keywords
            )
            if not title_list:
                raise ValueError("Could not generate a title.")
            title = title_list[0]
            logger.info("Worker %s generated title: '%s'", thread_name, title)

            # 2. Run the main, single-article generation pipeline
            article, report, product = self.orchestrator.generate_blog(
                title,
                article_type=article_type,
                publish_to_wordpress=publish_to_wordpress,
                publish_to_blogger=publish_to_blogger,
                publish_to_tumblr=publish_to_tumblr,
                publish_to_linkedin=publish_to_linkedin,
                publish_to_medium=publish_to_medium,
                category=category,
                override_keywords=override_keywords
            )

            # 3. Return a success result with usage stats
            return {
                "status": "success",
                "title": article.title,
                "type": "Brand-Specific" if article_type == "brand" else "Industry-Generic",
                "product": product.get('product_name') if product else "N/A",
                "score": report.overall_score,
                "word_count": article.word_count,
                "total_tokens": article.token_usage.get('total_tokens', 0),
                "total_cost": article.cost,
                "useful_tokens": article.useful_tokens.get('total_tokens', 0),
                "useful_cost": article.useful_cost,
                "has_image": bool(article.image_path),
                "is_published": article.is_published,
                "article_id": getattr(article, "article_id", ""),
                "linkedin_path": getattr(article, "linkedin_path", ""),
                "medium_path": getattr(article, "medium_path", ""),
                "wp_link": getattr(article, "wp_link", ""),
                "wp_slug": getattr(article, "wp_slug", "")
            }
        except NoAvailableProductError as error:
            logger.warning("Worker %s skipped brand-specific article: %s", thread_name, error)
            return {"status": "skipped", "reason": str(error)}
        except BlogGenerationError as error:
            logger.error("Worker %s failed to generate article: %s", thread_name, error)
            return {
                "status": "failure",
                "error": str(error),
                "total_tokens": error.total_tokens.get('total_tokens', 0),
                "total_cost": error.total_cost,
                "useful_tokens": 0,
                "useful_cost": 0.0
            }
        except Exception as error:  # pylint: disable=broad-exception-caught
            logger.error(
                "Worker %s failed to generate article (unexpected): %s",
                thread_name, error, exc_info=True
            )
            return {
                "status": "failure",
                "error": str(error),
                "total_tokens": 0,
                "total_cost": 0.0,
                "useful_tokens": 0,
                "useful_cost": 0.0
            }

    def run_campaign(self, total_articles: int, max_workers: int = 6,
                     publish_to_wordpress: bool = False,
                     publish_to_blogger: bool = False,
                     publish_to_tumblr: bool = False,
                     publish_to_linkedin: bool = False,
                     publish_to_medium: bool = False):
        """
        Executes the full concurrent generation campaign.
        Safeguards: Continues generating until 'total_articles' successes are achieved,
        replacing failed/skipped tasks automatically.
        """
        if total_articles <= 0 or max_workers <= 0:
            logger.error("Total articles and max workers must be positive integers.")
            return

        print(f"\nStarting concurrent generation for TARGET: {total_articles} successful articles...")
        logger.info("Target: %s successful articles. Max workers: %s.", total_articles, max_workers)

        # Tracking metrics
        stats = {
            "success_count": 0,
            "failure_count": 0,
            "skipped_count": 0,
            "processed_attempts": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "useful_tokens": 0,
            "useful_cost": 0.0,
            "articles_with_images_created": 0,
            "articles_published": 0,
            "articles_with_images_published": 0,
            "total_articles": total_articles,
            "successful_articles": []
        }

        # Prepare Coverage Mode Rotations & Seeds Pool
        seeds = {"articles": [], "pool": []}
        try:
            if os.path.exists(Config.SCRAPED_ARTICLES_JSON):
                with open(Config.SCRAPED_ARTICLES_JSON, 'r', encoding='utf-8') as file_handle:
                    seeds["articles"] = json.load(file_handle)
        except Exception as error:
            logger.warning("Failed loading scraped articles for campaign seeds: %s", error)

        seeds["pool"] = list(seeds["articles"])
        random.shuffle(seeds["pool"])

        industry_rotation = list(Config.INDUSTRY_CATEGORIES) or [Config.get_random_category("generic")]
        random.shuffle(industry_rotation)

        service_category_rotation = list(Config.PRODUCT_CATEGORIES) or [Config.get_random_category("brand")]
        random.shuffle(service_category_rotation)

        def get_next_job_params(article_type: str) -> dict:
            nonlocal industry_rotation, service_category_rotation
            seed_info = {
                "title": "",
                "keywords": None,
                "category": None
            }
            if article_type == "generic" and seeds["pool"]:
                # Pick a unique seed from the shuffled pool
                obj = seeds["pool"].pop(0)
                seed_info["title"] = obj.get("title", "")

                # Let the seed's category (if available) drive the choice, otherwise rotation
                scraped_cat = obj.get("category")
                if scraped_cat:
                    seed_info["category"] = scraped_cat
                else:
                    if not industry_rotation:
                        industry_rotation = list(Config.INDUSTRY_CATEGORIES) or [Config.get_random_category("generic")]
                        random.shuffle(industry_rotation)
                    seed_info["category"] = industry_rotation.pop(0)

                # Also use keywords from the seed if available
                kws = obj.get("keywords")
                if kws and isinstance(kws, list):
                    seed_info["keywords"] = kws[:15]

                # Refill pool if empty
                if not seeds["pool"]:
                    seeds["pool"] = list(seeds["articles"])
                    random.shuffle(seeds["pool"])
            elif article_type == "generic":
                if not industry_rotation:
                    industry_rotation = list(Config.INDUSTRY_CATEGORIES) or [Config.get_random_category("generic")]
                    random.shuffle(industry_rotation)
                seed_info["category"] = industry_rotation.pop(0)
            else:
                # For Brand-specific, use the product category rotation
                if not service_category_rotation:
                    service_category_rotation = list(Config.PRODUCT_CATEGORIES) or [Config.get_random_category("brand")]
                    random.shuffle(service_category_rotation)
                seed_info["category"] = service_category_rotation.pop(0)
                
            return seed_info

        # Safety valve: Stop if we try too many times (e.g., 5x the target) to prevent infinite loops
        max_attempts = total_articles * 5

        # Initial Batch Calculation
        # We need 'total_articles' successes. We start by queueing that many.
        remaining_needed = total_articles

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix='ArticleWorker'
        ) as executor:
            futures_set = set()

            # Helper to submit new batch of tasks
            def submit_batch(count):
                # Calculate ratio for this specific batch size
                n_brand = math.ceil(count * Config.BRAND_MENTION_RATIO)
                n_generic = count - n_brand
                batch_types = ['brand'] * n_brand + ['generic'] * n_generic
                random.shuffle(batch_types)

                for atype in batch_types:
                    params = get_next_job_params(atype)
                    fut = executor.submit(
                        self._generate_article_worker,
                        atype,
                        0,
                        publish_to_wordpress,
                        publish_to_blogger,
                        publish_to_tumblr,
                        publish_to_linkedin,
                        publish_to_medium,
                        params["category"],
                        params["title"],
                        params["keywords"]
                    )
                    futures_set.add(fut)

            # Submit initial batch
            submit_batch(remaining_needed)

            # Process Loop
            while (
                futures_set and
                stats["success_count"] < total_articles and
                stats["processed_attempts"] < max_attempts
            ):
                # Wait for at least one future to complete
                done, futures_set = concurrent.futures.wait(futures_set, return_when=concurrent.futures.FIRST_COMPLETED)

                for future in done:
                    # Pass context via stats or just assume it's there
                    stats['max_attempts'] = max_attempts
                    self._handle_worker_result(
                        future, stats, executor, futures_set,
                        publish_to_wordpress, publish_to_blogger, publish_to_tumblr,
                        publish_to_linkedin, publish_to_medium,
                        get_next_job_params
                    )

                # Check safety limit
                if stats["processed_attempts"] >= max_attempts and stats["success_count"] < total_articles:
                    print(
                        f"\n[WARNING] Reached maximum safety attempt limit ({max_attempts}). "
                        "Stopping campaign early."
                    )
                    logger.warning(
                        "Campaign stopped due to safety limit. Success: %s/%s",
                        stats["success_count"], total_articles
                    )
                    break

        self._print_campaign_summary(stats)

        logger.info(
            "Campaign finished. Target: %s, Achieved: %s, Cost: $%.4f",
            total_articles, stats["success_count"], stats["total_cost"]
        )
        return stats["successful_articles"]

    def _handle_worker_result(
        self, future, stats, executor, futures_set,
        publish_to_wordpress, publish_to_blogger, publish_to_tumblr,
        publish_to_linkedin, publish_to_medium,
        get_next_job_params
    ):
        """Helper to process a completed worker future and manage retries."""
        stats["processed_attempts"] += 1
        try:
            result = future.result()

            # Accumulate stats
            if 'total_tokens' in result:
                stats["total_tokens"] += result['total_tokens']
                stats["total_cost"] += result['total_cost']
                stats["useful_tokens"] += result['useful_tokens']
                stats["useful_cost"] += result['useful_cost']

            status = result['status']

            if status == 'success':
                stats["success_count"] += 1
                stats["successful_articles"].append(result)
                if result.get('has_image'):
                    stats["articles_with_images_created"] += 1
                if result.get('is_published'):
                    stats["articles_published"] += 1
                    if result.get('has_image'):
                        stats["articles_with_images_published"] += 1

                progress = f"({stats['success_count']}/{stats['total_articles']})"
                print(
                    f"SUCCESS {progress}: '{result['title']}' "
                    f"(Score: {result['score']}, Type: {result['type']})"
                )
            else:
                # Handle Failure/Skip
                if status == 'skipped':
                    stats["skipped_count"] += 1
                    print(f"SKIPPED (Will Retry): {result['reason']}")
                else:
                    stats["failure_count"] += 1
                    print(f"FAILURE (Will Retry): {result['error']}")

                # RETRY LOGIC: Replenish this slot immediately.
                if (
                    stats["success_count"] < stats["total_articles"] and
                    (stats["processed_attempts"] + len(futures_set)) < stats['max_attempts']
                ):
                    next_type = (
                        'brand' if random.random() < Config.BRAND_MENTION_RATIO
                        else 'generic'
                    )
                    params = get_next_job_params(next_type)
                    new_fut = executor.submit(
                        self._generate_article_worker,
                        next_type,
                        stats["processed_attempts"] + 1,
                        publish_to_wordpress,
                        publish_to_blogger,
                        publish_to_tumblr,
                        publish_to_linkedin,
                        publish_to_medium,
                        params["category"],
                        params["title"],
                        params["keywords"]
                    )
                    futures_set.add(new_fut)
                    print("   -> Re-queued 1 new task to replace failed/skipped article.")

        except Exception as error:  # pylint: disable=broad-exception-caught
            stats["failure_count"] += 1
            print(f"CRITICAL WORKER FAIL: {error}")
            # Even for crash, try to replenish
            if (
                stats["success_count"] < stats["total_articles"] and
                (stats["processed_attempts"] + len(futures_set)) < stats['max_attempts']
            ):
                next_type = 'generic'  # Fallback safe type
                params = get_next_job_params(next_type)
                new_fut = executor.submit(
                    self._generate_article_worker,
                    next_type,
                    stats["processed_attempts"] + 1,
                    publish_to_wordpress,
                    publish_to_blogger,
                    publish_to_tumblr,
                    publish_to_linkedin,
                    publish_to_medium,
                    params["category"],
                    params["title"],
                    params["keywords"]
                )
                futures_set.add(new_fut)

    def _print_campaign_summary(self, stats):
        """Helper to print the campaign summary to console."""
        wasted_tokens = stats["total_tokens"] - stats["useful_tokens"]
        wasted_cost = stats["total_cost"] - stats["useful_cost"]

        print(f"\n{'='*100}")
        print(f"{'CONTINUOUS GENERATION CAMPAIGN SUMMARY':^100}")
        print(f"{'='*100}")
        print(f"{'METRIC':<30} | {'VALUE':<15}")
        print(f"{'-'*100}")
        print(f"{'Target Success Count':<30} | {stats['total_articles']:<15}")
        print(f"{'Actual Successes':<30} | {stats['success_count']:<15}")
        print(f"{'Total Attempts Made':<30} | {stats['processed_attempts']:<15}")
        print(f"{'Failures (Retried)':<30} | {stats['failure_count']:<15}")
        print(f"{'Skipped (Retried)':<30} | {stats['skipped_count']:<15}")
        print(f"{'-'*100}")
        print(f"{'Total Tokens Used':<30} | {stats['total_tokens']:<15}")
        print(f"{'Total Cost ($)':<30} | ${stats['total_cost']:<14.4f}")
        print(f"{'Useful Tokens (Published)':<30} | {stats['useful_tokens']:<15}")
        print(f"{'Useful Cost ($)':<30} | ${stats['useful_cost']:<14.4f}")
        print(f"{'Wasted Tokens':<30} | {wasted_tokens:<15}")
        print(f"{'Wasted Cost ($)':<30} | ${wasted_cost:<14.4f}")
        print(f"{'-'*100}")
        print(f"{'Articles with Images Created':<30} | {stats['articles_with_images_created']:<15}")
        print(f"{'Total Articles Published':<30} | {stats['articles_published']:<15}")
        print(f"{'Articles w/ Images Published':<30} | {stats['articles_with_images_published']:<15}")
        print(f"{'='*100}\n")
