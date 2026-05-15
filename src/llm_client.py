"""
LLM Client Module
This module provides an optimized interface for interacting with Language Models
via the Google Gen AI SDK (Vertex AI). It includes caching and multi-model fallback support.
"""
import logging
from typing import Optional, List, Dict, Any, Union, Tuple

from google import genai
from src.config import Config

logger = logging.getLogger(__name__)

# Global client instance
_client = None

def get_client():
    """Lazy initialization of the GenAI Client."""
    global _client
    if _client is None:
        try:
            if Config.USE_VERTEX_AI:
                _client = genai.Client(
                    vertexai=True,
                    project=Config.GOOGLE_CLOUD_PROJECT,
                    location=Config.GOOGLE_CLOUD_LOCATION
                )
                logger.info("GenAI Client initialized using Vertex AI (Project: %s)", Config.GOOGLE_CLOUD_PROJECT)
            else:
                if not Config.GOOGLE_AI_STUDIO_API_KEY:
                    raise ValueError("GOOGLE_AI_STUDIO_API_KEY is not set and Vertex AI is disabled.")
                _client = genai.Client(api_key=Config.GOOGLE_AI_STUDIO_API_KEY)
                logger.info("GenAI Client initialized using API Key")
        except Exception as e:
            logger.error("Failed to initialize GenAI Client: %s", e)
            raise
    return _client

def call_llm(
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    fallback_models: Optional[List[str]] = None,
    presence_penalty: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    timeout: int = 60,
    max_retries: int = 2,
    include_usage: bool = False,
    task_name: str = "LLM Generation"
) -> Union[str, Tuple[str, Dict[str, Any]]]:
    """
    Call the Gemini model via the Google Gen AI SDK.
    """
    client = get_client()

    # Clean model name
    model = model.replace("gemini/", "", 1)

    # Default fallback models
    if fallback_models is None:
        fallback_models = [
            "gemini-2.5-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]

    models_to_try = [model] + [m.replace("gemini/", "", 1) for m in fallback_models if m != model]

    last_error = None
    for attempt_model in models_to_try:
        try:
            logger.debug("Attempting LLM call for [%s] with model: %s", task_name, attempt_model)

            # Using types.GenerateContentConfig for the SDK
            from google.genai import types
            gen_config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens
            )

            response = client.models.generate_content(
                model=attempt_model,
                contents=prompt,
                config=gen_config
            )

            content = response.text
            if not content:
                raise ValueError(f"Empty response from model {attempt_model}")

            logger.info("Successfully generated [%s] using model: %s", task_name, attempt_model)

            # Usage data calculation (simplified for SDK)
            usage_data = {}
            if include_usage:
                # The SDK response usually includes usage metadata
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    usage_data = {
                        "prompt_tokens": response.usage_metadata.prompt_token_count,
                        "completion_tokens": response.usage_metadata.candidates_token_count,
                        "total_tokens": response.usage_metadata.total_token_count,
                        "cost": _calculate_cost(
                            attempt_model, 
                            response.usage_metadata.prompt_token_count, 
                            response.usage_metadata.candidates_token_count
                        )
                    }
                return content, usage_data

            return content

        except Exception as loop_error:
            last_error = loop_error
            is_last = models_to_try.index(attempt_model) == len(models_to_try) - 1
            msg = "All models failed." if is_last else "Trying next fallback..."
            logger.warning("Error calling LLM with model %s: %s", attempt_model, loop_error)
            logger.info(msg)
            continue

    raise Exception(f"Failed to generate content after trying {len(models_to_try)} models. Last error: {last_error}")

def _calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate approximate cost for Google Gemini models.
    """
    pricing = {
        "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
        "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
        "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-pro": {"input": 0.50, "output": 1.50},
    }

    model_pricing = None
    sorted_keys = sorted(pricing.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in model.lower():
            model_pricing = pricing[key]
            break

    if not model_pricing:
        return 0.0

    input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]

    return input_cost + output_cost

def get_available_models() -> List[str]:
    return [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ]

def clear_cache():
    # google-genai SDK handles caching internally if enabled on GCP, 
    # but there's no direct 'clear_cache' like in LiteLLM for this wrapper.
    logger.info("Clear cache called (no-op for GenAI SDK wrapper)")
