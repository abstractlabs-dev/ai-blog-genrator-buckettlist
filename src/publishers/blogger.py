import logging
import html
import re
from typing import Dict, Any
import markdown

from ..models import ArticleDraft
from ..stats_manager import StatsManager
from .blogger_account_selector import BloggerAccountSelector

logger = logging.getLogger(__name__)

# Lazy import to avoid dependency issues if google libraries aren't installed
try:
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    build = None
    Request = None
    logger.warning("Google API libraries not available. Blogger publishing will be disabled.")


class BloggerPublisher:
    """
    Publisher for Google Blogger platform.
    """

    def __init__(self):
        self._selector = BloggerAccountSelector(
            build_fn=build,
            request_cls=Request,
            google_api_available=GOOGLE_API_AVAILABLE
        )

        if not self._selector.is_configured():
            logger.warning("Blogger Config Missing: BLOGGER_BLOG_ID1..3 (or BLOGGER_BLOG_ID)")

    def is_configured(self) -> bool:
        """Check if Blogger is properly configured."""
        return self._selector.is_configured()

    def publish_article(self, article: ArticleDraft, _image_path: str = None) -> Dict[str, Any]:
        """
        Publish an article to Blogger.

        Args:
            article: The article draft to publish
            image_path: Optional path to featured image (not currently used by Blogger API)

        Returns:
            Dictionary with publication result including 'url' and 'id'
        """
        if not self.is_configured():
            raise ValueError("Blogger not configured properly. Check BLOGGER_BLOG_ID1..3 and token files.")

        account = self._selector.next_account()
        client = account["client"]
        blog_id = account["blog_id"]

        html_tag_re = re.compile(r"<[a-zA-Z][^>]*>")

        def cleanup_generated_artifacts(text: str) -> str:
            if not text:
                return ""

            cleaned = text
            cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
            cleaned = re.sub(r"<script\b[^>]*>.*?</script\s*>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
            cleaned = re.sub(r"<style\b[^>]*>.*?</style\s*>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)

            cleaned = re.sub(r"```(?:html)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = cleaned.replace("```", "")

            cleaned = re.sub(
                r"(?im)^\s*(note:|please\s+note:).*$",
                "",
                cleaned,
            )
            cleaned = re.sub(
                r"(?im)^\s*\.{3,}\s*$",
                "",
                cleaned,
            )

            cleaned = re.sub(r"\\textbf\{([^}]+)\}", r"<strong>\1</strong>", cleaned)
            cleaned = re.sub(r"\\textit\{([^}]+)\}", r"<em>\1</em>", cleaned)

            # Remove full HTML document structures
            cleaned = re.sub(r"<!DOCTYPE[^>]*>", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"<html\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"</html>", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"<head\b[^>]*>.*?</head>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
            cleaned = re.sub(r"<body\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"</body>", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"<meta\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"<link\b[^>]*>", "", cleaned, flags=re.IGNORECASE)

            # Fix malformed headers and other tags like <h2Setting -> <h2>Setting or <pText -> <p>Text
            # We look for a valid tag name followed immediately by something that is NOT a space, >, or /
            cleaned = re.sub(r"<((?:h[1-6])|p|ul|ol|li|div|strong|b|em|i|span|blockquote)(?=[^>\s/])", r"<\1>", cleaned, flags=re.IGNORECASE)

            cleaned = re.sub(r"(?<![</])\b(h[1-6]|p|ul|ol|li|div|strong|b)\s*>", r"<\1>", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"(?<!<)\b/(h[1-6]|p|ul|ol|li|div|strong|b)\s*>", r"</\1>", cleaned, flags=re.IGNORECASE)

            cleaned = re.sub(r"<\s+(h[1-6]|p|ul|ol|li|div|strong|b)\b", r"<\1", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"<\s+/\s*(h[1-6]|p|ul|ol|li|div|strong|b)\b", r"</\1", cleaned, flags=re.IGNORECASE)

            return cleaned

        def ensure_html(text: str) -> str:
            if not text:
                return ""

            unescaped = text
            for _ in range(3):
                next_unescaped = html.unescape(unescaped)
                if next_unescaped == unescaped:
                    break
                unescaped = next_unescaped

            cleaned = cleanup_generated_artifacts(unescaped)

            if cleaned != text and ("&lt;" in text or "&gt;" in text or "&amp;lt;" in text or "&amp;gt;" in text):
                logger.info("Detected escaped HTML entities in Blogger content; unescaping before publish.")

            if html_tag_re.search(cleaned):
                return cleaned

            return markdown.markdown(
                cleaned,
                extensions=[
                    'markdown.extensions.extra',
                    'markdown.extensions.tables',
                    'markdown.extensions.sane_lists',
                    'markdown.extensions.toc'
                ]
            )

        # Convert both main content and FAQ section from Markdown to HTML
        content_ctx = {
            "main": ensure_html(article.content_html),
            "faq": ensure_html(article.faq_section),
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

        if "&lt;" in content_ctx["full"] or "&gt;" in content_ctx["full"]:
            logger.warning(
                "Blogger post body still contains HTML entities like &lt; or &gt;. "
                "If tags appear on the live blog, content may be getting escaped upstream."
            )

        # Prepare post body
        body = {
            "kind": "blogger#post",
            "title": article.metadata.title or article.title,
            "content": content_ctx["full"],
        }

        # Add labels (categories/tags) if available
        labels = []
        if hasattr(article, "category") and article.category:
            labels.append(article.category)
        if hasattr(article, "parent_category") and article.parent_category:
            labels.append(article.parent_category)

        # Add SEO keywords as labels
        if article.metadata.focus_keyword:
            labels.append(article.metadata.focus_keyword)
        if article.metadata.keywords:
            # Add up to 5 additional unique keywords
            existing_labels = {l.lower() for l in labels}
            count = 0
            for keyword in article.metadata.keywords:
                if keyword.lower() not in existing_labels:
                    labels.append(keyword)
                    existing_labels.add(keyword.lower())
                    count += 1
                if count >= 5:
                    break

        if labels:
            body["labels"] = labels

        try:
            logger.info("Publishing article '%s' to Blogger...", article.title)
            post = (
                client.posts()
                .insert(blogId=blog_id, body=body, isDraft=False)
                .execute()
            )

            result = {
                "id": post.get("id"),
                "url": post.get("url"),
                "published": post.get("published"),
                "title": post.get("title")
            }

            logger.info("Successfully published to Blogger! Post ID: %s - URL: %s", result["id"], result["url"])

            # Update stats
            try:
                StatsManager.increment_published("blogger")
            except Exception as err:
                logger.warning("Failed to update stats for Blogger publish: %s", err)

            return result

        except Exception as err:
            logger.error("Failed to publish to Blogger: %s", err)
            raise
