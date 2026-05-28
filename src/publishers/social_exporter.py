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
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import google.genai.errors

from src.config import Config
from src.models import ArticleDraft, LLMConfig
from src.llm_client import call_llm
from prompts.prompts import create_linkedin_prompt

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


def _build_related_linkedin_text_link_free(related_articles: List[Dict]) -> str:
    """Build a short text snippet listing related articles without URLs."""
    if not related_articles:
        return ""
    lines = ["📌 More reads you'll love (links in the comment section!):"]
    for a in related_articles:
        lines.append(f"   → {a['title']}")
    return "\n".join(lines)


def _get_random_first_comment(wp_url: str) -> str:
    """Generate a highly natural, randomized first comment containing the link."""
    templates = [
        "🔗 Read the complete detailed travel guide here: {url}",
        "👉 Get all the insider tips, costs, and safety info in our full guide: {url}",
        "The full article with step-by-step planning details is live here: {url}",
        "Check out our complete, updated guide for all details: {url}",
        "🔗 We compiled everything you need to know in our full guide: {url}",
        "Read the full story and plan your trip here: {url}"
    ]
    return random.choice(templates).format(url=wp_url)


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
        medium_path   = self._export_medium(article, wp_url, related, filename_base)

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

    def _truncate_commentary(self, text: str, max_chars: int) -> str:
        """Truncate commentary to max_chars breaking at last sentence boundary."""
        if len(text) <= max_chars:
            return text
        logger.warning("LinkedIn commentary too long. Truncating...")
        sliced = text[:max_chars]
        boundary_matches = list(re.finditer(r'[.!?](\s|\n|$)', sliced))
        if boundary_matches:
            last_idx = boundary_matches[-1].end()
            return sliced[:last_idx].strip() + "\n\n..."

        last_space = sliced.rfind(" ")
        if last_space != -1:
            return sliced[:last_space].strip() + "..."
        return sliced.strip() + "..."

    def _build_fallback_commentaries(
        self,
        article: ArticleDraft,
        wp_url: str,
        related: List[Dict],
    ) -> Tuple[str, str]:
        """Build standard and link-free commentaries using fallback excerpt."""
        hook_text = _excerpt(_strip_html(article.content_html), max_chars=280)
        hashtags = _keywords_to_hashtags(
            list(article.metadata.keywords or []) + [
                "Rishikesh",
                "Adventure",
                "Travel",
                "India",
                Config.BRAND_NAME,
            ]
        )

        related_text = _build_related_linkedin_text(related)
        related_text_free = _build_related_linkedin_text_link_free(related)

        selected_cta = random.choice([
            "📖 Read the full guide here: {url}",
            "👉 Read the complete breakdown on our blog: {url}",
            "🏔️ Read the full story and plan your trip: {url}",
            "Check out the complete updated guide for all details: {url}",
            "Get all the insider tips in the full article: {url}"
        ]).format(url=wp_url)

        selected_link_free_cta = random.choice([
            "👇 Read the full guide in the first comment below!",
            "👉 Link to the complete, detailed breakdown is in the first comment!",
            "🏔️ The link to the full story and planning guide is in the comments below!",
            "Check out the first comment for the link to the full guide!",
            "👇 Details and full travel guide link are pinned in the first comment!"
        ])

        parts = [f"🏔️ {article.metadata.title or article.title}", "", hook_text, ""]
        parts_free = list(parts)

        if related_text:
            parts.extend([related_text, ""])
        if related_text_free:
            parts_free.extend([related_text_free, ""])

        parts.extend([selected_cta, "", hashtags])
        parts_free.extend([selected_link_free_cta, "", hashtags])

        return "\n".join(parts), "\n".join(parts_free)

    def _export_linkedin(
        self,
        article: ArticleDraft,
        wp_url: str,
        related: List[Dict],
        filename_base: str,
    ) -> str:
        """
        Build a LinkedIn post JSON in the Posts API v2 format.
        """
        title = article.metadata.title or article.title
        commentary = ""
        commentary_link_free = ""
        llm_success = False

        try:
            logger.info("Attempting to generate long-form LinkedIn article via LLM...")
            commentary_response = call_llm(
                create_linkedin_prompt(
                    title,
                    article.content_html or f"<p>{article.metadata.description or ''}</p>",
                    list(article.metadata.keywords or [])
                ),
                config=LLMConfig(
                    model_name=Config.MODEL_NAME,
                    max_tokens=4096,
                    temperature=0.7,
                    task_name=f"LinkedIn Post: {title[:20]}"
                )
            )
            if isinstance(commentary_response, tuple):
                commentary_response = commentary_response[0]

            commentary_response = commentary_response.strip().strip('`').strip()
            if commentary_response.startswith("markdown"):
                commentary_response = commentary_response[8:].strip()
            elif commentary_response.startswith("text"):
                commentary_response = commentary_response[4:].strip()

            commentary_response = self._truncate_commentary(
                commentary_response,
                2800 - max(
                    len(_build_related_linkedin_text(related)),
                    len(_build_related_linkedin_text_link_free(related))
                ) - 100
            )

            # 1. Standard Commentary (with Link in Body)
            commentary_parts = [commentary_response]
            if _build_related_linkedin_text(related):
                commentary_parts.append(_build_related_linkedin_text(related))
            commentary_parts.append(random.choice([
                "📖 Read the full guide here: {url}",
                "👉 Read the complete breakdown on our blog: {url}",
                "🏔️ Read the full story and plan your trip: {url}",
                "Check out the complete updated guide for all details: {url}",
                "Get all the insider tips in the full article: {url}"
            ]).format(url=wp_url))
            commentary = "\n\n".join(commentary_parts)

            # 2. Link-Free Commentary (Link in Comments Pointers)
            commentary_parts_free = [commentary_response]
            if _build_related_linkedin_text_link_free(related):
                commentary_parts_free.append(_build_related_linkedin_text_link_free(related))
            commentary_parts_free.append(random.choice([
                "👇 Read the full guide in the first comment below!",
                "👉 Link to the complete, detailed breakdown is in the first comment!",
                "🏔️ The link to the full story and planning guide is in the comments below!",
                "Check out the first comment for the link to the full guide!",
                "👇 Details and full travel guide link are pinned in the first comment!"
            ]))
            commentary_link_free = "\n\n".join(commentary_parts_free)

            llm_success = True
            logger.info("Successfully generated LLM LinkedIn article (%d chars).", len(commentary))
        except (RuntimeError, ValueError, TypeError, KeyError, AttributeError, OSError,
                google.genai.errors.APIError) as exc:
            logger.warning("LLM LinkedIn generation failed or offline: %s. Falling back to excerpt.", exc)

        if not llm_success:
            commentary, commentary_link_free = self._build_fallback_commentaries(
                article, wp_url, related
            )

        self._write_json(
            os.path.join(self.linkedin_dir, f"{filename_base}.json"),
            {
                "author": "urn:li:person:YOUR_MEMBER_ID",
                "commentary": commentary,
                "commentary_link_free": commentary_link_free,
                "first_comment": _get_random_first_comment(wp_url),
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
                        "description": (article.metadata.description or "")[:200],
                    }
                },
                "related_articles": related,
                "_meta": {
                    "platform": "linkedin",
                    "generated_at": datetime.now().isoformat(),
                    "wp_url": wp_url,
                    "wp_slug": filename_base.split("_", 1)[-1],
                    "instructions": (
                        "ANTI-BAN LinkedIn MULTI-ACCOUNT PUBLISHING INSTRUCTIONS:\n"
                        "Option A (Safe - Standard Outbound Link):\n"
                        "  - Copy the 'commentary' field and paste it directly into LinkedIn.\n"
                        "Option B (Ultra-Safe - Link-in-Comments Strategy for Multi-Accounts):\n"
                        "  1. Copy the 'commentary_link_free' field and post it directly to LinkedIn "
                        "(this post has zero outbound links, completely bypassing domain spam filters).\n"
                        "  2. Immediately after publishing the post, copy the 'first_comment' field and "
                        "post it as the very first comment on that post.\n"
                        "3. Replace 'YOUR_MEMBER_ID' with your LinkedIn member or organization ID if posting via API."
                    )
                }
            }
        )
        return os.path.join(self.linkedin_dir, f"{filename_base}.json")

    # ------------------------------------------------------------------
    # Medium
    # ------------------------------------------------------------------

    def _export_medium(
        self,
        article: ArticleDraft,
        wp_url: str,
        related: List[Dict],
        filename_base: str,
    ) -> str:
        """
        Build a Medium post JSON in the Publishing API v1 format.

        Strategy: FULL CONTENT + CANONICAL URL.
        Medium supports canonical URLs — the system sets this to the live WordPress
        URL, so Google knows the main site is the original. Safe for SEO.
        """
        wp_slug = article.metadata.url_slug or ""

        self._write_json(
            os.path.join(self.medium_dir, f"{filename_base}.json"),
            {
                "title": article.metadata.title or article.title,
                "contentFormat": "html",
                "content": (
                    (article.content_html or f"<h1>{article.metadata.title or article.title}</h1>")
                    + "\n"
                    + (article.faq_section or "")
                    + "\n"
                    + _build_related_html_block(related)
                    + "\n"
                    + "<hr/><p><em>This article was originally published at "
                    + f"<a href='{wp_url}'>{Config.BRAND_NAME}</a>.</em></p>"
                ),
                "tags": _keywords_to_medium_tags(list(article.metadata.keywords or [])),
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
        )
        return os.path.join(self.medium_dir, f"{filename_base}.json")

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
        except (OSError, TypeError, ValueError) as exc:
            logger.error("Failed to write social export to %s: %s", path, exc)
