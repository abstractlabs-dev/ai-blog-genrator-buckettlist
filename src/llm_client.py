"""
LLM Client Module
This module provides an optimized interface for interacting with Language Models
via LiteLLM. It includes caching, retry logic, and multi-provider fallback support.
"""
import os
import socket
import logging
from typing import Optional, List, Dict, Any, Union, Tuple

from src.config import Config

# --- Dependency Imports with Graceful Fallbacks ---
try:
    import litellm
    from litellm import completion
    from litellm.caching import Cache
    LLM_AVAILABLE = True

    # Configure LiteLLM for optimal performance
    litellm.set_verbose = False
    litellm.logging = False # Further reduce logging noise
    litellm.suppress_handler_errors = True
    litellm.drop_params = True  # Drop unsupported params instead of erroring
    litellm.modify_params = True  # Auto-modify params for different providers

    # Silence Pydantic/LiteLLM logger noise
    logging.getLogger('litellm').setLevel(logging.ERROR)

    # Enable caching if Redis is available (improves performance and reduces costs)
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))

    REDIS_AVAILABLE = False
    try:
        with socket.create_connection((redis_host, redis_port), timeout=0.5):
            REDIS_AVAILABLE = True
    except OSError:
        REDIS_AVAILABLE = False

    if REDIS_AVAILABLE:
        try:
            litellm.cache = Cache(
                type="redis",
                host=redis_host,
                port=redis_port,
            )
            CACHE_ENABLED = True
            logging.info("LiteLLM Redis caching enabled")
        except Exception:
            litellm.cache = Cache()
            CACHE_ENABLED = True
            logging.info("LiteLLM in-memory caching enabled")
    else:
        litellm.cache = Cache()
        CACHE_ENABLED = True
        logging.info("LiteLLM Redis not reachable. Using in-memory caching")

except Exception as error:
    LLM_AVAILABLE = False
    CACHE_ENABLED = False
    logging.warning("litellm is not available: %s. Falling back to offline generation stubs.", error)

logger = logging.getLogger(__name__)


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
    # Original LLM logic below
    if not LLM_AVAILABLE or not Config.GOOGLE_AI_STUDIO_API_KEY:
        raise ConnectionError("LiteLLM is not available or GOOGLE_AI_STUDIO_API_KEY is not set.")

    # LiteLLM expects GEMINI_API_KEY for the Gemini provider. We source it from GOOGLE_AI_STUDIO_API_KEY.
    os.environ["GEMINI_API_KEY"] = Config.GOOGLE_AI_STUDIO_API_KEY

    # Allow users to provide either "gemini-2.0-flash" or "gemini/gemini-2.0-flash".
    model = model.replace("gemini/", "", 1)

    # Default fallback models if not provided
    if fallback_models is None:
        fallback_models = [
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
        ]

    # Try primary model first, then fallbacks
    models_to_try = [model] + [m.replace("gemini/", "", 1) for m in fallback_models if m != model]

    last_error = None
    for attempt_model in models_to_try:
        try:
            logger.debug("Attempting LLM call for [%s] with model: %s", task_name, attempt_model)

            response = completion(
                model=f"gemini/{attempt_model}",  # LiteLLM requires 'gemini/' prefix
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                num_retries=max_retries,
                # Optimization settings
                caching=CACHE_ENABLED
            )

            # Log token usage if available in the response
            if hasattr(response, 'usage') and response.usage:
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens
                total_tokens = response.usage.total_tokens

                # Calculate approximate cost (for Gemini models)
                cost = _calculate_cost(attempt_model, prompt_tokens, completion_tokens)

                logger.info(
                    "Token Usage for [%s] (Model: %s): Prompt=%s, Completion=%s, Total=%s, Approx Cost=$%.4f",
                    task_name, attempt_model, prompt_tokens, completion_tokens, total_tokens, cost
                )

            # Success - return the response
            content = response.choices[0].message.content
            logger.info("Successfully generated [%s] using model: %s", task_name, attempt_model)

            if include_usage:
                usage_data = {}
                if hasattr(response, 'usage') and response.usage:
                    usage_data = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                        "cost": _calculate_cost(
                            attempt_model, response.usage.prompt_tokens, response.usage.completion_tokens
                        )
                    }
                return content, usage_data

            return content

        except Exception as loop_error:  # pylint: disable=broad-exception-caught
            last_error = loop_error
            is_last = models_to_try.index(attempt_model) == len(models_to_try) - 1
            msg = "All models failed." if is_last else "Trying next fallback..."
            logger.warning(
                "Error calling LLM with model %s: %s. %s",
                attempt_model,
                loop_error,
                msg
            )
            continue

    # All attempts failed
    logger.error("All LLM model attempts failed. Last error: %s", last_error, exc_info=True)
    raise Exception(  # pylint: disable=broad-exception-raised
        f"Failed to generate content after trying {len(models_to_try)} models. Last error: {last_error}"
    )


def _calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate approximate cost for Google Gemini models.

    Args:
        model: Model name
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens

    Returns:
        Approximate cost in USD
    """
    # Pricing per 1M tokens (as of April 2026)
    pricing = {
        "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
        "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
        "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-pro": {"input": 0.50, "output": 1.50},
    }

    # Find matching pricing - sort by length descending to match most specific model first
    model_pricing = None
    sorted_keys = sorted(pricing.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in model.lower():
            model_pricing = pricing[key]
            break

    if not model_pricing:
        return 0.0  # Unknown model

    # Calculate cost
    input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]

    return input_cost + output_cost


def get_available_models() -> List[str]:
    """
    Get list of available Gemini models that can be used.

    Returns:
        List of model names
    """
    if not LLM_AVAILABLE:
        return []

    return [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ]


def clear_cache():
    """Clear the LiteLLM cache."""
    if CACHE_ENABLED and LLM_AVAILABLE:
        try:
            litellm.cache.flush()
            logger.info("LiteLLM cache cleared")
        except Exception as clear_error:
            logger.warning("Failed to clear cache: %s", clear_error)
