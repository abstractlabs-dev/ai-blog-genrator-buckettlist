import base64
import logging
import mimetypes
import os
import re
from typing import Dict, Any

import markdown
import requests
from bs4 import BeautifulSoup

from ..config import Config
from ..models import ArticleDraft
from ..stats_manager import StatsManager

logger = logging.getLogger(__name__)

class WordPressPublisher:

    def __init__(self):
        # Strip both whitespace and a trailing slash — prevents double-slash endpoints
        # when the env var is set as 'https://example.com/' instead of 'https://example.com'
        self.base_url = Config.WORDPRESS_BASE_URL.strip().rstrip('/') if Config.WORDPRESS_BASE_URL else None
        self.username = Config.WORDPRESS_USERNAME.strip() if Config.WORDPRESS_USERNAME else None
        self.app_password = Config.WORDPRESS_TOKEN.replace(" ", "") if Config.WORDPRESS_TOKEN else None

        if not self.base_url:
            logger.warning("WordPress Config Missing: WORDPRESS_BASE_URL")
        if not self.username:
            logger.warning("WordPress Config Missing: WORDPRESS_USERNAME")
        if not self.app_password:
            logger.warning("WordPress Config Missing: WORDPRESS_TOKEN")

        # Setup Session with Retries and Headers
        self.session = requests.Session()
        retries = requests.adapters.HTTPAdapter(max_retries=3)
        self.session.mount('https://', retries)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; BlogGenerator/2.0; +http://company_name.com)",
            "Accept": "application/json"
        })

    def is_configured(self) -> bool:
        return bool(self.base_url and self.username and self.app_password)

    def upload_media(self, file_path: str, alt_text: str = "", description: str = "") -> int:
        """
        Uploads an image to WordPress Media Library and sets its metadata.
        Returns the attachment ID on success, or 0 on failure.
        """
        if not self.is_configured():
            logger.warning("WordPress not configured, skipping media upload.")
            return 0

        if not file_path:
            return 0

        if not os.path.exists(file_path):
            logger.warning("Image file not found at %s, skipping upload.", file_path)
            return 0

        endpoint = f"{self.base_url}/wp-json/wp/v2/media"
        auth_string = f"{self.username}:{self.app_password}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()

        # Determine Mime Type
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "image/png" if file_path.endswith('.png') else "application/octet-stream"

        # Specific headers for media upload
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": mime_type,
            "Content-Disposition": f'attachment; filename="{os.path.basename(file_path)}"'
        }

        try:
            with open(file_path, 'rb') as img_file:
                media_data = img_file.read()

            logger.info("Uploading %s (%s bytes) to WordPress...", os.path.basename(file_path), len(media_data))

            response = self.session.post(
                endpoint,
                data=media_data,
                headers=headers,
                timeout=120  # increased to 120s for large uploads
            )

            if response.status_code not in (200, 201):
                logger.error("WordPress Media Upload failed (%s): %s", response.status_code, response.text[:500])
                return 0

            result = response.json()
            media_id = result.get('id', 0)
            logger.info("Successfully uploaded image %s (ID: %s)", os.path.basename(file_path), media_id)

            # Step 2: Update Media Metadata (Alt Text, Title, Description)
            if media_id > 0 and (alt_text or description):
                try:
                    update_endpoint = f"{endpoint}/{media_id}"
                    update_payload = {}
                    if alt_text:
                        update_payload["alt_text"] = alt_text
                    if description:
                        update_payload["description"] = description
                        update_payload["caption"] = description

                    # Update Title to match alt text or description if possible
                    update_payload["title"] = alt_text or description or os.path.basename(file_path)

                    update_headers = {
                        "Authorization": f"Basic {encoded_auth}",
                        "Content-Type": "application/json"
                    }

                    logger.info("Updating metadata for image ID %s (Alt: %s)", media_id, alt_text[:50])
                    update_resp = self.session.post(update_endpoint, json=update_payload, headers=update_headers, timeout=30)

                    if update_resp.status_code not in (200, 201):
                        logger.warning("Failed to update image metadata (%s): %s", update_resp.status_code, update_resp.text[:200])
                except Exception as meta_err:
                    logger.warning("Error updating image metadata for ID %s: %s", media_id, meta_err)

            return media_id

        except Exception as err:
            logger.error("Exception during media upload %s: %s", file_path, err)
            return 0

    def _get_category_id(self, category_name: str, parent_id: int = 0) -> int:
        """
        Gets the ID of a category by name. Does NOT create new categories.
        If parent_id is provided, it searches specifically for children of that parent.
        Returns the category ID on success, or 0 if not found.
        """
        if not self.is_configured() or not category_name:
            return 0

        # Encode credentials for basic auth
        auth_string = f"{self.username}:{self.app_password}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        headers = {"Authorization": f"Basic {encoded_auth}"}

        try:
            # Search for existing category
            search_url = f"{self.base_url}/wp-json/wp/v2/categories"
            params = {
                "search": category_name,
                "per_page": 100
            }
            if parent_id > 0:
                params["parent"] = parent_id

            resp = self.session.get(search_url, params=params, headers=headers, timeout=30)

            if resp.status_code == 200:
                categories = resp.json()
                for cat in categories:
                    if cat['name'].lower() == category_name.lower():
                        return cat['id']

            # If not found with parent filter, and we had one, log it
            if parent_id > 0:
                logger.warning("Category '%s' not found under parent %s", category_name, parent_id)
            else:
                logger.warning("Category '%s' not found in WordPress", category_name)

        except Exception as err:
            logger.error("Exception during category lookup for '%s': %s", category_name, err)

        return 0

    def publish_article(self, article: ArticleDraft, image_path: str = None) -> Dict[str, Any]:

        if not self.is_configured():
            raise ValueError("WordPress not configured properly.")

        media_id = 0
        if image_path:
            # Send image description as Alt Text and Description to Media Library
            media_id = self.upload_media(
                image_path,
                alt_text=getattr(article, "image_description", ""),
                description=getattr(article, "image_description", "")
            )

        pub_config = {
            "endpoint": f"{self.base_url}/wp-json/wp/v2/posts",
            "auth": base64.b64encode(f"{self.username}:{self.app_password}".encode()).decode(),
            "headers": {}
        }
        pub_config["headers"] = {
            "Authorization": f"Basic {pub_config['auth']}",
            "Content-Type": "application/json"
        }

        # Step 1: Fix malformed HTML tags (spacing issues, incomplete brackets)
        def fix_malformed_tags(html: str) -> str:
            """Pre-process HTML to fix common AI-generated tag errors."""
            if not html:
                return ""

            # Fix multiple spaces in closing tags: </  p  > -> </p>
            html = re.sub(r'<\s*/\s*([a-z0-9]+)\s*>', r'</\1>', html, flags=re.IGNORECASE)

            # Fix multiple spaces in opening tags: <h3  > -> <h3>
            html = re.sub(r'<\s*([a-z0-9]+)\s+>', r'<\1>', html, flags=re.IGNORECASE)

            # Remove space after opening bracket: < tag> -> <tag>
            html = re.sub(r'<\s+([a-z0-9]+)', r'<\1', html, flags=re.IGNORECASE)

            # Normalize spaces in tags: < h3 > -> <h3>
            html = re.sub(r'<\s*([a-z0-9]+)\s*>', r'<\1>', html, flags=re.IGNORECASE)
            html = re.sub(r'<\s*/\s*([a-z0-9]+)\s*>', r'</\1>', html, flags=re.IGNORECASE)

            # Fix period instead of bracket: <h3.Text -> <h3>Text
            html = re.sub(r'<(h[1-3]|p|b|strong|li|ul|ol|blockquote)\.', r'<\1>', html, flags=re.IGNORECASE)

            # Strip all attributes from headings (H1-H3) to remove AI garbage
            html = re.sub(r'<(h[1-3])\s+[^>]*>', r'<\1>', html, flags=re.IGNORECASE)

            # Close heading tags missing a bracket at the end of a line
            html = re.sub(r'<(h[1-3])\s+[^>\n]+$', r'<\1>', html, flags=re.IGNORECASE)

            # Fix severely broken tags like <h3<monitoring... -> <h3>
            html = re.sub(r'<(h[1-3]|p|b|strong|li|ul|ol|blockquote)<[^>]*?>', r'<\1>', html, flags=re.IGNORECASE)

            # Fix tags starting with double brackets: <h3<name -> <h3>name
            html = re.sub(r'<(h[1-3]|p|b|strong|li|ul|ol|blockquote)<([A-Za-z])', r'<\1>\2', html, flags=re.IGNORECASE)

            # Resolve internal opening brackets that break parsing: <h3<... -> <h3>
            html = re.sub(r'<(h[1-3]|p|b|strong|li|ul|ol|blockquote)<', r'<\1>', html, flags=re.IGNORECASE)

            return html

        # Step 2: Close unclosed tags using BeautifulSoup
        def close_unclosed_tags(html: str) -> str:
            """Use BeautifulSoup to automatically close any unclosed tags."""
            if not html:
                return ""

            try:
                # html5lib parser is very forgiving and follows browser behavior
                soup = BeautifulSoup(html, 'html5lib')

                # Extract body content (html5lib wraps everything in html/body)
                if soup.body:
                    # Get the body's inner HTML
                    body_content = ''.join(str(child) for child in soup.body.children)
                    return body_content

                # Fallback if no body tag
                return str(soup)
            except Exception as err:
                logger.warning("BeautifulSoup cleanup failed: %s. Returning original HTML.", err)
                return html

        # Step 3: Convert Markdown to HTML
        def convert_markdown_to_html(text: str) -> str:
            if not text:
                return ""
            # Convert Markdown to HTML
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

        # Combined HTML cleanup and conversion pipeline
        # Process main content: Fix malformed tags → Close unclosed tags → Convert any Markdown
        main_content = article.content_html or ""
        main_content = fix_malformed_tags(main_content)
        main_content = close_unclosed_tags(main_content)
        main_content = convert_markdown_to_html(main_content)

        # Process FAQ section: Fix malformed tags → Close unclosed tags → Convert any Markdown
        faq_content = article.faq_section or ""
        faq_content = fix_malformed_tags(faq_content)
        faq_content = close_unclosed_tags(faq_content)
        faq_content = convert_markdown_to_html(faq_content)

        # Check if FAQ is already embedded in main content to prevent duplication
        faq_markers = [
            '<div class="faq-section">',
            '<h2>Frequently Asked Questions',
            '<h2>Frequently Asked Question',
            '<h2>FAQ',
            '<h3>FAQ',
            '<strong>Frequently Asked Questions'
        ]
        faq_found = any(marker.lower() in main_content.lower() for marker in faq_markers)

        if faq_found:
            logger.info("FAQ section appears to be already embedded in main content, skipping duplicate FAQ append")
            faq_content = ""  # Don't append FAQ again

        # Combine content
        content_ctx = {
            "main": main_content,
            "faq": faq_content,
            "full": ""
        }
        full_content = f"{content_ctx['main']}\n{content_ctx['faq']}" if content_ctx["faq"] else content_ctx["main"]
        content_ctx["full"] = full_content

        # Strip leading <h1>...</h1> so WordPress theme title is not duplicated
        content_ctx["full"] = re.sub(
            r"^\s*<h1[^>]*>.*?</h1>\s*", "", content_ctx["full"],
            flags=re.DOTALL | re.IGNORECASE
        )

        # ── Bucketlistt.com Dynamic Linking ──────────────────────────────────
        # Inject contextual backlinks (Tier 1) and a CTA widget (Tier 2) into
        # the assembled HTML before sending it to the WP REST API.
        try:
            from ..services.linking_manager import LinkingManager
            article.content_html = content_ctx["full"]
            enriched_html = LinkingManager.inject_bucketlistt_links(article)
            content_ctx["full"] = enriched_html
            logger.info("[WordPress] Bucketlistt linking applied to '%s'.", article.metadata.title or article.title)
        except Exception as link_err:
            logger.warning("[WordPress] Bucketlistt linking failed (non-fatal): %s", link_err)

        # Prepare publish context
        # Use meta description if available, otherwise excerpt (already stripped/filtered in orchestrator)
        excerpt = article.metadata.description if article.metadata.description else ""

        ctx = {
            "title": article.metadata.title or article.title,
            "content": content_ctx["full"],
            "excerpt": excerpt,
            "slug": article.metadata.url_slug,
            "status": "publish",
            "meta": {
                "_yoast_wpseo_metadesc": excerpt,
                "_yoast_wpseo_title": article.metadata.title,
                "_yoast_wpseo_focuskw": article.metadata.focus_keyword,
                "rank_math_description": excerpt,
                "rank_math_title": article.metadata.title,
                "rank_math_focus_keyword": article.metadata.focus_keyword
            }
        }

        generated_at = getattr(article, "generated_at", None)
        if generated_at:
            ctx["date"] = generated_at.strftime("%Y-%m-%dT%H:%M:%S")
            ctx["date_gmt"] = ctx["date"]

        if media_id > 0:
            ctx["featured_media"] = media_id

        # Handle Categories - strictly 1 Child and 1 Parent
        cat_ctx = {
            "category": str(getattr(article, "category", "")).strip(),
            "parent_category": str(getattr(article, "parent_category", "")).strip(),
            "category_ids": []
        }

        mapping = Config.CATEGORIES_MAPPING
        child_id = 0
        parent_id = 0

        # 1. Resolve Child Category ID (Robust & Case-Insensitive)
        if cat_ctx["category"]:
            # Determine mapping section based on parent
            section_key = "product_categories" if cat_ctx["parent_category"] == "Product Categories" else "industry_categories"
            search_section = mapping.get(section_key, {})

            # Normalize the input category name for matching (strip and lowercase)
            norm_name = cat_ctx["category"].lower()
            # Also try matching without common suffixes like " product" or " products"
            alt_name = re.sub(r'\s+products?$', '', norm_name)

            for name, cid in search_section.items():
                m_name = name.strip().lower()
                m_alt_name = re.sub(r'\s+products?$', '', m_name)

                if m_name == norm_name or m_alt_name == alt_name:
                    child_id = cid
                    break

            if child_id:
                cat_ctx["category_ids"].append(child_id)
                logger.info("Category Mapping: Resolved Child '%s' -> ID %s (Primary)", cat_ctx["category"], child_id)
            else:
                logger.warning("Category Mapping: Child '%s' NOT found in '%s' mapping (checked exact and suffix-neutral).",
                               cat_ctx["category"], section_key)

        # 2. Resolve Parent Category ID (Case-Insensitive)
        if cat_ctx["parent_category"]:
            parents_mapping = mapping.get("parents", {})
            norm_parent = cat_ctx["parent_category"].lower()

            for p_name, p_id in parents_mapping.items():
                if p_name.strip().lower() == norm_parent:
                    parent_id = p_id
                    break

            if parent_id:
                if parent_id not in cat_ctx["category_ids"]:
                    cat_ctx["category_ids"].append(parent_id)
                logger.info("Category Mapping: Resolved Parent '%s' -> ID %s", cat_ctx["parent_category"], parent_id)
            else:
                logger.warning("Category Mapping: Parent '%s' NOT found in mapping.", cat_ctx["parent_category"])

        # Final Category Assignment
        if cat_ctx["category_ids"]:
            ctx["categories"] = cat_ctx["category_ids"]
            logger.info("Category Mapping: Final WP Categories: %s (Child=%s, Parent=%s)",
                        cat_ctx["category_ids"], child_id, parent_id)
        else:
            logger.warning("Category Mapping: No categories resolved for article.")

        if "date" in ctx:
            logger.info("WordPress Post Payload Date: %s", ctx["date"])

        try:
            logger.info("Sending publish request to %s...", pub_config["endpoint"])
            response = self.session.post(pub_config["endpoint"], json=ctx, headers=pub_config["headers"], timeout=60)
            if response.status_code not in (200, 201):
                logger.error("WordPress Publishing failed (%s): %s", response.status_code, response.text[:500])
            response.raise_for_status()
        except requests.RequestException as err:
            logger.error("Failed WordPress publish: %s", err)
            raise

        try:
            result = response.json()
        except Exception:
            result = {}

        try:
            StatsManager.increment_published("wordpress")
        except Exception as err:
            logger.warning("Failed to update stats for WordPress publish: %s", err)

        return result
