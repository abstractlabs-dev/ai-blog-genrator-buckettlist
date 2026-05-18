"""
Configuration Module
This module centralizes all configuration variables for the application,
including API keys, file paths, and SEO settings.
"""
import os
import json
import logging
import random
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

class Config:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CONFIG_DIR = os.path.join(PROJECT_ROOT, "data", "config")

    # Brand and Industry Configuration
    BRAND_NAME = os.getenv("BRAND_NAME", "your_brand_name")
    INDUSTRY_NAME = os.getenv("INDUSTRY_NAME", "your_industry_name")
    BRAND_MENTION_RATIO = float(os.getenv("BRAND_MENTION_RATIO", "0.25"))

    # Location Configuration
    TARGET_CITY = os.getenv("TARGET_CITY", "your_city")
    TARGET_STATE = os.getenv("TARGET_STATE", "your_state")

    # Content Configuration
    BRAND_PROMOTION_ENABLED = os.getenv("BRAND_PROMOTION_ENABLED", "True").lower() == "true"
    DEFAULT_LINK_URL = os.getenv("DEFAULT_LINK_URL", "https://your-website.com/blog")
    DEFAULT_LINK_TEXT = os.getenv("DEFAULT_LINK_TEXT", "Visit our website")

    # Scraper Configuration
    SCRAPER_RAW_MODE = os.getenv("SCRAPER_RAW_MODE", "0") == "1"
    SCRAPER_PAGE_LOAD_TIMEOUT = int(os.getenv("SCRAPER_PAGE_LOAD_TIMEOUT", "30"))
    SCRAPER_ELEMENT_WAIT_TIMEOUT = int(os.getenv("SCRAPER_ELEMENT_WAIT_TIMEOUT", "20"))
    SCRAPER_MAX_RETRIES = int(os.getenv("SCRAPER_MAX_RETRIES", "2"))
    SCRAPER_RETRY_DELAY = int(os.getenv("SCRAPER_RETRY_DELAY", "5"))
    SCRAPER_SITE_GAP = int(os.getenv("SCRAPER_SITE_GAP", "10"))


    # API Configuration
    # Primary key name (preferred): Google AI Studio key used for Gemini text + (optionally) image generation.
    # Backward-compat: fall back to GEMINI_API_KEY if an existing .env still uses it.
    GOOGLE_AI_STUDIO_API_KEY = os.getenv("GOOGLE_AI_STUDIO_API_KEY") or os.getenv("GEMINI_API_KEY")
    # Backward-compat alias. Keep until old envs are migrated.
    GEMINI_API_KEY = GOOGLE_AI_STUDIO_API_KEY

    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash")
    MODEL_NAME = GEMINI_MODEL
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "imagen-4.0-generate-001")
    API_KEY = os.getenv('API_KEY')
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))
    PRESENCE_PENALTY = float(os.getenv("PRESENCE_PENALTY", "0.8"))
    FREQUENCY_PENALTY = float(os.getenv("FREQUENCY_PENALTY", "0.6"))
    WEBSITE_START_DATE = os.getenv("WEBSITE_START_DATE", "2024-01-01")

    # Vertex AI / Google Gen AI SDK Configuration
    GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "ai-blog-genrator")
    GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "asia-south1")
    USE_VERTEX_AI = os.getenv("USE_VERTEX_AI", "True").lower() == "true"

    # WordPress Configuration
    WORDPRESS_BASE_URL = os.getenv("WORDPRESS_BASE_URL")
    WORDPRESS_USERNAME = os.getenv("WORDPRESS_USERNAME")
    WORDPRESS_TOKEN = os.getenv("WORDPRESS_TOKEN")

    @classmethod
    def validate_api_key(cls):
        if cls.USE_VERTEX_AI:
            if not cls.GOOGLE_CLOUD_PROJECT or not cls.GOOGLE_CLOUD_LOCATION:
                logger.warning(
                    "Vertex AI is enabled but GOOGLE_CLOUD_PROJECT or GOOGLE_CLOUD_LOCATION is missing.\n"
                    "Please check your .env file."
                )
            else:
                logger.info("Vertex AI configuration loaded: Project=%s, Location=%s", 
                            cls.GOOGLE_CLOUD_PROJECT, cls.GOOGLE_CLOUD_LOCATION)
        elif not cls.GOOGLE_AI_STUDIO_API_KEY:
            logger.warning(
                "GOOGLE_AI_STUDIO_API_KEY not found. Running in fallback (offline) mode.\n"
                "Set it in your environment or .env to enable live generation."
            )
        else:
            logger.info("Google AI Studio API key loaded successfully")

    @classmethod
    def get_random_category(cls, article_type: str) -> str:
        categories = cls.PRODUCT_CATEGORIES if article_type == "brand" else cls.INDUSTRY_CATEGORIES
        if categories:
            return random.choice(categories)
        logger.warning("No categories configured for article_type=%s. Using industry fallback.", article_type)
        return cls.INDUSTRY_NAME or "general"

    # Storage Configuration
    BASE_DIR = os.getenv("APP_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
    PROJECT_DATA_CSV = os.path.join(BASE_DIR, "services.csv")  # Renamed from products.csv
    CSV_PATH = os.path.join(BASE_DIR, "database", "articles.csv")
    USED_TITLES_CSV = os.path.join(BASE_DIR, "database", "used_titles.csv")
    VECTOR_STORE_PATH = os.path.join(BASE_DIR, "vector_store")
    OUTPUT_DIR = os.path.join(BASE_DIR, "output")
    BRAND_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "brand")
    IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
    JSON_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "json")
    # Social cross-posting export directories
    SOCIAL_DIR         = os.path.join(OUTPUT_DIR, "social")
    SOCIAL_LINKEDIN_DIR = os.path.join(SOCIAL_DIR, "linkedin")
    SOCIAL_MEDIUM_DIR   = os.path.join(SOCIAL_DIR, "medium")

    @classmethod
    def ensure_directories(cls):
        try:
            os.makedirs(cls.BASE_DIR, exist_ok=True)
            os.makedirs(os.path.dirname(cls.CSV_PATH), exist_ok=True)
            os.makedirs(cls.OUTPUT_DIR, exist_ok=True)
            os.makedirs(cls.BRAND_OUTPUT_DIR, exist_ok=True)
            os.makedirs(cls.IMAGES_DIR, exist_ok=True)
            os.makedirs(cls.JSON_OUTPUT_DIR, exist_ok=True)
            os.makedirs(cls.SOCIAL_LINKEDIN_DIR, exist_ok=True)
            os.makedirs(cls.SOCIAL_MEDIUM_DIR, exist_ok=True)
            logger.info("Storage directories ensured under: %s", cls.BASE_DIR)
        except Exception as error:
            logger.warning("Could not create storage directories at %s: %s", cls.BASE_DIR, error)

    # Scraped data paths
    SCRAPED_TITLES_CSV = os.path.join(BASE_DIR, "database", "scraped_blog_titles.csv")
    SCRAPED_KEYWORDS_CSV = os.path.join(BASE_DIR, "database", "scraped_blog_keywords.csv")
    SCRAPED_ARTICLES_JSON = os.path.join(BASE_DIR, "database", "scraped_articles.json")



    @staticmethod
    def _load_json_config(path: str, default: dict = None) -> dict:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as config_file:
                    return json.load(config_file)
            except Exception as error:
                logger.warning("Failed to load %s: %s. Using defaults.", path, error)
        else:
            logger.warning("Config file not found at %s. Using defaults.", path)
        return default or {}

    # Load specific configs using locally available CONFIG_DIR
    _keywords_cfg = _load_json_config.__func__(os.path.join(CONFIG_DIR, "keywords.json"), {
        "primary": [], "curated": [], "location": [], "forbidden": []
    })
    _competitors_cfg = _load_json_config.__func__(os.path.join(CONFIG_DIR, "competitors.json"), {
        "scraper_targets": {}, "brand_blacklist": []
    })
    _categories_cfg = _load_json_config.__func__(os.path.join(CONFIG_DIR, "categories.json"), {
        "product_categories": [], "industry_categories": []
    })
    _templates_cfg = _load_json_config.__func__(os.path.join(CONFIG_DIR, "templates.json"), {})
    _categories_mapping_cfg = _load_json_config.__func__(os.path.join(CONFIG_DIR, "categories_mapping.json"), {})
    CATEGORIES_MAPPING = _categories_mapping_cfg
    _schema_map_cfg = _load_json_config.__func__(os.path.join(CONFIG_DIR, "schema_map.json"), {
        "mapping": {}, "id_column": "id"
    })

    @staticmethod
    def _get_env_json(env_name: str, default_val):
        """Helper to load JSON structures from environment variables."""
        val = os.getenv(env_name)
        if val:
            try:
                return json.loads(val)
            except Exception as error:
                logger.warning("Failed to parse JSON for %s from env: %s", env_name, error)
        return default_val

    # Expose as Class Attributes - Prioritize .env if available
    # Keywords
    # Load ALL keywords from keywords.json for deep-topic targeting
    KEYWORDS_ALL = _keywords_cfg
    
    PRIMARY_KEYWORDS = (
        os.getenv("PRIMARY_KEYWORDS", "").split(",")
        if os.getenv("PRIMARY_KEYWORDS")
        else _keywords_cfg.get("primary", [])
    )
    CURATED_KEYWORDS = (
        os.getenv("CURATED_KEYWORDS", "").split(",")
        if os.getenv("CURATED_KEYWORDS")
        else _keywords_cfg.get("curated", [])
    )
    LOCATION_KEYWORDS = (
        os.getenv("LOCATION_KEYWORDS", "").split(",")
        if os.getenv("LOCATION_KEYWORDS")
        else _keywords_cfg.get("location", [])
    )
    FORBIDDEN_KEYWORDS = (
        os.getenv("FORBIDDEN_KEYWORDS", "").split(",")
        if os.getenv("FORBIDDEN_KEYWORDS")
        else _keywords_cfg.get("forbidden", [])
    )

    # Filter out empty strings from splitting
    PRIMARY_KEYWORDS = [k.strip() for k in PRIMARY_KEYWORDS if k.strip()]
    CURATED_KEYWORDS = [k.strip() for k in CURATED_KEYWORDS if k.strip()]
    LOCATION_KEYWORDS = [k.strip() for k in LOCATION_KEYWORDS if k.strip()]
    FORBIDDEN_KEYWORDS = [k.strip() for k in FORBIDDEN_KEYWORDS if k.strip()]

    # Places Data
    PLACES_PATH = os.path.join(CONFIG_DIR, "places.json")
    PLACES_DATA = _load_json_config.__func__(PLACES_PATH, {"top_tourist_places": [], "underrated_hidden_gems": []})
    
    # Detailed Places Information (New Researcher Data)
    PLACES_DETAILS_PATH = os.path.join(CONFIG_DIR, "rishikesh_places_details.json")
    PLACES_DETAILS_DATA = _load_json_config.__func__(PLACES_DETAILS_PATH, {"locations": [], "rafting_routes": [], "travel_tips_2026": {}})

    # Scraper Targets & Blacklist (Override with JSON strings in .env if needed)
    SCRAPER_TARGETS = _get_env_json.__func__("SCRAPER_TARGETS", _competitors_cfg.get("scraper_targets", {}))
    SCRAPER_BRAND_BLACKLIST = _get_env_json.__func__(
        "SCRAPER_BRAND_BLACKLIST", _competitors_cfg.get("brand_blacklist", [])
    )

    # Categories
    PRODUCT_CATEGORIES = _get_env_json.__func__("PRODUCT_CATEGORIES", _categories_cfg.get("product_categories", []))
    INDUSTRY_CATEGORIES = _get_env_json.__func__("INDUSTRY_CATEGORIES", _categories_cfg.get("industry_categories", []))

    # Templates & Schema
    TEMPLATES = _get_env_json.__func__("TEMPLATES", _templates_cfg)
    SCHEMA_MAP = _get_env_json.__func__("SCHEMA_MAP", _schema_map_cfg.get("mapping", {}))
    PRODUCT_ID_COL = _schema_map_cfg.get("id_column", os.getenv("PRODUCT_ID_COL", "service_name"))

    IMAGE_GENERATION_RATIO = float(os.getenv("IMAGE_GENERATION_RATIO", "1.0"))

    # SEO Configuration
    MIN_WORD_COUNT = int(os.getenv("MIN_WORD_COUNT", "1000"))
    MAX_WORD_COUNT = int(os.getenv("MAX_WORD_COUNT", "2000"))
    SEO_THRESHOLD = int(os.getenv("SEO_THRESHOLD", "80"))
    MAX_ITERATIONS = int(os.getenv("MAX_ARTICLE_RETRIES", "3"))
    MAX_TOTAL_ARTICLES = int(os.getenv("MAX_TOTAL_ARTICLES", "5000"))

    # Fallback lists are now handled via default .env values or JSON files.
    # To add keywords, update data/config/keywords.json or the .env file.
