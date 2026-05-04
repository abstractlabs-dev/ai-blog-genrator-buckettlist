import base64
import logging
from typing import Optional, Tuple

import requests

from src.config import Config

logger = logging.getLogger(__name__)

# Pricing per image for tested models
IMAGE_PRICING = {
    # Imagen 4.0 models (tested and working)
    "imagen-4.0-generate-001": 0.04,
    "imagen-4.0-fast-generate-001": 0.02,
    "imagen-4.0-ultra-generate-001": 0.06,
    # Gemini models (tested and working - free during preview)
    "gemini-2.0-flash-exp-image-generation": 0.00,
    "gemini-2.0-flash-exp": 0.00,
    "default": 0.04
}

def generate_blog_image(prompt: str) -> Tuple[Optional[bytes], float]:
    """
    Generates an image using Google's Imagen/Gemini API.

    Fallback order (only tested models):
    1. imagen-4.0-generate-001 (best quality)
    2. imagen-4.0-fast-generate-001 (faster)
    3. imagen-4.0-ultra-generate-001 (ultra quality)
    4. gemini-2.0-flash-exp-image-generation (free fallback)
    5. gemini-2.0-flash-exp (free fallback)

    Returns: (image_bytes, cost_usd)
    """
    api_key = Config.GOOGLE_AI_STUDIO_API_KEY
    if not api_key:
        logger.warning("GOOGLE_AI_STUDIO_API_KEY not set. Skipping image generation.")
        return None, 0.0

    masked_key = f"{api_key[:5]}...{api_key[-5:]}" if len(api_key) > 10 else "***"
    logger.info("Attempting image generation with Gemini API key: %s", masked_key)

    headers = {"Content-Type": "application/json"}

    # ONLY tested models in priority order:
    # 1. Imagen 4.0 models (best quality, try first)
    # 2. Gemini Flash models (free fallback if Imagen rate limited)
    models_to_try = [
        # Imagen 4.0 - Primary (tested and working)
        {
            "model": "imagen-4.0-generate-001",
            "type": "imagen",
            "url": (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"imagen-4.0-generate-001:predict?key={api_key}"
        ),
        },
        {
            "model": "imagen-4.0-fast-generate-001",
            "type": "imagen",
            "url": (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"imagen-4.0-fast-generate-001:predict?key={api_key}"
        ),
        },
        {
            "model": "imagen-4.0-ultra-generate-001",
            "type": "imagen",
            "url": (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"imagen-4.0-ultra-generate-001:predict?key={api_key}"
        ),
        },
        # Gemini Flash - Fallback (tested and working, free during preview)
        {
            "model": "gemini-2.0-flash-exp-image-generation",
            "type": "gemini",
            "url": (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash-exp-image-generation:generateContent?key={api_key}"
        ),
        },
        {
            "model": "gemini-2.0-flash-exp",
            "type": "gemini",
            "url": (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash-exp:generateContent?key={api_key}"
        ),
        },
    ]

    for config in models_to_try:
        model = config["model"]
        model_type = config["type"]

        try:
            logger.info("Trying %s for image generation...", model)

            # Build payload based on model type
            if model_type == "gemini":
                payload = {
                    "contents": [{
                        "parts": [{
                        "text": (
                        f"Create a PURELY VISUAL photorealistic professional blog banner "
                        f"image for: {prompt}. STRICT MANDATE: DO NOT include any text, "
                        "letters, titles, names, words or characters of any kind. "
                        "The image must be 100% pure visual imagery without any written "
                        "words, typography, or signage whatsoever. Focus on materials, "
                        "textures, and the realistic professional environment."
                    )
                        }]
                    }],
                    "generationConfig": {
                        "responseModalities": ["image", "text"]
                    }
                }
            else:  # imagen
                payload = {
                    "instances": [{"prompt": prompt}],
                    "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}
                }

            response = requests.post(config["url"], headers=headers, json=payload, timeout=120)

            if response.status_code == 200:
                result = response.json()

                # Handle Gemini response format
                if model_type == "gemini":
                    candidates = result.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            if "inlineData" in part:
                                b64_data = part["inlineData"].get("data", "")
                                if b64_data:
                                    cost = IMAGE_PRICING.get(model, IMAGE_PRICING["default"])
                                    logger.info("SUCCESS: Image generated using %s (Cost: $%.4f)", model, cost)
                                    return base64.b64decode(b64_data), cost

                # Handle Imagen response format
                else:
                    predictions = result.get("predictions", [])
                    if predictions:
                        first_pred = predictions[0]
                        b64_data = ""
                        if isinstance(first_pred, str):
                            b64_data = first_pred
                        elif isinstance(first_pred, dict):
                            b64_data = first_pred.get("bytesBase64Encoded") or first_pred.get("b64") or ""

                        if b64_data:
                            cost = IMAGE_PRICING.get(model, IMAGE_PRICING["default"])
                            logger.info("SUCCESS: Image generated using %s (Cost: $%.4f)", model, cost)
                            return base64.b64decode(b64_data), cost

                logger.warning("%s response did not contain image data", model)

            elif response.status_code == 429:
                # Rate limited - try next model
                logger.warning("Rate limit (429) for %s. Trying next model...", model)
                continue
            elif response.status_code == 503:
                # Service unavailable - try next model
                logger.warning("Service unavailable (503) for %s. Trying next model...", model)
                continue
            else:
                error_body = response.text[:400] if response.text else "No error body"
                logger.warning("%s failed with HTTP %s: %s", model, response.status_code, error_body)
                continue

        except requests.exceptions.Timeout:
            logger.warning("Timeout for %s. Trying next model...", model)
            continue
        except Exception as err:
            logger.error("Exception during %s generation: %s", model, str(err))
            continue

    logger.warning("All image generation models failed or rate limited.")
    logger.info("TIP: Check your Gemini API quota at https://aistudio.google.com/app/plan")
    return None, 0.0
