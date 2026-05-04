"""
Web Scraper Module
This module contains the RobustScraper class, which is responsible for scraping
competitor websites for blog titles using undetected-chromedriver
to bypass bot detection measures.
"""
import json
import logging
import os
import random
import re
import time

from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin

from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.config import Config

from src.llm_client import call_llm

# --- Dependency Imports with Graceful Fallbacks ---
try:
    from bs4 import BeautifulSoup
    import undetected_chromedriver as uc
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.chrome.service import Service as ChromeService
    import requests # Added for sitemap fetching
    SCRAPING_AVAILABLE = True

    try:
        _uc_orig_del = getattr(uc.Chrome, "__del__", None)

        def _uc_safe_del(self):
            try:
                if _uc_orig_del:
                    _uc_orig_del(self)
            except OSError:
                pass
            except Exception:
                pass

        if _uc_orig_del:
            uc.Chrome.__del__ = _uc_safe_del
    except Exception:
        pass
except ImportError as import_error:
    SCRAPING_AVAILABLE = False
    logging.warning(
        "Scraping libraries (beautifulsoup4, undetected-chromedriver) not available: %s. "
        "Scraping will be disabled.", import_error
    )
    logging.warning("Please run: pip install undetected-chromedriver beautifulsoup4")

logger = logging.getLogger(__name__)


class RobustScraper:
    """Scrapes titles from dynamic, protected websites using a stealth browser."""
    def __init__(self):
        if not SCRAPING_AVAILABLE:
            raise ImportError(
                "Scraping libraries not installed. Please run: pip install undetected-chromedriver beautifulsoup4"
            )

        self.targets = Config.SCRAPER_TARGETS
        self.driver = self._init_driver()
        self.total_tokens = 0
        self.total_cost = 0.0
        self.titles_processed_for_keywords = 0
        self.keywords_generated_count = 0

    def _init_driver(self):
        """Initializes a more human-like undetected Chrome WebDriver."""
        logger.info("Initializing stealth browser with enhanced options...")
        try:
            use_plain_selenium = os.getenv("USE_PLAIN_SELENIUM") == "1"

            if use_plain_selenium:
                # Plain Selenium path (used inside Docker to rely on system chromium+chromedriver)
                chrome_options = webdriver.ChromeOptions()
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-infobars")
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-popup-blocking")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--disable-software-rasterizer")
                chrome_options.add_argument("--disable-background-timer-throttling")
                chrome_options.add_argument("--disable-backgrounding-occluded-windows")
                chrome_options.add_argument("--disable-renderer-backgrounding")
                chrome_options.add_argument("--disable-features=TranslateUI")
                chrome_options.add_argument("--disable-ipc-flooding-protection")
                chrome_options.add_argument("--memory-pressure-off")
                chrome_options.add_argument("--max_old_space_size=4096")
                chrome_options.add_argument("--window-size=1920,1080")
                chrome_options.add_argument(
                    'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.204 Safari/537.36'
                )

                chrome_binary = os.getenv("CHROME_BIN", "/usr/bin/chromium")
                chrome_options.binary_location = chrome_binary
                chromedriver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
                service = ChromeService(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                # Default path: undetected-chromedriver for stealth on local machines
                options = uc.ChromeOptions()
                options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-infobars")
                options.add_argument("--disable-extensions")
                options.add_argument("--disable-popup-blocking")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-software-rasterizer")
                options.add_argument("--disable-background-timer-throttling")
                options.add_argument("--disable-backgrounding-occluded-windows")
                options.add_argument("--disable-renderer-backgrounding")
                options.add_argument("--disable-features=TranslateUI")
                options.add_argument("--disable-ipc-flooding-protection")
                options.add_argument("--memory-pressure-off")
                options.add_argument("--max_old_space_size=4096")
                options.add_argument("--window-size=1920,1080")
                options.add_argument(
                    'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.204 Safari/537.36'
                )

                # Common Chrome installation paths on Windows
                chrome_paths = [
                    os.getenv("CHROME_BIN"),
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%PROGRAMFILES(x86)%\Google\Chrome\Application\chrome.exe")
                ]

                # Find the first valid Chrome path
                browser_executable = None
                for chrome_path in chrome_paths:
                    if chrome_path and os.path.exists(chrome_path):
                        browser_executable = chrome_path
                        logger.info("Found Chrome at: %s", browser_executable)
                        break

                if not browser_executable:
                    raise FileNotFoundError(
                        "Google Chrome not found. Please install Chrome or set the CHROME_BIN "
                        "environment variable to point to your Chrome installation.")

                logger.info("Using Chrome executable: %s", browser_executable)
                driver = uc.Chrome(options=options, browser_executable_path=browser_executable)
            # Set reasonable page load timeout
            driver.set_page_load_timeout(Config.SCRAPER_PAGE_LOAD_TIMEOUT)
            logger.info("Stealth browser initialized.")
            return driver
        except Exception as error:
            logger.error("Failed to initialize undetected-chromedriver: %s", error)
            logger.error("Please ensure Google Chrome is installed on this system.")
            raise

    def _load_categories(self) -> Dict[str, List[str]]:
        """Load categories from the config file."""
        try:
            categories_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'config', 'categories.json')
            with open(categories_path, 'r', encoding='utf-8') as file_handle:
                categories_data = json.load(file_handle)

            # Combine both product and industry categories for matching
            all_categories = []
            if 'product_categories' in categories_data:
                all_categories.extend(categories_data['product_categories'])
            if 'industry_categories' in categories_data:
                all_categories.extend(categories_data['industry_categories'])

            logger.info("Loaded %d categories for keyword filtering", len(all_categories))
            return {
                'all_categories': all_categories,
                'product_categories': categories_data.get('product_categories', []),
                'industry_categories': categories_data.get('industry_categories', [])
            }
        except Exception as error:
            logger.error("Failed to load categories: %s", error)
            return {'all_categories': [], 'product_categories': [], 'industry_categories': []}

    def _filter_titles_by_category(self, titles: List[str], site_name: str = "Unknown") -> List[str]:
        """Filter titles to only include those related to defined categories.
        RELAXED: Matches if any meaningful part of the title aligns with industry categories.
        """
        categories = self._load_categories()
        all_categories = categories['all_categories']

        if not all_categories:
            logging.warning("[%s] No categories loaded, returning original titles", site_name)
            return titles

        filtered_titles = []
        skipped_titles = []

        for title in titles:
            title_lower = title.strip().lower()
            if not title_lower:
                continue

            match = False
            for category in all_categories:
                cat_lower = category.lower()

                # 1. Direct contains match (Title contains category or vice versa)
                if cat_lower in title_lower or title_lower in cat_lower:
                    match = True
                    break

                # 2. Key terms match (RELAXED: Check for any word overlap >= 3 chars)
                cat_words = [w.strip() for w in re.split(r'[&\s,/]', cat_lower) if len(w.strip()) >= 3]
                title_words = [w.strip() for w in re.split(r'[&\s,/]', title_lower) if len(w.strip()) >= 3]

                if any(cat_word in title_lower for cat_word in cat_words) or any(
                    title_word in cat_lower for title_word in title_words
                ):
                    match = True
                    break

            if match:
                filtered_titles.append(title)
            else:
                skipped_titles.append(title)

        if skipped_titles:
            logger.info(
                "[%s] Filtered out %s titles (did not align even slightly with categories).",
                site_name, len(skipped_titles)
            )

        logger.info("[%s] Kept %s titles aligned with categories.", site_name, len(filtered_titles))
        return filtered_titles


    def _handle_popups(self):
        """Proactively find and close common cookie consent banners or popups."""
        try:
            # Common keywords in button texts
            consent_keywords = ["Accept", "Allow all", "Agree", "Got it", "Dismiss"]
            for keyword in consent_keywords:
                try:
                    # Find buttons by partial text match
                    buttons = self.driver.find_elements(
                        By.XPATH,
                        "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                        f"'abcdefghijklmnopqrstuvwxyz'), '{keyword.lower()}')]"
                    )
                    for button in buttons:
                        if button.is_displayed() and button.is_enabled():
                            logger.info("Attempting to close popup with button: '%s'", button.text)
                            button.click()
                            time.sleep(2) # Wait for popup to disappear
                            return # Exit after one successful click
                except Exception:
                    continue # Ignore errors if a button isn't found
        except Exception as error:
            logger.warning("Could not handle popups: %s", error)

    def _human_like_idle(self, min_pause: float = 1.5, max_pause: float = 4.0) -> None:
        """Simulate short reading/idle time with tiny scrolls to look more human."""
        try:
            total_sleep = random.uniform(min_pause, max_pause)
            end_time = time.time() + total_sleep
            while time.time() < end_time:
                # Occasionally perform a tiny scroll up or down
                if random.random() < 0.4:
                    direction = random.choice([-1, 1])
                    distance = random.uniform(0.1, 0.3)
                    self.driver.execute_script(
                        "window.scrollBy(0, arguments[0] * window.innerHeight);",
                        direction * distance,
                    )
                time.sleep(random.uniform(0.3, 0.9))
        except Exception as error:
            logger.debug("Human-like idle behaviour failed: %s", error)

    def _human_like_scroll(self):
        """Scrolls the page in a more human-like way to trigger dynamic content."""
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        max_scrolls = random.randint(3, 6)
        for _ in range(max_scrolls):
            # Scroll to a random fraction of the page height instead of jumping straight to the bottom
            scroll_target = random.uniform(0.4, 1.0)
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight * arguments[0]);",
                scroll_target,
            )
            time.sleep(random.uniform(2, 5))

            self._handle_popups() # Check for popups after scrolling

            # Occasionally scroll back up a bit as if the user is re-reading
            if random.random() < 0.3:
                self.driver.execute_script(
                    "window.scrollBy(0, -window.innerHeight * arguments[0]);",
                    random.uniform(0.3, 0.8),
                )
                time.sleep(random.uniform(1, 3))

            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break # Exit if page height is not increasing
            last_height = new_height

        # Ensure we end near the bottom of the page
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(2, 4))

    def _get_title_selectors(self, config: Dict) -> List[str]:
        selectors: List[str] = []
        try:
            if isinstance(config.get("title_selectors"), list) and config.get("title_selectors"):
                selectors = [s for s in config.get("title_selectors") if isinstance(s, str) and s.strip()]
            elif isinstance(config.get("title_selector"), str) and config.get("title_selector").strip():
                selectors = [config.get("title_selector").strip()]
        except Exception:
            pass
        if not selectors:
            selectors = [
                "h2 a", "h3 a", "article h2 a", "article h3 a",
                "h2.entry-title a", "a.title", "a.post-title", "a.entry-title",
            ]
        return selectors

    def stabilize_browser_interaction(self, driver, title_selector: str, max_wait: int = 15, max_scrolls: int = 15):
        try:
            WebDriverWait(driver, max_wait).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, title_selector))
            )
        except TimeoutException:
            logger.warning(
                "Timeout waiting for title elements using selector '%s' during stabilization; "
                "proceeding with available content.", title_selector
            )

        for _ in range(max_scrolls):
            try:
                driver.execute_script(
                    "window.scrollBy(0, document.body.scrollHeight/arguments[0]);",
                    max_scrolls,
                )
            except Exception as err:
                logger.debug("Scroll step failed during stabilization: %s", err)
                break

            time.sleep(1)

            try:
                self._handle_popups()
            except Exception:
                pass

    def _scrape_with_browser(self, site_name: str, config: Dict) -> Tuple[List[str], List[str]]:
        """Scrape a single site by fully rendering it and extract titles and keywords."""
        scrape_ctx = {
            "url": config["url"],
            "title_selectors": self._get_title_selectors(config),
            "keyword_selector": config.get("keyword_selector"),
            "keyword_attr": config.get("keyword_attr"),
            "page_source": "",
            "titles": [],
            "seen_titles": set(),
            "per_selector_counts": [],
            "keywords": [],
            "load_timeout": config.get("page_load_timeout", Config.SCRAPER_PAGE_LOAD_TIMEOUT),
            "wait_timeout": config.get("element_wait_timeout", Config.SCRAPER_ELEMENT_WAIT_TIMEOUT),
            "visible_any": False
        }
        logger.info("Starting scrape for '%s' at %s", site_name, scrape_ctx["url"])

        try:
            self.driver.set_page_load_timeout(scrape_ctx["load_timeout"])

            try:
                self.driver.get(scrape_ctx["url"])
            except TimeoutException as err:
                logger.warning(
                    "Page load timeout after %ss for '%s': %s. Continuing with available content.",
                    scrape_ctx["load_timeout"], site_name, err
                )

            WebDriverWait(self.driver, scrape_ctx["wait_timeout"]).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(random.uniform(2, 4))
            self._handle_popups()

            logger.info("Scrolling page for '%s' to load content and stabilize before extraction", site_name)
            self.stabilize_browser_interaction(self.driver, scrape_ctx["title_selectors"][0])
            self._human_like_idle(1.5, 3.5)
            self._human_like_idle(1.0, 3.0)

            for sel in scrape_ctx["title_selectors"]:
                try:
                    WebDriverWait(self.driver, max(3, int(scrape_ctx["wait_timeout"]/2))).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    scrape_ctx["visible_any"] = True
                    break
                except TimeoutException:
                    continue
            if not scrape_ctx["visible_any"]:
                logger.warning(
                    "Did not see visible title elements quickly on '%s'. Will still try parsing HTML.", site_name
                )
            time.sleep(random.uniform(1.5, 3.0))

            scrape_ctx["page_source"] = self.driver.page_source
            soup = BeautifulSoup(scrape_ctx["page_source"], 'html.parser')

            logger.info(
                "Looking for titles on '%s' using %s selector(s): %s",
                site_name, len(scrape_ctx["title_selectors"]), scrape_ctx["title_selectors"]
            )
            for sel in scrape_ctx["title_selectors"]:
                try:
                    elems = soup.select(sel)
                except Exception:
                    elems = []
                scrape_ctx["per_selector_counts"].append((sel, len(elems)))
                for elem in elems:
                    title_text = elem.get_text(strip=True)
                    if title_text and title_text.lower() not in scrape_ctx["seen_titles"]:
                        scrape_ctx["titles"].append(title_text)
                        scrape_ctx["seen_titles"].add(title_text.lower())

            logger.info("Selector hit counts on '%s': %s", site_name, scrape_ctx["per_selector_counts"])
            scrape_ctx["titles"] = self._filter_titles_by_category(scrape_ctx["titles"], site_name=site_name)

            if not scrape_ctx["titles"]:
                logger.warning(
                    "No titles passed category filtering on '%s'. Skipping further extraction.", site_name
                )
                return [], []

            if scrape_ctx["keyword_selector"]:
                keyword_elements = soup.select(scrape_ctx["keyword_selector"])
                raw_values = []
                for elem in keyword_elements:
                    val = (
                    elem.get(scrape_ctx["keyword_attr"] or "")
                    if scrape_ctx["keyword_attr"]
                    else elem.get_text(" ", strip=True)
                )
                    if val:
                        raw_values.append(val)

                for raw in raw_values:
                    for token in re.split(r"[\,\|;/]", raw):
                        kw_clean = token.strip()
                        if kw_clean:
                            scrape_ctx["keywords"].append(kw_clean)

                drop_set = {"none", "blog", "blogs"}
                scrape_ctx["keywords"] = [
                    k for k in scrape_ctx["keywords"]
                    if k.strip() and k.strip().lower() not in drop_set
                ]

                if not scrape_ctx["keywords"]:
                    logger.warning(
                        "No usable meta keywords found on '%s' using selector '%s'.",
                        site_name, scrape_ctx["keyword_selector"]
                    )

            if scrape_ctx["keywords"]:
                scrape_ctx["keywords"] = scrape_ctx["keywords"][:12]

            return scrape_ctx["titles"], scrape_ctx["keywords"]
        except Exception as error:
            logger.error("Scraping failed for '%s': %s", site_name, error)
            logger.info("Scraping failure for '%s' not saved to debug folder - only logged", site_name)
            return [], []
        finally:
            try:
                self.driver.set_page_load_timeout(Config.SCRAPER_PAGE_LOAD_TIMEOUT)
            except Exception:
                pass

    def run_scraping_campaign(self) -> Tuple[List[List[str]], List[List[str]], Dict[str, Any]]:
        """Runs the scraper for all target sites and aggregates titles and keywords.

        Returns a tuple of two lists:
        - all_titles: [[title, source], ...]
        - all_keywords: [[keyword, source], ...]
        """
        all_titles: List[List[str]] = []
        all_keywords: List[List[str]] = []
        site_stats: Dict[str, Dict[str, Any]] = {}

        logger.info("Running scraping campaign for %d target sites: %s", len(self.targets), list(self.targets.keys()))

        def _worker(site_name: str, config: Dict) -> Tuple[str, List[str], List[str], int, float, int, int]:
            local_scraper = None
            try:
                local_scraper = RobustScraper()
                titles, keywords = local_scraper.scrape_with_retry(site_name, config)
                return (site_name, titles, keywords,
                        local_scraper.total_tokens, local_scraper.total_cost,
                        local_scraper.titles_processed_for_keywords, local_scraper.keywords_generated_count)
            except Exception as error:
                logger.error("Scraping failed in worker for '%s': %s", site_name, error)
                return site_name, [], [], 0, 0.0, 0, 0
            finally:
                if local_scraper:
                    try:
                        local_scraper.close()
                    except Exception:
                        pass

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(_worker, site_name, config)
                for site_name, config in self.targets.items()
            ]

            for future in as_completed(futures):
                site_name, titles, keywords, t_tokens, t_cost, t_processed, k_generated = future.result()
                logger.info(
                    "[%s] Campaign worker finished: %d titles, %d keywords.",
                    site_name, len(titles), len(keywords)
                )
                all_titles.extend([[title, site_name] for title in titles])
                all_keywords.extend([[keyword, site_name] for keyword in keywords])

                site_stats[site_name] = {
                    "titles": len(titles),
                    "tokens": t_tokens,
                    "cost": t_cost,
                    "titles_processed": t_processed,
                    "kws_generated": k_generated
                }

        return all_titles, all_keywords, site_stats

    def run_scraping_campaign_raw(self) -> Tuple[List[List[str]], List[List[str]], Dict[str, Any]]:
        """Runs the scraper in RAW mode - extracts only real titles and meta keywords without any LLM processing.

        Returns a tuple of two lists:
        - all_titles: [[title, source], ...]
        - all_keywords: [[keyword, source], ...] (may be empty if no meta keywords exist)
        """
        all_titles: List[List[str]] = []
        all_keywords: List[List[str]] = []
        site_stats: Dict[str, Dict[str, Any]] = {}

        logger.info(
            "Running RAW scraping campaign for %d target sites: %s",
            len(self.targets), list(self.targets.keys())
        )

        def _worker_raw(site_name: str, config: Dict) -> Tuple[str, List[str], List[str], int, float]:
            local_scraper = None
            try:
                local_scraper = RobustScraper()
                titles, keywords = local_scraper.scrape_site_raw(site_name, config)
                return site_name, titles, keywords, local_scraper.total_tokens, local_scraper.total_cost
            except Exception as error:
                logger.error("RAW scraping failed in worker for '%s': %s", site_name, error)
                return site_name, [], [], 0, 0.0
            finally:
                if local_scraper:
                    try:
                        local_scraper.close()
                    except Exception:
                        pass

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(_worker_raw, site_name, config)
                for site_name, config in self.targets.items()
            ]

            for future in as_completed(futures):
                site_name, titles, keywords, t_tokens, t_cost = future.result()
                logger.info("[%s] Found %d titles and %d keywords (RAW mode).", site_name, len(titles), len(keywords))
                all_titles.extend([[title, site_name] for title in titles])
                all_keywords.extend([[keyword, site_name] for keyword in keywords])

                site_stats[site_name] = {
                    "titles": len(titles),
                    "tokens": t_tokens,
                    "cost": t_cost
                }


        return all_titles, all_keywords, site_stats

    def scrape_with_retry(self, site_name: str, config: Dict) -> Tuple[List[str], List[str]]:
        """Scrape a site with retry logic to handle failures.

        Returns titles and keywords (which may be empty lists if scraping fails).
        """
        last_keywords: List[str] = []
        # Initialize tracking variables for this scrape attempt
        self.total_tokens = 0
        self.total_cost = 0.0
        self.titles_processed_for_keywords = 0
        self.keywords_generated_count = 0

        for attempt in range(Config.SCRAPER_MAX_RETRIES + 1):
            try:
                if attempt > 0:
                    logger.info("Retry attempt %d for %s", attempt, site_name)
                    time.sleep(Config.SCRAPER_RETRY_DELAY)

                titles, keywords = self._scrape_with_browser(site_name, config)
                if keywords:
                    last_keywords = keywords
                if titles:  # Success - we got some titles
                    return titles, keywords
                if attempt == 0:  # First attempt failed but no exception
                    logger.warning("No titles found on first attempt for %s, retrying...", site_name)
                    continue

                # Retry attempts failed
                logger.warning("No titles found after %d retries for %s", attempt, site_name)
                if config.get("sitemap_url"):
                    logger.info("Visual scraping failed for %s. Attempting Sitemap fallback...", site_name)
                    return self._scrape_via_sitemap(site_name, config)
                return [], last_keywords
            except Exception as error:
                if attempt < Config.SCRAPER_MAX_RETRIES:
                    logger.warning(
                        "Attempt %s failed for %s: %s... Retrying in %ss",
                        attempt + 1, site_name, str(error)[:100], Config.SCRAPER_RETRY_DELAY
                    )
                else:
                    logger.error(
                        "All %s attempts failed for %s: %s...",
                        Config.SCRAPER_MAX_RETRIES + 1, site_name, str(error)[:100]
                    )
                    if config.get("sitemap_url"):
                        logger.info("Visual scraping failed for %s. Attempting Sitemap fallback...", site_name)
                        return self._scrape_via_sitemap(site_name, config)
                    return [], last_keywords
        return [], last_keywords

    def scrape_site_raw(self, site_name: str, config: Dict) -> Tuple[List[str], List[str]]:
        """RAW mode scraping - extracts only real titles and meta keywords without any LLM processing.

        This method:
        1. Scrapes the listing page to discover article URLs
        2. Visits each article to extract the real title (prefer h1) and meta keywords
        3. Does NOT use any LLM for keyword generation or extraction
        4. Returns empty keyword lists if no meta keywords exist

        Returns titles and keywords (keywords may be empty if no meta keywords exist).
        """
        scrape_config = {
            "base_url": config.get("url"),
            "title_selector": config.get("title_selector"),
            "keyword_selector": config.get("keyword_selector"),
            "keyword_attr": config.get("keyword_attr", "content"),
            "per_site_limit": int(config.get("keyword_articles_limit", 100))
        }

        if not scrape_config["base_url"] or not scrape_config["title_selector"]:
            logger.error("Missing required config for RAW scraping '%s': url or title_selector", site_name)
            return [], []

        raw_state: Dict[str, Any] = {
            "titles": [], "keywords": [], "options": uc.ChromeOptions(), "browser": None
        }
        raw_state["options"].add_argument("--headless")
        raw_state["options"].add_argument("--no-sandbox")
        raw_state["options"].add_argument("--disable-dev-shm-usage")
        raw_state["options"].add_argument("--disable-gpu")
        raw_state["options"].add_argument("--window-size=1920,1080")

        try:
            # Step 1: Visit the listing page to discover article URLs
            listing_url = scrape_config["base_url"]
            logger.info("RAW scraping %s from listing page: %s", site_name, listing_url)

            raw_state["browser"] = uc.Chrome(options=raw_state["options"])
            try:
                raw_state["browser"].get(listing_url)
                time.sleep(3)

                raw_state["listing_soup"] = BeautifulSoup(raw_state["browser"].page_source, "html.parser")
                raw_state["title_elements"] = raw_state["listing_soup"].select(scrape_config["title_selector"])

                raw_state["article_urls"] = []
                for element in raw_state["title_elements"]:
                    href = element.get("href") or element.get("data-href", "")
                    if href:
                        # Convert relative URLs to absolute
                        if href.startswith("/"):

                            href = urljoin(scrape_config["base_url"], href)
                        raw_state["article_urls"].append(href)

                logger.info("RAW mode discovered %d article URLs on %s", len(raw_state["article_urls"]), site_name)

                # Step 2: Visit each article to extract title and meta keywords
                for i, article_url in enumerate(raw_state["article_urls"][:scrape_config["per_site_limit"]]):
                    try:
                        logger.info(
                            "RAW scraping article %s/%s: %s",
                            i + 1, min(scrape_config["per_site_limit"], len(raw_state["article_urls"])), article_url
                        )
                        raw_state["browser"].get(article_url)
                        time.sleep(2)

                        raw_state["it"] = {
                            "soup": BeautifulSoup(raw_state["browser"].page_source, "html.parser"),
                            "title": "",
                            "meta_kw": None,
                            "kws": []
                        }

                        # Extract title
                        for selector in ["h1", "title", ".entry-title", "h2", "h3", "h4"]:
                            tag = raw_state["it"]["soup"].select_one(selector)
                            if tag:
                                raw_state["it"]["title"] = tag.get_text(strip=True)
                                break

                        # Validate title against categories
                        raw_state["it"]["filtered"] = self._filter_titles_by_category(
                            [raw_state["it"]["title"]], site_name=site_name
                        ) if raw_state["it"]["title"] else []

                        if not raw_state["it"]["filtered"]:
                            logger.debug("Title '%s' did not match categories. Skipping.", raw_state["it"]["title"])
                            continue

                        # Extract keywords
                        if scrape_config["keyword_selector"]:
                            raw_state["it"]["elements"] = raw_state["it"]["soup"].select(
                                scrape_config["keyword_selector"]
                            )
                            for element in raw_state["it"]["elements"]:
                                raw_state["it"]["text"] = element.get(scrape_config["keyword_attr"], "") or \
                                                        element.get_text(" ", strip=True)
                                if raw_state["it"]["text"]:
                                    for keyword_part in re.split(r'[,;|]', raw_state["it"]["text"]):
                                        keyword_part = keyword_part.strip()
                                        if keyword_part and len(keyword_part) > 2:
                                            raw_state["it"]["kws"].append(keyword_part)

                        raw_state["titles"].append(raw_state["it"]["title"])
                        raw_state["keywords"].extend(raw_state["it"]["kws"])

                    except Exception as it_error:
                        logger.debug("Failed to scrape article %s: %s", article_url, it_error)
                        continue

            finally:
                if raw_state.get("browser"):
                    raw_state["browser"].quit()

        except Exception as error:
            logger.error("RAW scraping failed for %s: %s", site_name, error)
            return [], []

        # Deduplicate keywords while preserving order
        raw_state["dedupe_kw"] = {"seen": set(), "unique": []}
        for keyword in raw_state["keywords"]:
            kw_lower = keyword.lower()
            if kw_lower not in raw_state["dedupe_kw"]["seen"]:
                raw_state["dedupe_kw"]["seen"].add(kw_lower)
                raw_state["dedupe_kw"]["unique"].append(keyword)

        logger.info(
            "RAW mode extracted %d titles and %d keywords from %s",
            len(raw_state["titles"]), len(raw_state["dedupe_kw"]["unique"]), site_name
        )
        return raw_state["titles"], raw_state["dedupe_kw"]["unique"]

    def _scrape_via_sitemap(self, site_name: str, config: Dict) -> Tuple[List[str], List[str]]:
        """Fallback method using sitemap.xml (supports discovery and sitemap indexes)."""
        sitemap_config = {
            "configured": config.get("sitemap_url"),
            "base": config.get("url") or "",
            "limit": int(config.get("keyword_articles_limit", 10)),
            "urls": [],
            "all_u": [],
            "dedupe": {"seen": set(), "urls": []}
        }
        sitemap_config["urls"] = self._discover_sitemaps(sitemap_config["base"], sitemap_config["configured"])
        if not sitemap_config["urls"]:
            logger.warning("No sitemap locations discovered for '%s'.", site_name)
            return [], []

        try:
            for sm_url in sitemap_config["urls"]:
                urls = self._fetch_sitemap_urls(sm_url, config.get("sitemap_pattern"))
                if urls:
                    sitemap_config["all_u"].extend(urls)

            # Dedupe while preserving order and limit candidates
            for url in sitemap_config["all_u"]:
                if url not in sitemap_config["dedupe"]["seen"]:
                    sitemap_config["dedupe"]["urls"].append(url)
                    sitemap_config["dedupe"]["seen"].add(url)

            if not sitemap_config["dedupe"]["urls"]:
                logger.warning("No relevant URLs found in sitemap for %s", site_name)
                return [], []

            logger.info(
                "Found %s URL candidates in sitemaps for '%s'. Scanning top %s",
                len(sitemap_config["dedupe"]["urls"]), site_name, sitemap_config["limit"]
            )

            # Limit to top N mostly recent URLs
            extracted = {"titles": [], "keywords": []}
            # Only process candidates up to the limit
            for url in sitemap_config["dedupe"]["urls"][:sitemap_config["limit"]]:
                extracted["it"] = self._scrape_single_article(url)
                extracted["it_title"] = extracted["it"].get("title")

                if extracted["it_title"]:
                    # Workflow: only accept titles that fit the industry/brand categories
                    extracted["it_filtered"] = self._filter_titles_by_category(
                        [extracted["it_title"]], site_name=site_name
                    )
                    if extracted["it_filtered"]:
                        extracted["titles"].append(extracted["it_title"])
                        extracted["keywords"].extend(extracted["it"].get("keywords", []))
                        logger.info("[%s] Sitemap article matched: %s", site_name, extracted["it_title"])
                    else:
                        logger.debug(
                            "[%s] Sitemap article '%s' did not match. Skipping.",
                            site_name, extracted["it_title"]
                        )

            # Deduplicate and return
            extracted["out_kw"] = []
            extracted["seen_k"] = set()
            for k in extracted["keywords"]:
                keyword = (k or "").strip()
                if not keyword:
                    continue
                low = keyword.lower()
                if low in extracted["seen_k"]:
                    continue
                extracted["seen_k"].add(low)
                extracted["out_kw"].append(keyword)
            return extracted["titles"], extracted["out_kw"][:12]

        except Exception as error:
            logger.error("Sitemap fallback failed for %s: %s", site_name, error)
            return [], []

    def _fetch_sitemap_urls(
        self, sitemap_url: str, pattern: str = None, visited: Optional[Set[str]] = None
    ) -> List[str]:
        """Fetches and parses an XML sitemap or sitemap index recursively."""
        try:
            if visited is None:
                visited = set()
            if sitemap_url in visited:
                return []
            visited.add(sitemap_url)

            # Request and parse
            request_info = {
                "headers": {
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/91.0.4472.124 Safari/537.36'
                    )
                },
                "resp": requests.get(sitemap_url, headers={'User-Agent': '...'}, timeout=20)
            }
            # Re-fetch properly
            request_info["resp"] = requests.get(sitemap_url, headers=request_info["headers"], timeout=20)

            if request_info["resp"].status_code != 200:
                logger.warning("Failed to fetch sitemap '%s': HTTP %d", sitemap_url, request_info["resp"].status_code)
                return []

            soup = BeautifulSoup(request_info["resp"].content, 'xml')
            urls: List[str] = []
            if soup.find('sitemapindex'):
                nodes = soup.find_all('sitemap')
                logger.info("'%s' is a sitemap index with %d child sitemaps", sitemap_url, len(nodes))
                for node in nodes:
                    loc = node.find('loc')
                    if not loc or not loc.text:
                        continue
                    child = loc.text.strip()
                    try:
                        child_urls = self._fetch_sitemap_urls(child, pattern, visited)
                        urls.extend(child_urls)
                    except Exception:
                        continue
            else:
                locs = soup.find_all('loc')
                urls = [loc.text.strip() for loc in locs if loc and loc.text]
                if pattern:
                    urls = [u for u in urls if pattern in u]
            return urls
        except Exception as error:
            logger.warning("Error parsing sitemap '%s': %s", sitemap_url, error)
            return []

    def _discover_sitemaps(self, base_url: str, configured: Optional[str] = None) -> List[str]:
        discovery = {"candidates": [], "base_root": ""}
        if configured and isinstance(configured, str):
            discovery["candidates"].append(configured)
        try:
            if base_url:
                if not base_url.endswith('/'):
                    root_parts = base_url.split('/', 3)
                    if len(root_parts) >= 3:
                        discovery["base_root"] = f"{root_parts[0]}//{root_parts[2]}/"
                    else:
                        discovery["base_root"] = base_url + '/'
                else:
                    discovery["base_root"] = base_url
                for path in ["sitemap.xml", "sitemap_index.xml", "sitemap/sitemap.xml"]:
                    discovery["candidates"].append(urljoin(discovery["base_root"], path))
                # robots.txt
                robots_url = urljoin(discovery["base_root"], "robots.txt")
                try:
                    robots_headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    robots_resp = requests.get(robots_url, headers=robots_headers, timeout=10)
                    if robots_resp.status_code == 200:
                        for line in robots_resp.text.splitlines():
                            if line.lower().startswith("sitemap:"):
                                sitemap_loc = line.split(":", 1)[1].strip()
                                if sitemap_loc:
                                    discovery["candidates"].append(sitemap_loc)
                except Exception:
                    pass
        except Exception:
            pass
        # Deduplicate while preserving order
        dedupe = {"seen": set(), "out": []}
        for candidate in discovery["candidates"]:
            if candidate and candidate not in dedupe["seen"]:
                dedupe["seen"].add(candidate)
                dedupe["out"].append(candidate)
        logger.info("Discovered %d sitemap location(s)", len(dedupe["out"]))
        return dedupe["out"]


    def _scrape_single_article(self, article_url: str) -> Dict[str, Any]:
        """Scrapes text and keywords from a single article URL with robust error handling."""
        art_ctx = {
            "chrome_options": uc.ChromeOptions(),
            "browser": None,
            "html": ""
        }
        art_ctx["chrome_options"].add_argument("--headless")
        art_ctx["chrome_options"].add_argument("--no-sandbox")
        art_ctx["chrome_options"].add_argument("--disable-dev-shm-usage")

        try:
            art_ctx["browser"] = uc.Chrome(options=art_ctx["chrome_options"])
            art_ctx["browser"].get(article_url)
            time.sleep(2)
            art_ctx["html"] = art_ctx["browser"].page_source
            return self._extract_text_and_keywords(art_ctx["html"])
        except Exception as error:
            logger.error("Failed to scrape single article %s: %s", article_url, error)
            return {"text": "", "keywords": []}
        finally:
            if art_ctx.get("browser"):
                art_ctx["browser"].quit()

    def _extract_text_and_keywords(self, html: str) -> Dict[str, Any]:
        """Extracts main content text and keywords from article HTML."""
        ex_ctx = {
            "soup": BeautifulSoup(html, "html.parser"),
            "res": {"text": "", "keywords": []},
            "selectors": ["article", ".entry-content", ".content", "main", "body"]
        }

        # Remove script and style elements
        for script_or_style in ex_ctx["soup"](["script", "style"]):
            script_or_style.decompose()

        for selector in ex_ctx["selectors"]:
            tag = ex_ctx["soup"].select_one(selector)
            if tag:
                ex_ctx["res"]["text"] = tag.get_text(separator="\n", strip=True)
                break

        if not ex_ctx["res"]["text"]:
            ex_ctx["res"]["text"] = ex_ctx["soup"].get_text(separator="\n", strip=True)

        # Meta keywords extraction
        ex_ctx["meta"] = ex_ctx["soup"].find("meta", attrs={"name": "keywords"})
        if ex_ctx["meta"] and ex_ctx["meta"].get("content"):
            ex_ctx["res"]["keywords"] = [k.strip() for k in ex_ctx["meta"]["content"].split(",")]

        # Also look for OG keywords or similar
        ex_ctx["og"] = ex_ctx["soup"].find("meta", attrs={"property": "article:tag"})
        if ex_ctx["og"] and ex_ctx["og"].get("content"):
            ex_ctx["res"]["keywords"].append(ex_ctx["og"]["content"].strip())

        return ex_ctx["res"]

    def _extract_keywords_from_text(self, text: str, top_n: int = 12, site_name: str = "Unknown") -> List[str]:
        """Extract unique, content-specific keywords using industry context."""
        if not text or not isinstance(text, str):
            return []

        kw_ctx = {
            "industry": getattr(Config, 'INDUSTRY_NAME', 'industry'),
            "clean_text": "",
            "tokens": [],
            "task": f"Keyword Extraction for {site_name}",
            "prompt": ""
        }

        # Basic text cleaning
        kw_ctx["clean_text"] = re.sub(r"[^a-z0-9\s]", " ", text.lower())
        kw_ctx["clean_text"] = re.sub(r"\s+", " ", kw_ctx["clean_text"]).strip()

        kw_ctx["tokens"] = kw_ctx["clean_text"].split()
        if not kw_ctx["tokens"]:
            return []

        # Enhanced prompt for unique keyword extraction
        try:
            kw_ctx["prompt"] = f"""
You are an SEO expert specializing in the {kw_ctx['industry']} industry.

TASK: Extract {top_n} UNIQUE keywords from this article content.

CONTENT: {kw_ctx['clean_text'][:1000]}  # First 1000 chars for context

REQUIREMENTS:
1. Extract keywords that are SPECIFIC to this content
2. Include {kw_ctx['industry']} industry terms
3. Avoid generic keywords that apply to any article
4. Focus on unique concepts, products, techniques mentioned
5. Each keyword should be 2-4 words long

Generate exactly {top_n} unique keywords as a comma-separated list:
"""

            response_text, usage = call_llm(
                model=Config.MODEL_NAME,
                prompt=kw_ctx["prompt"],
                max_tokens=400,
                temperature=0.6,
                presence_penalty=Config.PRESENCE_PENALTY,
                frequency_penalty=Config.FREQUENCY_PENALTY,
                task_name=kw_ctx["task"],
                include_usage=True
            )
            self.total_tokens += usage.get("total_tokens", 0)
            self.total_cost += usage.get("cost", 0.0)
            keywords = [k.strip() for k in response_text.split(",") if k.strip()]

            return keywords[:top_n]

        except Exception as error:
            logger.warning("[%s] AI keyword extraction failed: %s", site_name, error)
            # Fallback to simple word extraction
            stop = {
                'the', 'and', 'for', 'with', 'this', 'that', 'from', 'are', 'was', 'were', 'will', 'would', 'in',
                'on', 'of', 'to', 'a', 'an', 'by', 'as', 'it', 'its', 'is', 'be', 'or', 'at', 'we', 'you', 'our',
                'their', 'they', 'he', 'she', 'them', 'his', 'her', 'i', 'have', 'has', 'had', 'but', 'not', 'also',
                'can', 'could', 'into', 'about', 'more', 'most', 'such', 'than', 'other', 'which', 'who', 'whom',
                'when', 'where', 'how', 'why', 'what', 'your', 'yours', 'us', 'me', 'my', 'mine', 'theirs', 'ours',
                'over', 'under', 'between', 'within', 'across', 'per'
            }

            words = [w for w in kw_ctx["tokens"] if w not in stop and not w.isdigit() and len(w) > 2]
            return list(set(words))[:top_n]

    def generate_keywords_from_title(
        self, title: Union[str, List[str]], top_n: int = 12, site_name: str = "Unknown"
    ) -> Union[List[str], List[List[str]]]:
        """Generate unique, title-specific keywords using industry context."""
        gen_ctx = {
            "industry": getattr(Config, 'INDUSTRY_NAME', 'industry'),
            "is_bulk": isinstance(title, list),
            "titles": title if isinstance(title, list) else [title],
            "all_res": []
        }

        if gen_ctx["is_bulk"]:
            logger.info("[%s] Parallel keyword gen for %d titles.", site_name, len(gen_ctx["titles"]))
            with ThreadPoolExecutor(max_workers=5) as kw_exe:
                gen_ctx["futures"] = {
                    kw_exe.submit(self.generate_keywords_from_title, t, top_n, site_name): t
                    for t in gen_ctx["titles"]
                }
                for future in as_completed(gen_ctx["futures"]):
                    try:
                        res = future.result()
                        if res:
                            self.titles_processed_for_keywords += 1
                            self.keywords_generated_count += len(res)
                            gen_ctx["all_res"].append(res)
                    except Exception as err:
                        logger.debug("[%s] Parallel keyword gen failed: %s", site_name, err)
                        gen_ctx["all_res"].append([])
            return gen_ctx["all_res"]

        # Single title logic
        if not title or not isinstance(title, str) or not title.strip():
            return []

        gen_ctx["clean"] = title.strip()
        try:
            gen_ctx["task"] = f"Keyword Generation for {site_name}: {gen_ctx['clean'][:30]}..."
            gen_ctx["prompt"] = f"""
You are an SEO expert specializing in the {gen_ctx['industry']} industry.

TASK: Generate {top_n} UNIQUE, high-value keywords for this article title.

TITLE: "{gen_ctx['clean']}"

REQUIREMENTS:
1. Keywords must be highly specific to the title's topic.
2. Focus on {gen_ctx['industry']} industry concepts, materials, or services.
3. Avoid generic keywords (e.g., "tips", "best practices").
4. Each keyword should be 2-4 words long.

EXAMPLES:
- Title: "How to Improve Your Workflow" → Keywords: ["efficient workflow", "productivity tools", "business optimization"]
- Title: "The Future of Technology" → Keywords: ["emerging tech", "innovation trends", "digital transformation"]

Generate exactly {top_n} unique keywords as a comma-separated list:
"""

            resp, usage = call_llm(
                model=Config.MODEL_NAME,
                prompt=gen_ctx["prompt"],
                max_tokens=200,
                temperature=0.7,
                presence_penalty=Config.PRESENCE_PENALTY,
                frequency_penalty=Config.FREQUENCY_PENALTY,
                task_name=gen_ctx["task"],
                include_usage=True
            )
            self.total_tokens += usage.get("total_tokens", 0)
            self.total_cost += usage.get("cost", 0.0)
            kws = [k.strip() for k in str(resp).split(",") if k.strip()]

            return kws[:top_n]

        except Exception as error:
            logger.warning("[%s] AI keyword generation from title failed: %s", site_name, error)
            # Fallback to simple extraction
            parts = [p for p in re.split(r"[^A-Za-z0-9]+", gen_ctx["clean"]) if len(p) > 2]
            return list({p.lower() for p in parts})[:top_n]

    def close(self):
        """Closes the browser."""
        driver = getattr(self, "driver", None)
        if driver:
            logger.info("Closing stealth browser.")
            try:
                driver.quit()
            except OSError:
                pass
            except Exception:
                pass
            finally:
                self.driver = None
