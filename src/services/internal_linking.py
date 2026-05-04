import re
import random
import logging
from typing import Dict, List
from src.config import Config
from src.models import ArticleDraft, InternalLink
from utils.utils import CSVManager, VectorStoreManager

logger = logging.getLogger(__name__)

class InternalLinkingService:
    def __init__(self, csv_manager: CSVManager, vector_store: VectorStoreManager):
        self.csv_manager = csv_manager
        self.vector_store = vector_store

    def _extract_text_from_html(self, html_content: str) -> str:
        """Extracts plain text from HTML content."""
        return re.sub(r'<[^>]+>', ' ', html_content)

    def _get_csv_fallback_links(self, exclude_slug: str) -> List[InternalLink]:
        """Gets 2 random fallback links from CSV and 1 direct site link.

        Always ensures exactly 3 links are returned.
        """
        all_articles = self.csv_manager.get_all_articles()
        links = []

        # 1. Get up to 2 article links from CSV
        if all_articles:
            others = [
                a for a in all_articles
                if a.get('url') and exclude_slug not in a['url']
            ]
            if others:
                sample_count = min(len(others), 2)
                sample = random.sample(others, sample_count)
                for sample_article in sample:
                    links.append(InternalLink(
                        anchor_text=self._generate_anchor_text(sample_article),
                        target_url=sample_article['url'],
                        relevance_score=0.4
                    ))

        # 2. Add 1 direct site link
        links.append(InternalLink(
            anchor_text=Config.DEFAULT_LINK_TEXT,
            target_url=Config.DEFAULT_LINK_URL,
            relevance_score=1.0
        ))

        # 3. Fill remaining slots to reach exactly 3 links if CSV was sparse
        while len(links) < 3:
            links.append(InternalLink(
                anchor_text=Config.DEFAULT_LINK_TEXT or "Explore more resources",
                target_url=Config.DEFAULT_LINK_URL,
                relevance_score=0.5
            ))

        logger.info("Internal linking (Fallback): Created %d links (2 Articles + 1 Site)", len(links))
        return links[:3]

    def add_internal_links(self, article: ArticleDraft) -> ArticleDraft:
        """Main orchestrator for adding exactly 2 article links and 1 site link."""
        text_content = self._extract_text_from_html(article.content_html)
        similar_articles = self.vector_store.find_similar_articles(text_content, k=5)
        current_article_slug = article.metadata.url_slug
        internal_links = []

        # Step 1: Try to get 2 article links from Vector Store
        if similar_articles:
            all_articles = self.csv_manager.get_all_articles()
            if all_articles:
                article_lookup = {art['article_id']: art for art in all_articles}
                for similar in similar_articles:
                    if len(internal_links) >= 2:
                        break

                    article_id = similar.get('article_id')
                    if article_id and article_id in article_lookup:
                        target_article = article_lookup[article_id]
                        if target_article.get('url') and current_article_slug in target_article['url']:
                            continue

                        anchor_text = self._generate_anchor_text(target_article)
                        internal_links.append(InternalLink(
                            anchor_text=anchor_text,
                            target_url=target_article['url'],
                            relevance_score=similar['relevance_score']
                        ))

        # Step 2: Fallback to CSV if vector search gave < 2 links
        if len(internal_links) < 2:
            all_articles = self.csv_manager.get_all_articles()
            if all_articles:
                others = [
                    a for a in all_articles
                    if a.get('url') and current_article_slug not in a['url']
                    and a.get('url') not in [l.target_url for l in internal_links]
                ]
                needed = 2 - len(internal_links)
                if others:
                    sample = random.sample(others, min(len(others), needed))
                    for sample_article in sample:
                        internal_links.append(InternalLink(
                            anchor_text=self._generate_anchor_text(sample_article),
                            target_url=sample_article['url'],
                            relevance_score=0.4
                        ))

        # Step 3: Always add 1 direct site link
        internal_links.append(InternalLink(
            anchor_text=Config.DEFAULT_LINK_TEXT,
            target_url=Config.DEFAULT_LINK_URL,
            relevance_score=1.0
        ))

        # Step 4: Final validation and insertion
        # Ensure we have at least 1 site link and fill gaps if somehow still below 3
        while len(internal_links) < 3:
             internal_links.append(InternalLink(
                anchor_text=Config.DEFAULT_LINK_TEXT or "Explore more resources",
                target_url=Config.DEFAULT_LINK_URL,
                relevance_score=0.5
            ))

        article.content_html = self._insert_links_into_content(article.content_html, internal_links[:3])
        article.internal_links = internal_links[:3]
        logger.info("Internal linking completed with %d links (2 Articles + 1 Site).", len(article.internal_links))
        return article

    def _generate_anchor_text(self, target_article: Dict) -> str:
        title = target_article.get('title', 'our latest article')
        return "Read more about: " + (title[:40] + "..." if len(title) > 40 else title)

    def _insert_links_into_content(self, content: str, links: list[InternalLink]) -> str:
        """Inserts internal links into the content HTML.

        Strategy:
        1. Find paragraphs in the content
        2. Insert links within paragraphs at appropriate positions
        3. Ensure links are properly wrapped and contextual
        """
        if not links:
            logger.debug("No internal links to insert.")
            return content

        # Case-insensitive split on </p> tag, handling variations like </P>, </p >, etc.
        paragraph_pattern = re.compile(r'(</[pP]\s*>)', re.IGNORECASE)
        parts = paragraph_pattern.split(content)

        if not parts or len(parts) < 3:
            # Fallback: append links at the end if too few paragraphs
            logger.warning("Article has fewer than 3 paragraphs. Appending links at end.")
            links_html = ''.join(
                f'<p>For more information, '
                f'<a href="{link.target_url}" title="{link.anchor_text}">'
                f'{link.anchor_text}</a>.</p>'
                for link in links
            )
            return content + links_html

        # Reconstruct paragraphs: combine content with closing tags
        paragraphs = []
        i = 0
        while i < len(parts):
            if i + 1 < len(parts) and paragraph_pattern.match(parts[i + 1]):
                paragraphs.append(parts[i] + parts[i + 1])
                i += 2
            else:
                paragraphs.append(parts[i])
                i += 1

        # Filter out empty paragraphs
        paragraphs = [p for p in paragraphs if p.strip()]

        if len(paragraphs) < 2:
            logger.warning("After reconstruction, too few paragraphs. Appending links at end.")
            links_html = ''.join(
                f'<p>For more information, '
                f'<a href="{link.target_url}" '
                f'title="{link.anchor_text}">'
                f'{link.anchor_text}</a>.</p>'
                for link in links
            )
            return content + links_html

        # Insert links at strategic positions (after 1/4, 2/4, and 3/4 of the content)
        total_paragraphs = len(paragraphs)
        link_positions = [
            max(1, total_paragraphs // 4),
            max(2, (2 * total_paragraphs) // 4),
            max(3, (3 * total_paragraphs) // 4)
        ]

        link_idx = 0
        inserted_count = 0
        result_parts = []

        for idx, para in enumerate(paragraphs):
            result_parts.append(para)

            # Insert link after this paragraph if it's a target position
            if idx in link_positions and link_idx < len(links):
                link = links[link_idx]
                # Insert a contextual link paragraph
                link_html = (
                f'<p class="internal-link">You might also be interested in: '
                f'<a href="{link.target_url}" title="{link.anchor_text}">'
                f'{link.anchor_text}</a></p>'
            )
                result_parts.append(link_html)
                link_idx += 1
                inserted_count += 1

        # If we still have remaining links, append them at the end
        while link_idx < len(links):
            link = links[link_idx]
            link_html = (
            f'<p class="internal-link">Related reading: '
            f'<a href="{link.target_url}" title="{link.anchor_text}">'
            f'{link.anchor_text}</a></p>'
        )
            result_parts.append(link_html)
            link_idx += 1
            inserted_count += 1

        logger.info("Inserted %d internal links into content.", inserted_count)
        return ''.join(result_parts)
