import os
import json
import threading
from typing import Any, Dict, List, Optional

from ..config import Config


class TumblrAccountSelector:
    def __init__(self, rest_client_cls, tumblr_api_available: bool):
        self._rest_client_cls = rest_client_cls
        self._tumblr_api_available = tumblr_api_available

        self._lock = threading.Lock()
        self._next_index = 0
        self._accounts: List[Dict[str, Any]] = []

        if not self._tumblr_api_available:
            return

        accounts_cfg = self._load_accounts_config()
        for account in accounts_cfg:
            blog_hostname = (account or {}).get("blog_hostname")
            consumer_key = (account or {}).get("consumer_key")
            consumer_secret = (account or {}).get("consumer_secret")
            token_file = (account or {}).get("token_file")
            token_file = self._resolve_token_file(token_file)

            if not blog_hostname or not consumer_key or not consumer_secret or not token_file:
                continue

            tokens = self._load_tokens(token_file)
            client = self._rest_client_cls(
                consumer_key,
                consumer_secret,
                tokens["access_token"],
                tokens["access_token_secret"],
            )

            self._accounts.append(
                {
                    "blog_hostname": blog_hostname,
                    "consumer_key": consumer_key,
                    "consumer_secret": consumer_secret,
                    "token_file": token_file,
                    "client": client,
                }
            )

    def is_configured(self) -> bool:
        return bool(self._tumblr_api_available and self._accounts)

    def next_account(self) -> Dict[str, Any]:
        if not self._accounts:
            raise ValueError("No Tumblr accounts configured")

        with self._lock:
            idx = self._next_index
            self._next_index = (self._next_index + 1) % len(self._accounts)
            return self._accounts[idx]

    def _resolve_token_file(self, token_file: Optional[str]) -> Optional[str]:
        if not token_file:
            return None
        if os.path.isabs(token_file):
            return token_file
        return os.path.join(Config.PROJECT_ROOT, token_file)

    def _load_accounts_config(self) -> List[Dict[str, str]]:
        """
        Dynamically discover and load Tumblr accounts from environment variables.

        Returns:
            List of account configuration dictionaries.
        """
        accounts: List[Dict[str, str]] = []

        # Dynamically discover all numbered credential suffixes from environment keys
        numbered_indices = set()
        for key in os.environ:
            if key.startswith("TUMBLR_BLOG_HOSTNAME"):
                suffix = key[len("TUMBLR_BLOG_HOSTNAME"):]
                if suffix.isdigit():
                    numbered_indices.add(int(suffix))

        # Load each discovered numbered account
        for idx in sorted(numbered_indices):
            blog_hostname = os.getenv(f"TUMBLR_BLOG_HOSTNAME{idx}")
            consumer_key = os.getenv(f"TUMBLR_CONSUMER_KEY{idx}")
            consumer_secret = os.getenv(f"TUMBLR_CONSUMER_SECRET{idx}")
            token_file = os.getenv(f"TUMBLR_TOKEN_FILE{idx}")
            if blog_hostname and consumer_key and consumer_secret and token_file:
                accounts.append(
                    {
                        "blog_hostname": blog_hostname,
                        "consumer_key": consumer_key,
                        "consumer_secret": consumer_secret,
                        "token_file": token_file,
                    }
                )

        if accounts:
            return accounts

        # Fallback to single account credentials
        blog_hostname = os.getenv("TUMBLR_BLOG_HOSTNAME")
        consumer_key = os.getenv("TUMBLR_CONSUMER_KEY")
        consumer_secret = os.getenv("TUMBLR_CONSUMER_SECRET")
        token_file = os.getenv("TUMBLR_TOKEN_FILE")

        if blog_hostname and consumer_key and consumer_secret:
            if not token_file:
                token_file = os.path.join(Config.PROJECT_ROOT, "tumblr_token.json")
            accounts.append(
                {
                    "blog_hostname": blog_hostname,
                    "consumer_key": consumer_key,
                    "consumer_secret": consumer_secret,
                    "token_file": token_file,
                }
            )

        return accounts

    def _load_tokens(self, token_file: str) -> Dict[str, str]:
        if not os.path.exists(token_file):
            raise FileNotFoundError(
                f"Tumblr token file not found at {token_file}. "
                "Please authenticate with Tumblr and save the token file."
            )

        with open(token_file, "r", encoding="utf-8") as f_handle:
            data = json.load(f_handle)

        if "access_token" not in data or "access_token_secret" not in data:
            raise ValueError("Invalid Tumblr token file. Missing access_token or access_token_secret")

        return data
