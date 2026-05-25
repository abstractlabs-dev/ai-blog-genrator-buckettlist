"""
linking_manager.py
------------------
Injects contextual Bucketlistt.com backlinks and styled CTA widgets into generated
article HTML *right before* WordPress publishing.

Two-tier strategy (as per sitemap_linking_plan.md):
  Tier 1 — Natural Anchor Matching: scan article text for known activity keywords
            and hyperlink the FIRST occurrence to the corresponding booking page.
  Tier 2 — CTA Widget Injection:    detect the primary activity topic of the article
            and append a branded, styled call-to-action widget after the 2nd H2 heading
            (or at the end of the article if no H2s exist).

The keyword → URL mapping is loaded from:
    data/config/sitemap_mapping.json

This service is stateless and all public methods are @staticmethods so it can be
called directly without instantiation:

    from src.services.linking_manager import LinkingManager
    article.content_html = LinkingManager.inject_bucketlistt_links(article)
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config loader (loaded once at module import)
# ---------------------------------------------------------------------------

_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__),          # src/services/
    "..", "..",                          # project root
    "data", "config", "sitemap_mapping.json"
)

def _load_sitemap_config() -> Dict:
    """Load and return the sitemap_mapping.json config, with a safe fallback."""
    try:
        abs_path = os.path.normpath(os.path.abspath(_CONFIG_PATH))
        with open(abs_path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
        logger.info("[LinkingManager] Loaded sitemap mapping from %s", abs_path)
        return config
    except Exception as err:
        logger.error("[LinkingManager] Failed to load sitemap_mapping.json: %s", err)
        return {}

_SITEMAP_CONFIG: Dict = _load_sitemap_config()


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _build_anchor(text: str, url: str, title: str = "") -> str:
    """Return a clean <a> tag for inline contextual linking."""
    title_attr = f' title="{title}"' if title else ""
    return (
        f'<a href="{url}" target="_blank" rel="noopener"'
        f'{title_attr}>{text}</a>'
    )


def _build_cta_widget(
    cta_title: str,
    cta_text: str,
    cta_url: str,
    button_text: str,
    button_color: str = "#ff5a5f",
) -> str:
    """
    Build an inline-styled, attractive CTA widget block (no external CSS needed).
    Uses inline styles so it works even in WordPress themes that strip <style> tags.
    """
    return f"""
<div class="bucketlistt-cta-box" style="border:2px solid {button_color};padding:22px 24px;border-radius:10px;margin:32px 0;background:linear-gradient(135deg,#fff8f8 0%,#fff 100%);box-shadow:0 2px 12px rgba(255,90,95,0.08);font-family:inherit;">
  <h4 style="margin:0 0 10px 0;color:{button_color};font-size:1.05em;font-weight:700;letter-spacing:-0.01em;">{cta_title}</h4>
  <p style="margin:0 0 16px 0;color:#444;font-size:0.97em;line-height:1.6;">{cta_text}</p>
  <a href="{cta_url}" target="_blank" rel="noopener sponsored"
     style="display:inline-block;background:{button_color};color:#fff;padding:10px 22px;border-radius:6px;text-decoration:none;font-weight:700;font-size:0.95em;letter-spacing:0.01em;transition:opacity 0.2s;"
     onmouseover="this.style.opacity='0.88'" onmouseout="this.style.opacity='1'">
    {button_text} →
  </a>
</div>
""".strip()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

class LinkingManager:
    """
    Static service for injecting Bucketlistt.com links & CTA widgets into article HTML.

    Usage:
        from src.services.linking_manager import LinkingManager
        article.content_html = LinkingManager.inject_bucketlistt_links(article)
    """

    # Maximum inline keyword anchors to insert (prevents over-linking)
    MAX_ANCHORS = 5

    @staticmethod
    def inject_bucketlistt_links(article) -> str:
        """
        Main entry point.  Takes an ArticleDraft, returns enriched HTML string.

        Steps:
          1. Detect the dominant activity/topic from article title + content.
          2. Run Tier-1 keyword → anchor replacement.
          3. Run Tier-2 CTA widget injection.
        """
        html = article.content_html or ""
        title = getattr(article, "title", "") or ""
        metadata_title = getattr(article.metadata, "title", "") if hasattr(article, "metadata") else ""
        full_title = metadata_title or title

        if not html:
            logger.warning("[LinkingManager] Article '%s' has empty content_html — skipping.", full_title)
            return html

        if "bucketlistt-cta-box" in html:
            logger.info("[LinkingManager] Bucketlistt linking already applied to '%s' — skipping.", full_title)
            return html

        activities_cfg: Dict = _SITEMAP_CONFIG.get("activities", {})
        hub_links_cfg: Dict  = _SITEMAP_CONFIG.get("hub_links", {})
        general_cta_cfg: Dict = _SITEMAP_CONFIG.get("general_cta", {})

        if not activities_cfg:
            logger.warning("[LinkingManager] sitemap_mapping.json is empty or not loaded — skipping linking.")
            return html

        # ── Tier 1: contextual inline anchors ──────────────────────────────
        html, inserted_anchors, matched_activities = LinkingManager._inject_inline_anchors(
            html, activities_cfg, hub_links_cfg
        )

        # ── Tier 2: CTA widget ─────────────────────────────────────────────
        html = LinkingManager._inject_cta_widget(
            html,
            activities_cfg,
            general_cta_cfg,
            matched_activities,
            full_title,
        )

        logger.info(
            "[LinkingManager] Article '%s' — anchors inserted: %d, matched activities: %s",
            full_title[:60],
            inserted_anchors,
            list(matched_activities.keys()),
        )
        return html

    # ------------------------------------------------------------------
    # Tier 1 — inline keyword → anchor replacement
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_inline_anchors(
        html: str,
        activities_cfg: Dict,
        hub_links_cfg: Dict,
    ) -> Tuple[str, int, Dict]:
        """
        Scans the article HTML and converts the FIRST occurrence of each
        activity keyword into an <a> hyperlink.

        Returns:
            (enriched_html, total_anchors_inserted, matched_activities_dict)
            matched_activities maps activity_key → activity_config for activities
            that were matched.
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        total_anchors = 0
        matched_activities: Dict = {}

        # Sort all activities by priority (highest first) so dominant topic wins
        sorted_activities = sorted(
            activities_cfg.items(),
            key=lambda kv: kv[1].get("priority", 0),
            reverse=True,
        )

        for activity_key, cfg in sorted_activities:
            if total_anchors >= LinkingManager.MAX_ANCHORS:
                break

            keywords: List[str] = cfg.get("keywords", [])
            booking_url: str     = cfg.get("url", "")
            if not keywords or not booking_url:
                continue

            # Sort keywords longest-first to prefer specific matches
            for kw in sorted(keywords, key=len, reverse=True):
                if total_anchors >= LinkingManager.MAX_ANCHORS:
                    break

                # Case-insensitive, whole-phrase, outside existing <a> tags
                n = LinkingManager._replace_keyword_outside_anchors_in_soup(
                    soup, kw, booking_url, title=cfg.get("cta_title", "")
                )
                if n > 0:
                    total_anchors += n
                    if activity_key not in matched_activities:
                        matched_activities[activity_key] = cfg
                    # Only link ONE keyword per activity to avoid spam
                    break

        # Hub links (lower priority — only if budget allows)
        for hub_key, cfg in hub_links_cfg.items():
            if total_anchors >= LinkingManager.MAX_ANCHORS:
                break
            keywords = cfg.get("keywords", [])
            url = cfg.get("url", "")
            anchor_text_override = cfg.get("anchor_text", "")
            if not keywords or not url:
                continue
            for kw in sorted(keywords, key=len, reverse=True):
                if total_anchors >= LinkingManager.MAX_ANCHORS:
                    break
                n = LinkingManager._replace_keyword_outside_anchors_in_soup(
                    soup, kw, url, override_text=anchor_text_override
                )
                if n > 0:
                    total_anchors += n
                    break

        return str(soup), total_anchors, matched_activities

    @staticmethod
    def _replace_keyword_outside_anchors_in_soup(
        soup,
        keyword: str,
        url: str,
        title: str = "",
        override_text: str = "",
    ) -> int:
        """
        Replaces the FIRST occurrence of *keyword* (case-insensitive) in the BeautifulSoup
        soup object that is NOT already inside an <a> tag with a hyperlink.

        Returns the number of replacements (0 or 1).
        """
        from bs4 import NavigableString

        replaced_count = 0

        # Find all text nodes in the document
        text_nodes = soup.find_all(string=True)

        for node in text_nodes:
            # Skip if the parent is an <a> tag or inside one
            if node.find_parent("a"):
                continue

            # Skip comments or other non-text components
            if type(node) is not NavigableString:
                continue

            # Case-insensitive whole-phrase match using word boundaries
            pattern = re.compile(r'\b(' + re.escape(keyword) + r')\b', re.IGNORECASE)
            match = pattern.search(node)
            if match:
                # We found the first occurrence!
                # Split the text node around the match
                start_idx = match.start()
                end_idx = match.end()
                matched_text = match.group(0)

                before_text = node[:start_idx]
                after_text = node[end_idx:]

                display_text = override_text if override_text else matched_text

                # Create the new <a> tag
                link_tag = soup.new_tag("a", href=url, target="_blank", rel="noopener")
                if title:
                    link_tag["title"] = title
                link_tag.string = display_text

                # Replace original node in-place with the link tag
                node.replace_with(link_tag)

                # Insert before_text before the link tag if it exists
                if before_text:
                    link_tag.insert_before(NavigableString(before_text))

                # Insert after_text after the link tag if it exists
                if after_text:
                    link_tag.insert_after(NavigableString(after_text))

                replaced_count = 1
                break  # Stop after first replacement

        return replaced_count

    # ------------------------------------------------------------------
    # Tier 2 — CTA widget injection
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_cta_widget(
        html: str,
        activities_cfg: Dict,
        general_cta_cfg: Dict,
        matched_activities: Dict,
        article_title: str,
    ) -> str:
        """
        Injects a single CTA widget into the article HTML.

        Placement preference:
          1. After the 2nd <h2> heading (catches reader mid-article).
          2. Fallback: append at the very end of the HTML.

        Widget selection:
          - If exactly one activity matched in Tier 1 → use its specific CTA.
          - If multiple activities matched → use the highest-priority one.
          - If no activities matched → use the general Rishikesh CTA.
          - Special case: detect activity from article TITLE as a last resort.
        """
        # --- Pick the best CTA config ---
        best_activity_cfg: Optional[Dict] = None

        if matched_activities:
            # Pick highest priority among matched
            best_key = max(matched_activities, key=lambda k: matched_activities[k].get("priority", 0))
            best_activity_cfg = matched_activities[best_key]
        else:
            # Last-resort: scan article title for activity keywords
            title_lower = article_title.lower()
            sorted_activities = sorted(
                activities_cfg.items(),
                key=lambda kv: kv[1].get("priority", 0),
                reverse=True,
            )
            for _, cfg in sorted_activities:
                for kw in cfg.get("keywords", []):
                    if kw.lower() in title_lower:
                        best_activity_cfg = cfg
                        break
                if best_activity_cfg:
                    break

        if best_activity_cfg:
            widget_html = _build_cta_widget(
                cta_title=best_activity_cfg.get("cta_title", "🏔️ Book Your Adventure"),
                cta_text=best_activity_cfg.get("cta_text", "Discover top-rated activities in Rishikesh on Bucketlistt."),
                cta_url=best_activity_cfg.get("url", general_cta_cfg.get("url", "https://www.bucketlistt.com/rishikesh")),
                button_text=best_activity_cfg.get("cta_button_text", "Book Now"),
                button_color=general_cta_cfg.get("button_color", "#ff5a5f"),
            )
        else:
            # Fallback to generic Rishikesh CTA
            widget_html = _build_cta_widget(
                cta_title=general_cta_cfg.get("title", "🏔️ Plan Your Rishikesh Adventure"),
                cta_text=general_cta_cfg.get("text", "Discover all adventures in Rishikesh on Bucketlistt."),
                cta_url=general_cta_cfg.get("url", "https://www.bucketlistt.com/rishikesh"),
                button_text=general_cta_cfg.get("button_text", "Explore All Rishikesh Activities"),
                button_color=general_cta_cfg.get("button_color", "#ff5a5f"),
            )

        # --- Find insertion point (after 2nd <h2>) ---
        h2_pattern = re.compile(r'</h2>', re.IGNORECASE)
        matches = list(h2_pattern.finditer(html))

        if len(matches) >= 2:
            # Insert after the 2nd H2 closing tag
            insert_pos = matches[1].end()
            html = html[:insert_pos] + "\n" + widget_html + "\n" + html[insert_pos:]
            logger.debug("[LinkingManager] CTA widget injected after 2nd H2.")
        else:
            # Fallback: append at the end
            html = html + "\n" + widget_html
            logger.debug("[LinkingManager] CTA widget appended at end (no 2nd H2 found).")

        return html
