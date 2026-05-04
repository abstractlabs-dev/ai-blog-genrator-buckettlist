"""
SocialExporter
==============
Generates platform-native, copy-paste-ready JSON files for LinkedIn and Medium
after each article is successfully published to WordPress.

Output files
------------
  data/output/social/linkedin/YYYY-MM-DD_<slug>.json
  data/output/social/medium/YYYY-MM-DD_<slug>.json

Medium JSON
-----------
Follows the Medium Publishing API v1 format (POST /v1/users/{userId}/posts).
- contentFormat: "html"
- publishStatus:  "draft"  ← always draft so the client can review before publishing
- canonicalUrl:   live WordPress URL (protects SEO, tells Medium this isn't the original)
- Related articles are appended as an HTML block at the bottom of the content.
- Includes step-by-step instructions inside _meta.

LinkedIn JSON
-------------
Follows the LinkedIn Posts API (/rest/posts) format.
- Post type: link share (article card)
- The "commentary" field contains a hook, key insight, 3 related-article teasers,
  and a CTA back to the full article — all ready to copy-paste.
- LinkedIn does NOT support canonical tags, so we never post full content.
  Instead: excerpt + link card. This is the SEO-safe, platform-recommended strategy.
- Hashtags derived from article keywords are appended to commentary.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from src.config import Config
from src.models import ArticleDraft

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace — for generating plain-text excerpts."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _excerpt(text: str, max_chars: int = 300) -> str:
    """Return a clean excerpt up to max_chars, breaking on a word boundary."""
    clean = _strip_html(text)
    if len(clean) <= max_chars:
        return clean
    cut = clean[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


def _keywords_to_hashtags(keywords: List[str], max_tags: int = 7) -> str:
    """Convert keyword list to LinkedIn-style hashtags, CamelCase, max max_tags."""
    hashtags = []
    seen = set()
    for kw in keywords:
        if len(hashtags) >= max_tags:
            break
        # Clean: remove special chars, title-case each word, join
        words = re.findall(r"[a-zA-Z0-9]+", kw)
        if not words:
            continue
        tag = "#" + "".join(w.capitalize() for w in words)
        if tag.lower() not in seen:
            seen.add(tag.lower())
            hashtags.append(tag)
    return " ".join(hashtags)


def _keywords_to_medium_tags(keywords: List[str], max_tags: int = 5) -> List[str]:
    """
    Convert keywords to Medium tags (max 5, lowercase, no spaces — Medium requirement).
    Medium allows up to 5 tags; tags must be single words or hyphenated.
    """
    tags = []
    seen: set = set()
    # Always include brand / location tags first
    priority = ["rishikesh", "adventure", "travel", "india", "adventure-sports"]
    for pt in priority:
        if len(tags) >= max_tags:
            break
        if pt not in seen:
            seen.add(pt)
            tags.append(pt)

    for kw in keywords:
        if len(tags) >= max_tags:
            break
        kw_clean = re.sub(r"[^a-z0-9\- ]", "", kw.lower().strip())
        kw_clean = re.sub(r"\s+", "-", kw_clean).strip("-")
        if kw_clean and kw_clean not in seen:
            seen.add(kw_clean)
            tags.append(kw_clean)

    return tags[:max_tags]


def _build_related_html_block(related_articles: List[Dict]) -> str:
    """
    Build an HTML block listing related articles — appended to Medium content.
    """
    if not related_articles:
        return ""
    items = "".join(
        f'<li><a href="{a["url"]}">{a["title"]}</a></li>'
        for a in related_articles
    )
    return (
        f"<hr/>"
        f"<h3>You Might Also Like</h3>"
        f"<ul>{items}</ul>"
    )


def _build_related_linkedin_text(related_articles: List[Dict]) -> str:
    """Build a short text snippet listing related articles for the LinkedIn commentary."""
    if not related_articles:
        return ""
    lines = ["📌 More reads you'll love:"]
    for a in related_articles:
        lines.append(f"   → {a['title']} — {a['url']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class SocialExporter:
    """
    Generates LinkedIn and Medium ready-to-paste JSON files for each published article.

    Usage
    -----
    exporter = SocialExporter()
    exporter.export(article, wp_url="https://...", wp_slug="slug", related_articles=[...])
    """

    def __init__(self):
        self.linkedin_dir = Config.SOCIAL_LINKEDIN_DIR
        self.medium_dir   = Config.SOCIAL_MEDIUM_DIR
        os.makedirs(self.linkedin_dir, exist_ok=True)
        os.makedirs(self.medium_dir,   exist_ok=True)

    # ------------------------------------------------------------------
    # Public: single entry point
    # ------------------------------------------------------------------

    def export(
        self,
        article: ArticleDraft,
        wp_url: str,
        wp_slug: str = "",
        related_articles: Optional[List[Dict]] = None,
    ) -> Dict[str, str]:
        """
        Generate both LinkedIn and Medium JSON files for a published article.

        Args:
            article:          The generated article draft.
            wp_url:           Live WordPress permalink (from API response).
            wp_slug:          The slug WordPress assigned.
            related_articles: List of related articles [{title, url, score}].

        Returns:
            Dict with keys 'linkedin_path' and 'medium_path'.
        """
        related = related_articles or []
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_slug = wp_slug or re.sub(r"[^a-z0-9-]", "-", article.title.lower())[:50]
        filename_base = f"{date_str}_{safe_slug}"

        linkedin_path = self._export_linkedin(article, wp_url, related, filename_base)
        medium_path   = self._export_medium(article, wp_url, wp_slug, related, filename_base)

        logger.info(
            "Social exports generated:\n  LinkedIn → %s\n  Medium   → %s",
            linkedin_path, medium_path
        )
        return {
            "linkedin_path": linkedin_path,
            "medium_path":   medium_path,
        }

    # ------------------------------------------------------------------
    # LinkedIn
    # ------------------------------------------------------------------

    def _export_linkedin(
        self,
        article: ArticleDraft,
        wp_url: str,
        related: List[Dict],
        filename_base: str,
    ) -> str:
        """
        Build a LinkedIn post JSON in the Posts API v2 format.

        Strategy: EXCERPT + LINK CARD (SEO-safe — no full content duplication).
        LinkedIn does not support canonical tags, so posting full content there
        would create duplicate-content risk for the main website's SEO.
        """
        title       = article.metadata.title or article.title
        description = article.metadata.description or ""
        keywords    = list(article.metadata.keywords or [])

        # Build hook — first 2 sentences of the article
        raw_text   = _strip_html(article.content_html or "")
        hook_text  = _excerpt(raw_text, max_chars=280)

        # Build hashtags from keywords
        hashtags = _keywords_to_hashtags(
            keywords + [
                "Rishikesh", "Adventure", "Travel", "India", Config.BRAND_NAME
            ]
        )

        # Related articles block
        related_text = _build_related_linkedin_text(related)

        # Full commentary — what the client pastes into LinkedIn
        commentary_parts = [
            f"🏔️ {title}",
            "",
            hook_text,
            "",
        ]
        if related_text:
            commentary_parts += [related_text, ""]
        commentary_parts += [
            f"📖 Read the full guide: {wp_url}",
            "",
            hashtags,
        ]
        commentary = "\n".join(commentary_parts)

        payload = {
            "author": "urn:li:person:YOUR_MEMBER_ID",
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
            "content": {
                "article": {
                    "source": wp_url,
                    "title": title,
                    "description": description[:200] if description else "",
                }
            },
            "related_articles": related,
            "_meta": {
                "platform": "linkedin",
                "generated_at": datetime.now().isoformat(),
                "wp_url": wp_url,
                "wp_slug": filename_base.split("_", 1)[-1],
                "instructions": (
                    "1. Replace 'YOUR_MEMBER_ID' with your LinkedIn person or organization ID.\n"
                    "2. Copy the 'commentary' field and paste it into LinkedIn's post composer.\n"
                    "3. The article card (title + description + URL) will auto-preview from the link.\n"
                    "4. Alternatively POST this JSON to LinkedIn /rest/posts with your Bearer token.\n"
                    "   Required headers: Content-Type: application/json, "
                    "X-Restli-Protocol-Version: 2.0.0, LinkedIn-Version: 202504"
                )
            }
        }

        path = os.path.join(self.linkedin_dir, f"{filename_base}.json")
        self._write_json(path, payload)
        return path

    # ------------------------------------------------------------------
    # Medium
    # ------------------------------------------------------------------

    def _export_medium(
        self,
        article: ArticleDraft,
        wp_url: str,
        wp_slug: str,
        related: List[Dict],
        filename_base: str,
    ) -> str:
        """
        Build a Medium post JSON in the Publishing API v1 format.

        Strategy: FULL CONTENT + CANONICAL URL.
        Medium supports canonical URLs — the system sets this to the live WordPress
        URL, so Google knows the main site is the original. Safe for SEO.
        """
        title       = article.metadata.title or article.title
        keywords    = list(article.metadata.keywords or [])

        # Prepare content: main HTML + related articles block + canonical note
        main_html = article.content_html or f"<h1>{title}</h1>"

        # Append FAQ if available and not already in content
        faq_html = article.faq_section or ""
        if faq_html and faq_html.strip() not in main_html:
            main_html = main_html + "\n" + faq_html

        # Append related articles block
        related_html = _build_related_html_block(related)

        # Append canonical attribution note (Medium best practice)
        attribution = (
            f"<hr/>"
            f"<p><em>This article was originally published at "
            f"<a href='{wp_url}'>{Config.BRAND_NAME}</a>.</em></p>"
        )

        full_content = main_html + "\n" + related_html + "\n" + attribution

        # Medium tags: max 5, lowercase
        tags = _keywords_to_medium_tags(keywords)

        payload = {
            "title": title,
            "contentFormat": "html",
            "content": full_content,
            "tags": tags,
            "publishStatus": "draft",
            "canonicalUrl": wp_url,
            "related_articles": related,
            "_meta": {
                "platform": "medium",
                "generated_at": datetime.now().isoformat(),
                "wp_url": wp_url,
                "wp_slug": wp_slug,
                "instructions": (
                    "HOW TO PUBLISH ON MEDIUM:\n"
                    "Option A — Manual (Recommended):\n"
                    "  1. Go to medium.com > Write a story.\n"
                    "  2. Copy the 'content' field HTML and paste into the Medium editor.\n"
                    "  3. Set the title to the 'title' field.\n"
                    "  4. Click the '...' menu > More Settings > Advanced Settings.\n"
                    "  5. Check 'This story was originally published elsewhere'.\n"
                    "  6. Paste the 'canonicalUrl' value and Save canonical link.\n"
                    "  7. Add tags from the 'tags' array.\n"
                    "  8. Publish!\n\n"
                    "Option B — API:\n"
                    "  POST https://api.medium.com/v1/users/{userId}/posts\n"
                    "  Header: Authorization: Bearer YOUR_MEDIUM_INTEGRATION_TOKEN\n"
                    "  Body: this JSON (remove _meta and related_articles fields)."
                )
            }
        }

        path = os.path.join(self.medium_dir, f"{filename_base}.json")
        self._write_json(path, payload)
        return path

    # ------------------------------------------------------------------
    # Util
    # ------------------------------------------------------------------

    @staticmethod
    def _write_json(path: str, data: dict) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            logger.debug("Written: %s", path)
        except Exception as exc:
            logger.error("Failed to write social export to %s: %s", path, exc)
