import logging
import os
import pickle
import threading
from typing import Any, Dict, List, Optional

from ..config import Config

logger = logging.getLogger(__name__)


class BloggerAccountSelector:
    def __init__(self, build_fn, request_cls, google_api_available: bool):
        self._build_fn = build_fn
        self._request_cls = request_cls
        self._google_api_available = google_api_available

        self._lock = threading.Lock()
        self._next_index = 0
        self._accounts: List[Dict[str, Any]] = []

        if not self._google_api_available:
            return

        accounts_cfg = self._load_accounts_config()
        for account in accounts_cfg:
            blog_id = (account or {}).get("blog_id")
            token_file = (account or {}).get("token_file")
            token_file = self._resolve_token_file(token_file)

            if not blog_id or not token_file:
                continue

            try:
                creds = self._load_credentials(token_file)
                client = self._build_fn("blogger", "v3", credentials=creds)
                self._accounts.append(
                    {
                        "blog_id": blog_id,
                        "token_file": token_file,
                        "client": client,
                    }
                )
            except (FileNotFoundError, Exception) as error:
                logger.warning(
                    "Failed to initialize Blogger account %s with token %s: %s",
                    blog_id, token_file, error
                )
                continue

    def is_configured(self) -> bool:
        return bool(self._google_api_available and self._accounts)

    def next_account(self) -> Dict[str, Any]:
        if not self._accounts:
            raise ValueError("No Blogger accounts configured")

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
        accounts: List[Dict[str, str]] = []

        for i in (1, 2, 3):
            blog_id = os.getenv(f"BLOGGER_BLOG_ID{i}")
            token_file = os.getenv(f"BLOGGER_TOKEN_FILE{i}")
            if blog_id and token_file:
                accounts.append({"blog_id": blog_id, "token_file": token_file})

        if accounts:
            return accounts

        blog_id = os.getenv("BLOGGER_BLOG_ID")
        token_file = os.getenv("BLOGGER_TOKEN_FILE")
        if blog_id and token_file:
            return [{"blog_id": blog_id, "token_file": token_file}]

        token_file_default = os.path.join(Config.PROJECT_ROOT, "blogger_token.pkl")
        if blog_id:
            return [{"blog_id": blog_id, "token_file": token_file_default}]

        return []

    def _load_credentials(self, token_file: str):
        if not os.path.exists(token_file):
            raise FileNotFoundError(
                f"blogger token file not found at {token_file}. "
                "Please authenticate with Google and save the token file."
            )

        with open(token_file, "rb") as f_handle:
            creds = pickle.load(f_handle)

        if creds.expired and creds.refresh_token:
            creds.refresh(self._request_cls())
            token_dir = os.path.dirname(token_file)
            if token_dir:
                os.makedirs(token_dir, exist_ok=True)
            with open(token_file, "wb") as f_handle:
                pickle.dump(creds, f_handle)

        return creds
