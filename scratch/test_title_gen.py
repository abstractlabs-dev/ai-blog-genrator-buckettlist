import os
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

load_dotenv(project_root / '.env')

# Override hosts to localhost since we are running outside docker network
os.environ['REDIS_HOST'] = 'localhost'
os.environ['WEAVIATE_HOST'] = 'localhost'

from src.config import Config
from src.agents import ContentGeneratorAgent

def main():
    print("Initializing ContentGeneratorAgent...")
    generator = ContentGeneratorAgent()
    
    print("\nTesting generate_titles with generic:")
    try:
        titles = generator.generate_titles(num=1, article_type='generic')
        print(f"Titles returned: {titles}")
    except Exception as e:
        print(f"FAILED with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
