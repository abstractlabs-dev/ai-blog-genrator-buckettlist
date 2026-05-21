"""
Diagnostics script to inspect raw LLM response.
"""
import os
import sys
from pathlib import Path

# Bootstrap project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.config import Config
from src.agents import ContentGeneratorAgent
from src.llm_client import call_llm
from src.models import LLMConfig
from prompts.prompts import create_content_prompt

def check_generation():
    Config.validate_api_key()
    
    title = "Top 5 Thrilling River Rafting Routes in Rishikesh"
    keywords = [
        "river rafting in rishikesh",
        "rishikesh rafting packages",
        "best rafting season in rishikesh",
        "rafting cost in rishikesh",
        "rapids in rishikesh"
    ]
    category = "Adventure Tourism"
    
    # Generate the context exactly as agents.py does
    places_context = ""
    if hasattr(Config, "PLACES_DATA") and Config.PLACES_DATA:
        top_places = Config.PLACES_DATA.get("top_tourist_places", [])
        if top_places:
            places_context += "\n**MUST MENTION SOME OF THESE TOP PLACES:**\n"
            for p in top_places[:3]:
                places_context += f"- {p['name']}: {p['description']}\n"
                
    if hasattr(Config, "PLACES_DETAILS_DATA") and Config.PLACES_DETAILS_DATA:
        locations = Config.PLACES_DETAILS_DATA.get("locations", [])
        if locations:
            places_context += "\n### Key Locations Details:\n"
            for loc in locations[:4]:
                places_context += f"- {loc.get('name')}: Famous for {loc.get('famous_for')}\n"
        rafting = Config.PLACES_DETAILS_DATA.get("rafting_routes", [])
        if rafting:
            places_context += "\n### River Rafting Route Options:\n"
            for route in rafting[:4]:
                places_context += f"- {route['name']}: {route['distance']}, Grade {route['grade']}\n"
                
    prompt = create_content_prompt(
        title=title,
        reference_text="",
        target_keywords=keywords,
        project_context=places_context,
        article_type="generic",
        category=category
    )
    
    print("Calling LLM...")
    response = call_llm(
        prompt,
        config=LLMConfig(
            model_name=Config.MODEL_NAME,
            max_tokens=4500,
            temperature=0.3,
            task_name="Diagnostics Gen",
            include_usage=False
        )
    )
    
    raw_path = Path("scratch/raw_response.txt")
    raw_path.write_text(response, encoding="utf-8")
    print(f"Raw response written to {raw_path}")
    print(f"Length of response: {len(response)} chars")
    print(f"Word count of response: {len(response.split())} words")

if __name__ == "__main__":
    check_generation()
