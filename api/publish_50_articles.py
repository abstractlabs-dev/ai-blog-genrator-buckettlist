import os
import sys
from pathlib import Path

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from src.config import Config
from src.services import BlogGeneratorOrchestrator
from src.concurrent_manager import ConcurrentCampaignManager

def main():
    print("🚀 [START] Initializing large-scale blog publishing engine...")
    Config.ensure_directories()
    orchestrator = BlogGeneratorOrchestrator()
    campaign_manager = ConcurrentCampaignManager(orchestrator)
    
    print("\n📦 [RUNNING] Starting full production campaign: 50 articles | 6 concurrent workers | Publishing to WordPress...\n")
    campaign_manager.run_campaign(
        total_articles=50,
        max_workers=6,
        publish_to_wordpress=True,
        publish_to_blogger=False,
        publish_to_tumblr=False
    )
    print("\n✅ [SUCCESS] WordPress 50-article campaign completed successfully!")

if __name__ == "__main__":
    main()
