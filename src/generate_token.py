import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow

# Blogger API scope
SCOPES = ["https://www.googleapis.com/auth/blogger"]

def generate_token(credentials_file, token_file):
    # Create OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)

    # This will open a browser to log in and grant permission
    creds = flow.run_local_server(port=0)

    # Ensure tokens folder exists
    os.makedirs("tokens", exist_ok=True)

    # Save token
    with open(token_file, "wb") as f_handle:
        pickle.dump(creds, f_handle)

    print(f"✅ Token saved: {token_file}")

# Generate token for your first blog
#generate_token("src/credentials1.json", "tokens/blogger1.pkl")
#generate_token("src/credentials2.json", "tokens/blogger2.pkl")
generate_token("src/credentials3.json", "tokens/blogger3.pkl")

