import os
import sys
from pathlib import Path

# Bootstrap project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from google.genai import types
from src.config import Config
from src.llm_client import call_llm, ClientManager
from src.models import LLMConfig, ArticleDraft, Metadata
from prompts.prompts import create_linkedin_prompt

def test_raw_linkedin():
    # Make sure we can log in
    Config.validate_api_key()

    title = "Top 5 Thrilling River Rafting Routes in Rishikesh"
    # Construct a sample draft content
    content_html = """
    <h1>Top 5 Thrilling River Rafting Routes in Rishikesh</h1>
    <p>River rafting in Rishikesh is one of the most adventurous sports in India. The Ganges offers various classes of rapids suitable for both beginners and experts.</p>
    <h2>1. Brahmpuri to Rishikesh (9 km)</h2>
    <p>This is a mild route, perfect for beginners and families. It features Class I and II rapids. The cost is affordable and the package is highly sought after by first-timers.</p>
    <h2>2. Shivpuri to Rishikesh (16 km)</h2>
    <p>The most popular route, offering a mix of thrill and scenic beauty. It has Class III rapids like Roller Coaster and Golf Course. It's the best quality rafting experience in Rishikesh.</p>
    <h2>3. Marine Drive to Rishikesh (26 km)</h2>
    <p>A challenging route requiring good stamina. Includes major rapids that will test your grit.</p>
    <h2>4. Byasi to Rishikesh (30 km)</h2>
    <p>An advanced route with high grade rapids.</p>
    <h2>5. Kaudiyala to Rishikesh (36 km)</h2>
    <p>The ultimate challenge with Class IV+ rapids like The Wall. Only for experienced rafters.</p>
    """
    keywords = ["river rafting in rishikesh", "rishikesh rafting packages", "best rafting season in rishikesh"]

    prompt = create_linkedin_prompt(title, content_html, keywords)
    print("--- PROMPT SENT ---")
    
    client = ClientManager.get_client()
    attempt_model = Config.MODEL_NAME.replace("gemini/", "", 1)
    gen_config = types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=4096,
    )
    
    print("Calling Gemini model directly...")
    res = client.models.generate_content(
        model=attempt_model,
        contents=prompt,
        config=gen_config
    )
    
    print("--- RESPONSE METADATA ---")
    candidate = res.candidates[0]
    print(f"Finish Reason: {candidate.finish_reason}")
    if hasattr(candidate, 'safety_ratings'):
        print(f"Safety Ratings: {candidate.safety_ratings}")
    
    response = res.text
    print("--- RAW LLM RESPONSE ---")
    print(f"Length: {len(response)} characters")
    print("-" * 50)
    print(response)
    print("-" * 50)

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    test_raw_linkedin()
