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

    print(f"🔄 Loading token file: {token_file}")
    with open(token_file, "rb") as f_handle:
        creds = pickle.load(f_handle)

    # Refresh token if expired
    if creds.expired and creds.refresh_token:
        print("🔄 Refreshing expired token...")
        creds.refresh(Request())

    print("🔌 Connecting to Google Blogger API v3...")
    client = build("blogger", "v3", credentials=creds)

    print("\n🔍 Fetching User Profile Information...")
    try:
        user_info = client.users().get(userId="self").execute()
        print(f"👤 Authenticated User Name: {user_info.get('displayName')}")
        print(f"🔗 Profile URL: {user_info.get('url')}")
    except Exception as e:
        print(f"❌ Failed to fetch user info: {e}")

    target_blog_id = os.getenv("BLOGGER_BLOG_ID")
    print(f"\n🎯 Target Blog ID in .env: {target_blog_id}")

    print("\n📚 Fetching blogs that this authenticated user has access to...")
    try:
        blogs_response = client.blogs().listByUser(userId="self").execute()
        blogs = blogs_response.get("items", [])
        if not blogs:
            print("⚠️ No blogs found for this user account!")
        else:
            print(f"✅ Found {len(blogs)} blog(s):")
            found_target = False
            for idx, blog in enumerate(blogs, 1):
                b_id = blog.get("id")
                b_name = blog.get("name")
                b_url = blog.get("url")
                is_target = "🌟 (MATCHES TARGET!)" if str(b_id) == str(target_blog_id) else ""
                if str(b_id) == str(target_blog_id):
                    found_target = True
                print(f"  {idx}. Name: '{b_name}'")
                print(f"     ID:   {b_id} {is_target}")
                print(f"     URL:  {b_url}")
                print("-" * 40)
            
            if not found_target and target_blog_id:
                print(f"\n❌ CRITICAL: The target Blog ID '{target_blog_id}' is NOT in the list of blogs this account has access to!")
                print("Please double check that the Google account you authenticated with has been invited to this blog and accepted the invite.")
    except Exception as e:
        print(f"❌ Failed to fetch blogs: {e}")

if __name__ == "__main__":
    main()
