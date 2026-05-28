import os
import sys
import pickle
from pathlib import Path

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from googleapiclient.discovery import build
from google.auth.transport.requests import Request

def main():
    token_file = "tokens/blogger1.pkl"
    if not os.path.exists(token_file):
        print(f"❌ Error: Token file not found at {token_file}")
        return

    with open(token_file, "rb") as f_handle:
        creds = pickle.load(f_handle)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    client = build("blogger", "v3", credentials=creds)
    blog_id = os.getenv("BLOGGER_BLOG_ID")

    print(f"🔄 Test 1: Inserting post as DRAFT (isDraft=True) with full details...")
    body_full = {
        "kind": "blogger#post",
        "title": "Blogger API Draft Test Post",
        "content": "<p>This is a test draft post created via Google Blogger API v3 from the AI Blog Generator.</p>",
        "labels": ["Test", "Draft"]
    }
    try:
        post = client.posts().insert(blogId=blog_id, body=body_full, isDraft=True).execute()
        print(f"✅ Success! Draft post created. ID: {post.get('id')} - URL: {post.get('url')}")
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")

    print(f"\n🔄 Test 2: Inserting post as LIVE (isDraft=False) with minimal body...")
    body_minimal = {
        "kind": "blogger#post",
        "title": "Blogger API Live Minimal Test Post",
        "content": "This is a live minimal test post."
    }
    try:
        post = client.posts().insert(blogId=blog_id, body=body_minimal, isDraft=False).execute()
        print(f"✅ Success! Live post created. ID: {post.get('id')} - URL: {post.get('url')}")
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")

if __name__ == "__main__":
    main()
