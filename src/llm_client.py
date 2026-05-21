"""
LLM Client Module
This module provides an optimized interface for interacting with Language Models
via the Google Gen AI SDK (Vertex AI). It includes multi-model fallback support.
"""
import logging
from typing import Optional, List, Dict, Any, Union, Tuple

from google import genai
from google.genai import types
from src.config import Config
from src.models import LLMConfig

logger = logging.getLogger(__name__)

LLM_AVAILABLE = True


class ClientManager:
    """Singleton manager for the GenAI Client."""
    _client: Optional[genai.Client] = None

    @classmethod
    def get_client(cls) -> genai.Client:
        """
        Lazy initialization of the GenAI Client.

        Returns:
            genai.Client: The initialized client instance.
        """
        if cls._client is None:
            try:
                if Config.USE_VERTEX_AI:
                    cls._client = genai.Client(
                        vertexai=True,
                        project=Config.GOOGLE_CLOUD_PROJECT,
                        location=Config.GOOGLE_CLOUD_LOCATION
                    )
                    logger.info(
                        "[CLIENT_INIT] Mode: Vertex AI | Project: %s | Location: %s",
                        Config.GOOGLE_CLOUD_PROJECT,
                        Config.GOOGLE_CLOUD_LOCATION
                    )
                else:
                    if Config.GOOGLE_AI_STUDIO_API_KEY:
                        cls._client = genai.Client(api_key=Config.GOOGLE_AI_STUDIO_API_KEY)
                        logger.info("[CLIENT_INIT] Mode: API Key")
                    else:
                        # Auto-detect local ADC credentials to use the Gemini API (generativelanguage.googleapis.com)
                        cls._client = genai.Client()
                        logger.info("[CLIENT_INIT] Mode: Application Default Credentials (ADC) for Gemini API")
            except Exception as ex:
                logger.error("[CLIENT_INIT_FAILED] Error: %s", ex)
                raise
        return cls._client


def call_llm(
    prompt: str,
    config: Optional[LLMConfig] = None
) -> Union[str, Tuple[str, Dict[str, Any]]]:
    """
    Call the Gemini model via the Google Gen AI SDK with fallback support.

    Args:
        prompt: The text prompt to send to the model.
        config: Configuration parameters for the generation.

    Returns:
        Generated content as a string, or a tuple of (content, usage_data) if requested.
    """
    if config is None:
        config = LLMConfig(model_name=Config.MODEL_NAME)

    client = ClientManager.get_client()

    # Clean model name (remove 'gemini/' prefix if present)
    primary_model = config.model_name.replace("gemini/", "", 1)

    # Default fallback models if none provided
    models_to_try = [primary_model]
    if not config.fallback_models:
        default_fallbacks = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        for model in default_fallbacks:
            clean_m = model.replace("gemini/", "", 1)
            if clean_m != primary_model:
                models_to_try.append(clean_m)
    else:
        for model in config.fallback_models:
            clean_m = model.replace("gemini/", "", 1)
            if clean_m not in models_to_try:
                models_to_try.append(clean_m)

    last_error = None
    import time
    for attempt_model in models_to_try:
        max_429_retries = 5
        backoff_sec = 2.0
        for retry_attempt in range(max_429_retries + 1):
            try:
                logger.debug(
                    "[GENERATION_ATTEMPT] Task: %s | Model: %s (attempt %d)",
                    config.task_name,
                    attempt_model,
                    retry_attempt
                )

                gen_config = types.GenerateContentConfig(
                    temperature=config.temperature,
                    max_output_tokens=config.max_tokens,
                    presence_penalty=config.presence_penalty,
                    frequency_penalty=config.frequency_penalty
                )

                response = client.models.generate_content(
                    model=attempt_model,
                    contents=prompt,
                    config=gen_config
                )

                content = response.text
                if not content:
                    raise ValueError(f"Empty response from model {attempt_model}")

                logger.info(
                    "[GENERATION_SUCCESS] Task: %s | Model: %s",
                    config.task_name,
                    attempt_model
                )

                if config.include_usage:
                    usage_data = _extract_usage_data(response, attempt_model)
                    return content, usage_data

                return content

            except Exception as ex:
                last_error = ex
                err_str = str(ex).upper()
                is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "TOO MANY REQUESTS" in err_str
                
                if is_429 and retry_attempt < max_429_retries:
                    logger.warning(
                        "[GENERATION_429] Model %s hit rate limit (429/RESOURCE_EXHAUSTED). Retrying in %.1fs... Error: %s",
                        attempt_model,
                        backoff_sec,
                        ex
                    )
                    time.sleep(backoff_sec)
                    backoff_sec *= 2.0
                    continue
                else:
                    logger.warning(
                        "[GENERATION_RETRY] Task: %s | Model: %s | Error: %s",
                        config.task_name,
                        attempt_model,
                        ex
                    )
                    break # Go to next model in fallback list

    raise RuntimeError(
        f"[GENERATION_FAILED] All models failed for task {config.task_name}. Last error: {last_error}"
    )


def _extract_usage_data(response: Any, model: str) -> Dict[str, Any]:
    """Extract usage metadata and calculate cost from the SDK response."""
    usage_data = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost": 0.0
    }
    
    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        p_tokens = response.usage_metadata.prompt_token_count
        c_tokens = response.usage_metadata.candidates_token_count
        t_tokens = response.usage_metadata.total_token_count
        
        usage_data.update({
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": t_tokens,
            "cost": _calculate_cost(model, p_tokens, c_tokens)
        })
        
    return usage_data


def _calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate approximate cost for Google Gemini models.
    Pricing per 1M tokens.
    """
    pricing = {
        "gemini-3-flash": {"input": 0.50, "output": 3.00},
        "gemini-3-pro": {"input": 3.00, "output": 15.00},
        "gemini-2.5-flash": {"input": 0.10, "output": 0.40},
        "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
        "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.0-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    }

    model_pricing = None
    # Match the model name against the pricing table
    for key in sorted(pricing.keys(), key=len, reverse=True):
        if key in model.lower():
            model_pricing = pricing[key]
            break

    if not model_pricing:
        return 0.0

    input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]

    return input_cost + output_cost


def get_available_models() -> List[str]:
    """Returns a list of supported Gemini models."""
    return [
        "gemini-3-flash",
        "gemini-3-pro",
        "gemini-2.5-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ]
