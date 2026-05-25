"""
test_model_availability.py
==========================
Standalone script to probe each candidate Gemini model through the SAME
Vertex AI / ADC client used in production and report which are accessible.

Run from the project root:
    python scratch/test_model_availability.py

What it does:
  - Uses exactly the same ClientManager from src/llm_client.py
  - Sends a minimal 5-token prompt ("Say: OK") to each candidate model
  - Prints AVAILABLE or NOT AVAILABLE with the reason
  - Writes a plain-text report to scratch/model_availability_report.txt
  - DOES NOT touch any CSV, stats.json, or vector database files

Results should inform which models to include in the fallback chain inside
src/llm_client.py  (the RATE_LIMIT_FALLBACK_MODELS constant).
"""

from __future__ import annotations

import os
import sys
import time
import datetime
from pathlib import Path
from typing import List, Tuple

# Reconfigure stdout/stderr to use UTF-8 on Windows to prevent UnicodeEncodeError
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# --------------------------------------------------------------------------- #
#  Bootstrap sys.path so we can import from src/ when run from any directory  #
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# --------------------------------------------------------------------------- #
#  Candidate models — ordered by preference as fallbacks                       #
# --------------------------------------------------------------------------- #
CANDIDATE_MODELS: List[str] = [
    # ----- Active Production Models (fully supported) ---------------------- #
    "gemini-2.5-flash",           # Primary production model (may hit rate limits)
    "gemini-2.5-flash-lite",      # Lighter variant — ideal first fallback
    "gemini-2.5-pro",             # Pro variant — high quality secondary fallback
]

# Minimal prompt for availability testing — uses near-zero tokens
TEST_PROMPT = "Respond with exactly the word: OK"

# Per-model timeout for the test call (seconds)
TEST_TIMEOUT_SEC = 30

# --------------------------------------------------------------------------- #
#  Colour helpers (graceful degradation on Windows without ANSI support)       #
# --------------------------------------------------------------------------- #
_USE_COLOR = sys.stdout.isatty() and os.name != "nt"

def _green(s: str) -> str:
    return f"\033[92m{s}\033[0m" if _USE_COLOR else s

def _red(s: str) -> str:
    return f"\033[91m{s}\033[0m" if _USE_COLOR else s

def _yellow(s: str) -> str:
    return f"\033[93m{s}\033[0m" if _USE_COLOR else s

def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _USE_COLOR else s


# --------------------------------------------------------------------------- #
#  Core test logic                                                              #
# --------------------------------------------------------------------------- #

def _test_single_model(client, model_name: str) -> Tuple[bool, str, float]:
    """
    Attempt a minimal generation call to `model_name`.

    Returns:
        (success: bool, message: str, latency_sec: float)
    """
    from google.genai import types

    gen_config = types.GenerateContentConfig(
        temperature=0.0,
        max_output_tokens=5,
    )

    t0 = time.monotonic()
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=TEST_PROMPT,
            config=gen_config,
        )
        latency = time.monotonic() - t0
        text = (response.text or "").strip()
        if not text:
            return False, "Model returned an empty response", latency
        return True, f'Response snippet: "{text[:40]}"', latency

    except Exception as exc:
        latency = time.monotonic() - t0
        err_str = str(exc)

        # Classify the error for a more useful message
        upper = err_str.upper()
        if "429" in upper or "RESOURCE_EXHAUSTED" in upper or "TOO MANY REQUESTS" in upper:
            category = "RATE_LIMITED (quota exhausted — model EXISTS but no quota)"
        elif "404" in upper or "NOT FOUND" in upper or "INVALID" in upper:
            category = "NOT FOUND / INVALID MODEL NAME"
        elif "403" in upper or "PERMISSION" in upper or "FORBIDDEN" in upper:
            category = "PERMISSION DENIED (model not enabled for this project)"
        elif "UNAUTHENTICATED" in upper or "CREDENTIAL" in upper:
            category = "AUTHENTICATION ERROR"
        elif "UNAVAILABLE" in upper or "DEADLINE" in upper or "TIMEOUT" in upper:
            category = "SERVICE UNAVAILABLE (transient)"
        else:
            category = f"ERROR: {err_str[:120]}"

        return False, category, latency


def run_availability_check() -> List[dict]:
    """
    Run the availability check for all CANDIDATE_MODELS.

    Returns a list of result dicts with keys:
        model, available, message, latency_sec
    """
    # Import the production ClientManager — uses same ADC/Vertex AI settings
    try:
        from src.llm_client import ClientManager
        from src.config import Config
    except ImportError as exc:
        print(_red(f"\nFATAL: Cannot import production modules: {exc}"))
        print("Make sure you are running from the project root directory.\n")
        sys.exit(1)

    # Print connection info
    print()
    print(_bold("=" * 65))
    print(_bold("  GEMINI MODEL AVAILABILITY TEST"))
    print(_bold("=" * 65))
    print(f"  Timestamp   : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if Config.USE_VERTEX_AI:
        print(f"  Auth Mode   : Vertex AI (ADC)")
        print(f"  Project     : {Config.GOOGLE_CLOUD_PROJECT}")
        print(f"  Location    : {Config.GOOGLE_CLOUD_LOCATION}")
    elif Config.GOOGLE_AI_STUDIO_API_KEY:
        print(f"  Auth Mode   : Google AI Studio API Key")
    else:
        print(f"  Auth Mode   : Application Default Credentials (ADC) for Gemini API")
    print(f"  Test Prompt : '{TEST_PROMPT}'")
    print(_bold("=" * 65))
    print()

    # Initialise the client once (same singleton as production)
    try:
        client = ClientManager.get_client()
    except Exception as exc:
        print(_red(f"FATAL: Could not initialise GenAI client: {exc}"))
        print("Check your ADC / .env configuration and try again.")
        sys.exit(1)

    results = []
    for model in CANDIDATE_MODELS:
        print(f"  Testing {_bold(model):<50}", end="", flush=True)
        available, message, latency = _test_single_model(client, model)

        if available:
            status_str = _green("✅  AVAILABLE")
        else:
            # Rate-limited models EXIST — mark them differently
            if "RATE_LIMITED" in message:
                status_str = _yellow("⚠️  RATE_LIMITED (exists but quota hit)")
            else:
                status_str = _red("❌  NOT AVAILABLE")

        print(f"  {status_str}  ({latency:.2f}s)")
        if message:
            print(f"              → {message}")

        results.append({
            "model": model,
            "available": available,
            "rate_limited": "RATE_LIMITED" in message,
            "message": message,
            "latency_sec": round(latency, 3),
        })

        # Small gap between calls to avoid burst 429 on the test itself
        time.sleep(1.5)

    return results


def _write_report(results: List[dict]) -> Path:
    """Write a plain-text availability report to scratch/model_availability_report.txt."""
    report_path = PROJECT_ROOT / "scratch" / "model_availability_report.txt"

    lines = [
        "=" * 65,
        "  GEMINI MODEL AVAILABILITY REPORT",
        f"  Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 65,
        "",
        f"{'MODEL':<40} {'STATUS':<25} {'LATENCY':>8}",
        "-" * 78,
    ]

    for r in results:
        if r["available"]:
            status = "AVAILABLE"
        elif r["rate_limited"]:
            status = "RATE_LIMITED (exists)"
        else:
            status = "NOT AVAILABLE"
        lines.append(f"{r['model']:<40} {status:<25} {r['latency_sec']:>7.2f}s")

    lines.append("-" * 78)
    lines.append("")

    available_models = [r["model"] for r in results if r["available"]]
    rate_limited_models = [r["model"] for r in results if r["rate_limited"]]
    unavailable_models = [r["model"] for r in results if not r["available"] and not r["rate_limited"]]

    lines.append("SUMMARY")
    lines.append(f"  Fully Available : {len(available_models)}")
    lines.append(f"  Rate-Limited    : {len(rate_limited_models)}  (model exists, quota issue)")
    lines.append(f"  Not Available   : {len(unavailable_models)}")
    lines.append("")

    if available_models or rate_limited_models:
        lines.append("RECOMMENDED FALLBACK ORDER FOR llm_client.py")
        lines.append("(copy-paste into RATE_LIMIT_FALLBACK_MODELS in src/llm_client.py)")
        lines.append("")

        # Primary is first available (should be gemini-2.5-flash ideally)
        all_working = available_models + rate_limited_models  # rate-limited still work, just throttled
        # Remove primary from fallback display
        fallbacks = [m for m in all_working if m != "gemini-2.5-flash"]
        lines.append("    RATE_LIMIT_FALLBACK_MODELS = [")
        for m in fallbacks:
            lines.append(f'        "{m}",')
        lines.append("    ]")

    lines.append("")
    lines.append("DETAIL")
    for r in results:
        lines.append(f"  {r['model']}: {r['message']}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main():
    results = run_availability_check()

    # Summary banner
    available = [r for r in results if r["available"]]
    rate_limited = [r for r in results if r["rate_limited"]]
    unavailable = [r for r in results if not r["available"] and not r["rate_limited"]]

    print()
    print(_bold("=" * 65))
    print(_bold("  SUMMARY"))
    print(_bold("=" * 65))
    print(f"  {_green('✅  Fully Available')}: {len(available)}")
    for r in available:
        print(f"       - {r['model']}")
    print(f"  {_yellow('⚠️  Rate-Limited')}  : {len(rate_limited)}  (model exists, quota hit)")
    for r in rate_limited:
        print(f"       - {r['model']}")
    print(f"  {_red('❌  Not Available')} : {len(unavailable)}")
    for r in unavailable:
        print(f"       - {r['model']}")

    # Recommended fallback list for llm_client.py
    all_working = [r["model"] for r in results if r["available"] or r["rate_limited"]]
    fallbacks = [m for m in all_working if m != "gemini-2.5-flash"]
    if fallbacks:
        print()
        print(_bold("  Recommended fallback order for src/llm_client.py:"))
        print("    RATE_LIMIT_FALLBACK_MODELS = [")
        for m in fallbacks:
            print(f'        "{m}",')
        print("    ]")

    # Write report file
    report_path = _write_report(results)
    print()
    print(f"  Report written to: {report_path}")
    print(_bold("=" * 65))
    print()


if __name__ == "__main__":
    main()
