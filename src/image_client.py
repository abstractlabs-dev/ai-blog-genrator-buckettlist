"""
Image Generation Client Module
This module provides interface for generating blog banner images via Google's Imagen.
It includes rate limiting and multi-model fallback support.
"""
import logging
import random
import threading
import time
from typing import Optional, Tuple

from google import genai

from src.config import Config
from src.llm_client import ClientManager, TokenBucketLimiter

logger = logging.getLogger(__name__)

# Pricing per image for tested models (May 2026 rates)
IMAGE_PRICING = {
    "imagen-4.0-ultra-001": 0.06,
    "imagen-4.0-generate-001": 0.04,  # Standard
    "imagen-4.0-fast-001": 0.02,
    "imagen-3.0-generate-001": 0.04,
    "default": 0.04
}


class ImagenLimiterManager:
    """Manages the thread-safe token bucket rate limiter for Imagen."""

    _limiter: Optional[TokenBucketLimiter] = None
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get_limiter(cls) -> Optional[TokenBucketLimiter]:
        """
        Get or initialize the rate limiter.

        Returns:
            The TokenBucketLimiter instance, or None if rate limiting is disabled.
        """
        if not Config.RATE_LIMIT_ENABLED:
            return None

        with cls._lock:
            if cls._limiter is None:
                rpm: float = Config.IMAGEN_RPM_LIMIT
                # Capacity 1.0 since Imagen has extremely low concurrent quota
                cls._limiter = TokenBucketLimiter(capacity=1.0, fill_rate=rpm / 60.0)
                logger.info("[RATE_LIMIT_INIT] Created Imagen limiter with %.1f RPM", rpm)
            return cls._limiter


def generate_blog_image(prompt: str) -> Tuple[Optional[bytes], float]:
    """
    Generates an image using Google's Imagen via the Gen AI SDK.

    Args:
        prompt: The text prompt for generating the image.

    Returns:
        A tuple of (image_bytes, cost), or (None, 0.0) if generation failed.
    """
    try:
        client = ClientManager.get_client()
    except (RuntimeError, ValueError, TypeError, OSError, AttributeError, LookupError) as e:
        logger.error("Could not initialize GenAI Client for image generation: %s", e)
        return None, 0.0

    primary_model: str = Config.IMAGE_MODEL or "imagen-3.0-generate-001"

    # Supported image models in Vertex AI
    models_to_try = [
        primary_model,
        "imagen-4.0-ultra-001",
        "imagen-4.0-generate-001",
        "imagen-4.0-fast-001",
        "imagen-3.0-generate-001",
    ]

    # Remove duplicates while preserving order
    models_to_try = list(dict.fromkeys(models_to_try))

    for model in models_to_try:
        max_retries: int = 2  # Total of 3 attempts per model
        for attempt in range(max_retries + 1):
            try:
                limiter = ImagenLimiterManager.get_limiter()
                if limiter:
                    limiter.acquire()

                logger.info(
                    "Attempting image generation with model: %s (attempt %d/%d)",
                    model,
                    attempt + 1,
                    max_retries + 1
                )

                response = client.models.generate_images(
                    model=model,
                    prompt=prompt,
                    config={
                        "number_of_images": 1,
                        "aspect_ratio": "16:9"
                    }
                )

                if response.generated_images:
                    image_data = response.generated_images[0].image.image_bytes
                    cost = IMAGE_PRICING.get(model, IMAGE_PRICING["default"])
                    logger.info("SUCCESS: Image generated using %s (Cost: $%.4f)", model, cost)
                    return image_data, cost

                logger.warning("Model %s returned success but no images were generated.", model)
                break

            except (
                RuntimeError, ValueError, TypeError, OSError,
                AttributeError, LookupError, genai.errors.APIError
            ) as e:
                is_429: bool = any(k in str(e).upper() for k in ("429", "RESOURCE_EXHAUSTED", "TOO MANY REQUESTS"))

                if is_429 and attempt < max_retries:
                    sleep_duration: float = (2.0 ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(
                        "Rate limit hit for image model %s. Retrying in %.1fs... Error: %s",
                        model,
                        sleep_duration,
                        e
                    )
                    time.sleep(sleep_duration)
                    continue

                logger.warning(
                    "Error generating image with %s (attempt %d/%d): %s",
                    model, attempt + 1, max_retries + 1, e
                )
                break

    logger.warning("All image generation models failed.")
    return None, 0.0
