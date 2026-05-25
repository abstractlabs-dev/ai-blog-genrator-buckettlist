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

    print(f"[SUCCESS] Token saved: {token_file}")

# Generate tokens for any credentials files that exist
for i in (1, 2, 3):
    cred_paths = [
        f"src/credentials/credentials{i}.json",
        f"src/credentials{i}.json"
    ]
    cred_path = None
    for cp in cred_paths:
        if os.path.exists(cp):
            cred_path = cp
            break

    tok_path = f"tokens/blogger{i}.pkl"
    if cred_path:
        print(f"[FOUND] Found {cred_path}. Starting authentication flow...")
        try:
            generate_token(cred_path, tok_path)
        except Exception as e:
            print(f"[ERROR] Error generating token for {cred_path}: {e}")
    else:
        print(f"[INFO] credentials{i}.json not found in src/ or src/credentials/, skipping.")




