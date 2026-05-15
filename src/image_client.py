import base64
import logging
from typing import Optional, Tuple

from src.config import Config
from src.llm_client import get_client

logger = logging.getLogger(__name__)

# Pricing per image for tested models
IMAGE_PRICING = {
    "imagen-3.0-generate-001": 0.04,
    "imagen-3.0-fast-generate-001": 0.02,
    "imagen-4.0-generate-001": 0.04,
    "default": 0.04
}

def generate_blog_image(prompt: str) -> Tuple[Optional[bytes], float]:
    """
    Generates an image using Google's Imagen via the Gen AI SDK.
    """
    try:
        client = get_client()
    except Exception as e:
        logger.error("Could not initialize GenAI Client for image generation: %s", e)
        return None, 0.0

    # Model priority: User configured model first, then fallbacks
    primary_model = Config.IMAGE_MODEL or "imagen-3.0-generate-001"
    
    # Supported image models in Vertex AI
    models_to_try = [
        primary_model,
        "imagen-3.0-generate-001",
        "imagen-3.0-fast-generate-001",
    ]

    # Remove duplicates while preserving order
    models_to_try = list(dict.fromkeys(models_to_try))

    for model in models_to_try:
        try:
            logger.info("Attempting image generation with model: %s", model)
            
            # Using the SDK's generate_images method
            response = client.models.generate_images(
                model=model,
                prompt=prompt,
                config={
                    "number_of_images": 1,
                    "aspect_ratio": "16:9",
                    "add_watermark": False # Set as per preference
                }
            )

            if response.generated_images:
                image_data = response.generated_images[0].image.image_bytes
                cost = IMAGE_PRICING.get(model, IMAGE_PRICING["default"])
                logger.info("SUCCESS: Image generated using %s (Cost: $%.4f)", model, cost)
                return image_data, cost
            
            logger.warning("Model %s returned success but no images were generated.", model)

        except Exception as e:
            logger.warning("Error generating image with %s: %s", model, e)
            continue

    logger.warning("All image generation models failed.")
    return None, 0.0
