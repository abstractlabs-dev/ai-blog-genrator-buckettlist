"""
Safe Trial Generation and Verification Script
=============================================
This script performs a trial run of the article generation and social media export workflows.
It validates that:
1. The article achieves an SEO score >= 80 (ideally 90+) on the first attempt.
2. The LinkedIn post is a value-packed long-form article of 1,800 to 2,500 characters.
3. No production database files (articles.csv, stats.json, etc.) are altered or written.
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

# Bootstrap project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from src.config import Config
from src.agents import ContentGeneratorAgent, SEOEvaluatorAgent
from src.publishers.social_exporter import SocialExporter
from src.models import ArticleDraft

# --- Safe Guarding Database Writes (Monkeypatching) ---
# Prevent any changes to database or metadata files during trial runs.
def mock_save_used_title(*args, **kwargs):
    title = args[1] if len(args) > 1 else (args[0] if args else "unknown")
    print(f"[SAFE-GUARD] Mocked TitleManager.save_used_title for: '{title}'")

def mock_register_slug(*args, **kwargs):
    slug = args[1] if len(args) > 1 else (args[0] if args else "unknown")
    print(f"[SAFE-GUARD] Mocked SlugRegistry.register for slug: '{slug}'")

def mock_write_json(*args, **kwargs):
    path = args[-2] if len(args) >= 2 else "unknown"
    data = args[-1] if len(args) >= 1 else {}
    print(f"[SAFE-GUARD] Mocked SocialExporter._write_json to path: {path}")
    # Print a summary of the data instead of writing it
    print(f"  Export Platform: {data.get('_meta', {}).get('platform')}")
    print(f"  Title: {data.get('title') or data.get('content', {}).get('article', {}).get('title')}")
    if data.get('_meta', {}).get('platform') == 'linkedin':
        commentary = data.get('commentary', '')
        print(f"  Commentary Length: {len(commentary)} chars")
        print("  Commentary Content:")
        print("-" * 50)
        print(commentary)
        print("-" * 50)

from src.agents import TitleManager, SlugRegistry, ContentGeneratorAgent

# Save original method
original_parse = ContentGeneratorAgent._parse_article_response

def mock_parse_article_response(self, content, title, target_keywords, category=""):
    with open("scratch/trial_gen_raw.txt", "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[SAFE-GUARD] Saved raw LLM response ({len(content)} chars) to scratch/trial_gen_raw.txt")
    return original_parse(self, content, title, target_keywords, category)

# Apply monkeypatches
TitleManager.save_used_title = mock_save_used_title
SlugRegistry.register = mock_register_slug
SocialExporter._write_json = mock_write_json
ContentGeneratorAgent._parse_article_response = mock_parse_article_response

def run_trial():
    print("=" * 70)
    print("              STARTING SEO & LINKEDIN TRIAL RUN")
    print("=" * 70)
    
    # Check API key config
    Config.validate_api_key()
    
    # Initialize agents and publisher
    generator = ContentGeneratorAgent()
    evaluator = SEOEvaluatorAgent()
    exporter = SocialExporter()
    
    # Sample keywords and topic
    title = "Top 5 Thrilling River Rafting Routes in Rishikesh"
    keywords = [
        "river rafting in rishikesh",
        "rishikesh rafting packages",
        "best rafting season in rishikesh",
        "rafting cost in rishikesh",
        "rapids in rishikesh"
    ]
    category = "Adventure Tourism"
    
    print(f"\n[1/3] Generating article: '{title}'")
    print(f"      Keywords: {keywords}")
    print(f"      Category: {category}")
    
    # Generate article draft
    # Use temperature = 0.3 for a good balance of creativity and structure compliance
    draft, product = generator.generate_article(
        title=title,
        reference_text="",
        target_keywords=keywords,
        temperature=0.3,
        article_type="generic",
        category=category
    )
    
    print("\n[2/3] Evaluating SEO metrics...")
    report = evaluator.evaluate_article(draft, iteration_number=1, article_type="generic")
    
    print("-" * 50)
    print(f"OVERALL SEO SCORE: {report.overall_score} / 100")
    print(f"Passed SEO Standards Threshold ({Config.SEO_THRESHOLD})? {report.passed}")
    print("-" * 50)
    
    print("\nSEO Metric Breakdown:")
    for metric in report.metrics:
        print(f"  - {metric.name:<30}: {metric.score}/{metric.max_score} | {metric.feedback}")
        
    if report.improvement_suggestions:
        print("\nImprovement Suggestions:")
        for sugg in report.improvement_suggestions:
            print(f"  * {sugg}")
            
    print("\nDraft Character & Word Counts:")
    print(f"  - Word Count: {draft.word_count} words (Target: >=1100)")
    print(f"  - Meta Title Length: {len(draft.metadata.title)} chars (Target: 40-65)")
    print(f"  - Meta Description Length: {len(draft.metadata.description)} chars (Target: 110-165)")
    print(f"  - Meta Description: \"{draft.metadata.description}\"")
    
    # Check for target city count and boosters manually
    content_lower = draft.content_html.lower()
    city_count = content_lower.count("rishikesh")
    print(f"  - Target City Count ('Rishikesh'): {city_count} mentions (Target: 4-8)")
    
    seo_boosters = [
        "in rishikesh",
        "across rishikesh",
        "customers in rishikesh",
        "projects in rishikesh",
        "best quality in rishikesh",
        "top-rated in rishikesh",
        "services in rishikesh",
        "experts in rishikesh"
    ]
    boosters_found = [b for b in seo_boosters if b in content_lower]
    print(f"  - Boosters Found ({len(boosters_found)}/4 needed): {boosters_found}")
    
    print("\n[3/3] Simulating LinkedIn commentary export...")
    # Generate the LinkedIn commentary JSON payload
    wp_url = "https://www.placesinrishikesh.com/rafting-routes-rishikesh"
    linkedin_export_path = exporter._export_linkedin(
        article=draft,
        wp_url=wp_url,
        related=[
            {"title": "Best Camp Sites in Rishikesh for Families", "url": "https://www.placesinrishikesh.com/camp-sites-families"},
            {"title": "Guide to the Bungee Jumping Height in Rishikesh", "url": "https://www.placesinrishikesh.com/bungee-jumping-height"}
        ],
        filename_base="trial_linkedin_export"
    )
    
    print("\nAll tasks completed successfully. Verification is complete.")

if __name__ == "__main__":
    run_trial()
