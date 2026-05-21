import os
import json
import sys
from pathlib import Path
from requests_oauthlib import OAuth1Session

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from dotenv import load_dotenv

def generate_tumblr_token():
    load_dotenv()
    
    # Check for Consumer Key and Secret
    client_key = os.getenv("TUMBLR_CONSUMER_KEY")
    client_secret = os.getenv("TUMBLR_CONSUMER_SECRET")
    
    if not client_key or not client_secret:
        print("\n[ERROR] TUMBLR_CONSUMER_KEY and/or TUMBLR_CONSUMER_SECRET not found in .env!")
        print("Please register an app at https://www.tumblr.com/oauth/apps and add the keys to .env.")
        sys.exit(1)
        
    request_token_url = 'https://www.tumblr.com/oauth/request_token'
    authorization_base_url = 'https://www.tumblr.com/oauth/authorize'
    access_token_url = 'https://www.tumblr.com/oauth/access_token'
    
    print("\n=== Tumblr API Token Generator ===")
    print("1. Fetching request token...")
    try:
        oauth = OAuth1Session(client_key, client_secret=client_secret)
        fetch_response = oauth.fetch_request_token(request_token_url)
        resource_owner_key = fetch_response.get('oauth_token')
        resource_owner_secret = fetch_response.get('oauth_token_secret')
    except Exception as e:
        print(f"\n[ERROR] Failed to fetch request token: {e}")
        print("Ensure your Consumer Key and Secret are correct.")
        sys.exit(1)
        
    # Get authorization
    authorization_url = oauth.authorization_url(authorization_base_url)
    print("\n2. Please go to the following URL in your browser and authorize the app:")
    print("-" * 60)
    print(authorization_url)
    print("-" * 60)
    
    # Get the redirect URL from the user
    redirect_response = input("\n3. After clicking 'Allow', you will be redirected. Paste the FULL redirect URL here:\n> ").strip()
    
    if not redirect_response:
        print("No URL provided. Exiting.")
        sys.exit(1)
        
    try:
        oauth.parse_authorization_response(redirect_response)
    except Exception as e:
        print(f"\n[ERROR] Failed to parse the redirect URL. Make sure you copy the entire URL. Error: {e}")
        sys.exit(1)
        
    print("\n4. Fetching access token...")
    try:
        oauth = OAuth1Session(
            client_key,
            client_secret=client_secret,
            resource_owner_key=resource_owner_key,
            resource_owner_secret=resource_owner_secret,
            verifier=oauth.token.get("oauth_verifier")
        )
        oauth_tokens = oauth.fetch_access_token(access_token_url)
    except Exception as e:
        print(f"\n[ERROR] Failed to fetch access token: {e}")
        sys.exit(1)
        
    # Save tokens to tumblr_token.json
    token_data = {
        "access_token": oauth_tokens.get("oauth_token"),
        "access_token_secret": oauth_tokens.get("oauth_token_secret")
    }
    
    token_file = "tumblr_token.json"
    with open(token_file, "w") as f:
        json.dump(token_data, f, indent=4)
        
    print(f"\n✅ SUCCESS! Tokens saved to '{token_file}'")
    print("Your Tumblr API integration is now ready to use!")

if __name__ == "__main__":
    generate_tumblr_token()
