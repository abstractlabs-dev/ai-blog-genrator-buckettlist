"""WordPress publish diagnostic test script."""
import sys
import base64
import json
import requests

sys.path.insert(0, '/app')

from src.config import Config
from src.models import ArticleDraft, Metadata
from src.publishers.wordpress import WordPressPublisher
from datetime import datetime

# Build a minimal ArticleDraft exactly like the real pipeline
meta = Metadata(
    title="Test Diagnostic Article WP",
    description="This is a 120-character test meta description for SEO testing purposes only. Please ignore this test post.",
    focus_keyword="test rishikesh",
    url_slug="test-diagnostic-wp-diag-1234",
    canonical_url="https://rishikeshplaces.com/test-diagnostic-wp-diag-1234",
    keywords=["test", "diagnostic", "rishikesh"],
    json_ld_schema={}
)

article = ArticleDraft(
    title="Test Diagnostic Article WP",
    content_html="<p>Test content for diagnostic purposes. Rishikesh adventures await you.</p>",
    word_count=1200,
    metadata=meta,
    faq_section="<h3>Test FAQ Question Here?</h3><p>Test answer for FAQ here.</p>",
    category="Travel",
    parent_category="Industry Categories",
    generated_at=datetime(2025, 6, 15, 10, 30, 0)
)

print("=== Testing Full WordPress Publish Flow ===")
print(f"Article title: {article.title}")
print(f"Slug: {article.metadata.url_slug}")
print(f"Category: {article.category} | Parent: {article.parent_category}")

publisher = WordPressPublisher()
print(f"Publisher configured: {publisher.is_configured()}")
print(f"Base URL: {repr(publisher.base_url)}")
print(f"Username: {repr(publisher.username)}")
print()

try:
    result = publisher.publish_article(article, image_path=None)
    print(f"RAW RESULT: {json.dumps(result, indent=2)[:800]}")
    print()

    if result.get("id"):
        print(f"SUCCESS! Post ID: {result['id']}")
        print(f"Link: {result.get('link')}")
        print(f"Status: {result.get('status')}")
        print(f"Categories: {result.get('categories')}")

        # Cleanup: delete test post
        auth_str = base64.b64encode(
            f"{publisher.username}:{publisher.app_password}".encode()
        ).decode()
        clean_base = publisher.base_url.rstrip("/")
        del_url = f"{clean_base}/wp-json/wp/v2/posts/{result['id']}?force=true"
        del_resp = requests.delete(
            del_url,
            headers={"Authorization": f"Basic {auth_str}"},
            timeout=30
        )
        print(f"Cleanup delete status: {del_resp.status_code}")
    else:
        print("FAILED: No ID returned in result")
        print(f"Full response: {result}")

except Exception as exc:
    print(f"EXCEPTION: {type(exc).__name__}: {exc}")
    import traceback
    traceback.print_exc()
