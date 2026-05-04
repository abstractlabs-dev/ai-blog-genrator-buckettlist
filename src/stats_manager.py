import os
import json
import logging
from typing import Dict
from threading import Lock

logger = logging.getLogger(__name__)

# Determine stats file path
_stats_file_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "database",
    "stats.json"
)

class StatsManager:
    """
    Manages generation and publishing statistics with persistent storage.
    """
    _stats: Dict[str, any] = {}
    _lock = Lock()  # Thread-safe file operations
    _stats_file = _stats_file_path

    @classmethod
    def _ensure_stats_file(cls):
        """Ensure the stats file exists with proper structure."""
        if not os.path.exists(cls._stats_file):
            os.makedirs(os.path.dirname(cls._stats_file), exist_ok=True)
            default_stats = {
                "generated": {
                    "total": 0
                },
                "published": {
                    "wordpress": 0,
                    "blogger": 0,
                    "tumblr": 0,
                    "total": 0
                }
            }
            with open(cls._stats_file, 'w', encoding='utf-8') as file_handle:
                json.dump(default_stats, file_handle, indent=2)
            logger.info("Created new stats file at %s", cls._stats_file)

    @classmethod
    def _load_stats(cls) -> Dict:
        """Load stats from JSON file."""
        cls._ensure_stats_file()
        try:
            with open(cls._stats_file, 'r', encoding='utf-8') as file_handle:
                return json.load(file_handle)
        except Exception as error:
            logger.error("Failed to load stats from %s: %s", cls._stats_file, error)
            return {
                "generated": {"total": 0},
                "published": {"wordpress": 0, "blogger": 0, "tumblr": 0, "total": 0}
            }

    @classmethod
    def _save_stats(cls, stats: Dict):
        """Save stats to JSON file."""
        try:
            with open(cls._stats_file, 'w', encoding='utf-8') as file_handle:
                json.dump(stats, file_handle, indent=2)
        except Exception as error:
            logger.error("Failed to save stats to %s: %s", cls._stats_file, error)

    @classmethod
    def increment_generated(cls):
        """Increment the count of generated articles."""
        with cls._lock:
            stats = cls._load_stats()
            stats["generated"]["total"] = stats.get("generated", {}).get("total", 0) + 1
            cls._save_stats(stats)
            logger.info("Incremented generated articles count: %s", stats["generated"]["total"])

    @classmethod
    def increment_published(cls, platform: str):
        """Increment the count of published articles for a specific platform."""
        with cls._lock:
            stats = cls._load_stats()

            # Ensure the platform key exists
            if platform not in stats["published"]:
                stats["published"][platform] = 0

            # Increment platform-specific count
            stats["published"][platform] += 1

            # Recalculate total published (excluding 'total' key itself)
            total = sum(v for k, v in stats["published"].items() if k != "total")
            stats["published"]["total"] = total

            cls._save_stats(stats)
            logger.info("Incremented publish stat for %s: %s (Total: %s)",
                       platform, stats["published"][platform], total)

    @classmethod
    def get_stats(cls) -> Dict:
        """Get current statistics."""
        return cls._load_stats()

    @classmethod
    def reset(cls):
        """Reset all statistics to zero."""
        with cls._lock:
            default_stats = {
                "generated": {"total": 0},
                "published": {"wordpress": 0, "blogger": 0, "tumblr": 0, "total": 0}
            }
            cls._save_stats(default_stats)
            logger.info("Reset all statistics to zero")
