import os
import re
import logging
from typing import Dict, Any
import markdown

from ..config import Config
from ..models import ArticleDraft
from ..stats_manager import StatsManager
from .tumblr_account_selector import TumblrAccountSelector

logger = logging.getLogger(__name__)

# Lazy import to avoid dependency issues if pytumblr isn't installed
try:
    import pytumblr
    PYTUMBLR_AVAILABLE = True
except ImportError:
    PYTUMBLR_AVAILABLE = False
    logger.warning("pytumblr library not available. Tumblr publishing will be disabled.")


class TumblrPublisher:
    """
    Publisher for Tumblr platform.
    """

    def __init__(self):
        self.blog_hostname = os.getenv("TUMBLR_BLOG_HOSTNAME")
        self.consumer_key = os.getenv("TUMBLR_CONSUMER_KEY")
        self.consumer_secret = os.getenv("TUMBLR_CONSUMER_SECRET")
        self.token_file = os.getenv("TUMBLR_TOKEN_FILE", os.path.join(Config.PROJECT_ROOT, "tumblr_token.json"))

        if not PYTUMBLR_AVAILABLE:
            logger.warning("Tumblr publisher initialized but pytumblr library is not installed.")
            self.client = None
            return
        self._selector = TumblrAccountSelector(
            rest_client_cls=pytumblr.TumblrRestClient if PYTUMBLR_AVAILABLE else None,
            tumblr_api_available=PYTUMBLR_AVAILABLE,
        )

        if not self._selector.is_configured():
            logger.warning(
                "Tumblr Config Missing: TUMBLR_BLOG_HOSTNAME1..3 (or TUMBLR_BLOG_HOSTNAME)"
            )

    def is_configured(self) -> bool:
        """Check if Tumblr is properly configured."""
        return self._selector.is_configured()

    def publish_article(self, article: ArticleDraft, _image_path: str = None) -> Dict[str, Any]:
        """
        Publish an article to Tumblr.

        Args:
            article: The article draft to publish
            image_path: Optional path to featured image (not currently used by Tumblr text posts)

        Returns:
            Dictionary with publication result including 'url' and 'id'
        """
        if not self.is_configured():
            raise ValueError("Tumblr not configured properly. Check credentials and token file.")

        account = self._selector.next_account()
        client = account["client"]
        blog_hostname = account["blog_hostname"]

        # Convert Markdown to HTML
        def convert_markdown_to_html(text: str) -> str:
            if not text:
                return ""
            html_content = markdown.markdown(
                text,
                extensions=[
                    'markdown.extensions.extra',
                    'markdown.extensions.tables',
                    'markdown.extensions.sane_lists',
                    'markdown.extensions.toc'
                ]
            )
            return html_content

        # Convert both main content and FAQ section from Markdown to HTML
        content_ctx = {
            "main": convert_markdown_to_html(article.content_html),
            "faq": convert_markdown_to_html(article.faq_section),
            "full": ""
        }

        # Check if FAQ is already embedded in main content to prevent duplication
        faq_markers = [
            '<div class="faq-section">',
            '<h2>Frequently Asked Questions',
            '<h2>Frequently Asked Question',
            '<h2>FAQ',
            '<h3>FAQ',
            '<strong>Frequently Asked Questions'
        ]
        faq_found = any(marker.lower() in content_ctx["main"].lower() for marker in faq_markers)

        if faq_found:
            logger.info("FAQ section appears to be already embedded in main content, skipping duplicate FAQ append")
            content_ctx["faq"] = ""  # Don't append FAQ again

        full_content = f"{content_ctx['main']}\n{content_ctx['faq']}" if content_ctx["faq"] else content_ctx["main"]
        content_ctx["full"] = full_content

        body = re.sub(
            r"^\s*<h1[^>]*>.*?</h1>\s*",
            "",
            content_ctx["full"],
            flags=re.DOTALL | re.IGNORECASE,
        )
        if not body.strip():
            body = content_ctx["full"]

        # Build tags list from article metadata
        tags = []
        if hasattr(article, "category") and article.category:
            tags.append(article.category)
        if hasattr(article, "parent_category") and article.parent_category:
            tags.append(article.parent_category)

        # Add SEO keywords as tags
        if article.metadata.focus_keyword:
            tags.append(article.metadata.focus_keyword)

        if article.metadata.keywords:
            existing_tags = {t.lower() for t in tags}
            count = 0
            for keyword in article.metadata.keywords:
                if keyword.lower() not in existing_tags:
                    tags.append(keyword)
                    existing_tags.add(keyword.lower())
                    count += 1
                if count >= 10:  # Tumblr handles tags well, let's include more
                    break

        try:
            logger.info("Publishing article '%s' to Tumblr...", article.title)

            response = client.create_text(
                blog_hostname,
                state="published",
                title=article.metadata.title or article.title,
                body=body,
                tags=tags,
                slug=article.metadata.url_slug
            )

            # Tumblr's Python client may return either a top-level id/id_string
            # or nest it under a "response" key depending on version.
            post_id = None

            if isinstance(response, dict):
                post_id = response.get("id") or response.get("id_string")

                # Older/nested shape: {"response": {"id": ...}}
                if not post_id and isinstance(response.get("response"), dict):
                    inner = response["response"]
                    post_id = inner.get("id") or inner.get("id_string")

            if not post_id:
                raise ValueError(f"Unexpected Tumblr response: {response}")

            post_url = f"https://{blog_hostname}/post/{post_id}"

            result = {
                "id": str(post_id),
                "url": post_url,
                "title": article.metadata.title or article.title,
                "blog_hostname": blog_hostname,
            }

            logger.info("Successfully published to Tumblr! Post ID: %s - URL: %s", post_id, post_url)

            # Update stats
            try:
                StatsManager.increment_published("tumblr")
            except Exception as err:
                logger.warning("Failed to update stats for Tumblr publish: %s", err)

            return result

        except Exception as err:
            logger.error("Failed to publish to Tumblr: %s", err)
            raise
