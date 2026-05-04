"""
Utilities Module
This module contains helper classes and functions that support the main application logic.
- CSVManager: Handles reading from and writing to CSV files.
- VectorStoreManager: Manages the FAISS vector store for article similarity.
"""
import os
import re
import csv
import hashlib
import logging
from typing import List, Dict, Optional

from src.config import Config
from src.models import ArticleDraft

# --- Dependency Imports with Graceful Fallbacks ---
try:
    import weaviate
    WEAVIATE_AVAILABLE = True
except Exception as e:
    WEAVIATE_AVAILABLE = False
    logging.warning(f"Weaviate client is not available: {e}. Vector store features will be disabled.")


logger = logging.getLogger(__name__)


class CSVManager:
    # ── Expanded header: 3 new WordPress tracking columns ─────────────────────
    # wp_published_url   — live permalink returned by WordPress REST API after publish
    # wp_published_slug  — actual slug WordPress assigned (confirms no -2/-3 appended)
    # wp_published_title — article title as WordPress rendered it (catches sanitization)
    HEADER = [
        'article_no', 'article_id', 'date', 'title',
        'url',                  # Pre-computed canonical URL (our side)
        'wp_published_url',     # Live WordPress permalink (from API response)
        'wp_published_slug',    # Slug WordPress actually used
        'wp_published_title',   # Title WordPress actually rendered
        'short_description', 'keywords', 'project_name', 'article_published'
    ]

    def __init__(self, csv_path: str = Config.CSV_PATH):
        self.csv_path = csv_path
        self.header = self.HEADER  # Instance alias for backward compat
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        if not os.path.exists(self.csv_path):
            self._write_header_only()

    def _write_header_only(self) -> None:
        """Write just the header row — used for init and reset."""
        with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(self.header)

    def reset_csv(self) -> None:
        """
        Truncate the CSV to headers only — removes ALL article data.
        Use this for a fresh run. Logs a warning so it is never silent.
        """
        self._write_header_only()
        logger.warning("articles.csv has been RESET to headers only. All previous article records cleared.")

    def save_article(self, article: ArticleDraft, short_description: str, product_name: Optional[str] = None) -> str:
        """Save a newly generated article row. WP columns are empty until publish."""
        existing_articles = self.get_all_articles()
        article_no = len(existing_articles) + 1
        article_id = hashlib.md5(article.title.encode()).hexdigest()[:8]
        generated_at = getattr(article, "generated_at", None)
        date_str = generated_at.strftime("%Y-%m-%d %H:%M:%S") if generated_at else ""

        with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                article_no,
                article_id,
                date_str,
                article.title,
                article.metadata.canonical_url,
                "",                              # wp_published_url  — filled after publish
                "",                              # wp_published_slug — filled after publish
                "",                              # wp_published_title — filled after publish
                short_description,
                ','.join(article.metadata.keywords),
                product_name if product_name else "",
                'yes' if article.is_published else 'no'
            ])
        logger.info(
            "Article #%s '%s' (ID: %s) saved to CSV (Published: %s).",
            article_no, article.title, article_id,
            'yes' if article.is_published else 'no'
        )
        return article_id

    def update_article_publication_status(self, article_id: str, status: str = 'yes') -> bool:
        """Updates the article_published column for a given article_id."""
        articles = self.get_all_articles()
        updated = False
        new_rows = []
        for row in articles:
            if row.get('article_id') == article_id:
                row['article_published'] = status
                updated = True
            new_rows.append([row.get(h, "") for h in self.header])

        if updated:
            try:
                with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.header)
                    writer.writerows(new_rows)
                logger.info("Updated article %s publication status to '%s'.", article_id, status)
                return True
            except Exception as e:
                logger.error("Failed to update article %s status: %s", article_id, e)
                return False
        logger.warning("Article ID %s not found in CSV for status update.", article_id)
        return False

    def update_article_wp_data(
        self,
        article_id: str,
        wp_url: str,
        wp_slug: str,
        wp_title: str,
    ) -> bool:
        """
        After a successful WordPress publish, write the live WP URL, slug, and
        rendered title back into the article row.  This is the ground-truth record
        that prevents slug collisions on subsequent runs.

        Args:
            article_id:  MD5-hash ID assigned at generation time (8 chars).
            wp_url:      Full permalink returned by wp_result.get('link').
            wp_slug:     Slug returned by wp_result.get('slug').
            wp_title:    Rendered title from wp_result.get('title', {}).get('rendered').
        """
        articles = self.get_all_articles()
        updated = False
        new_rows = []
        for row in articles:
            if row.get('article_id') == article_id:
                row['wp_published_url']   = wp_url   or ""
                row['wp_published_slug']  = wp_slug  or ""
                row['wp_published_title'] = wp_title or ""
                row['article_published']  = 'yes'
                updated = True
            new_rows.append([row.get(h, "") for h in self.header])

        if updated:
            try:
                with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.header)
                    writer.writerows(new_rows)
                logger.info(
                    "WP data written for article %s | URL: %s | Slug: %s",
                    article_id, wp_url, wp_slug
                )
                return True
            except Exception as e:
                logger.error("Failed to write WP data for article %s: %s", article_id, e)
                return False
        logger.warning("Article ID %s not found in CSV for WP data update.", article_id)
        return False

    def get_all_published_slugs(self) -> set:
        """Return all confirmed WordPress slugs from previous runs (collision guard)."""
        slugs = set()
        for row in self.get_all_articles():
            slug = row.get('wp_published_slug', '').strip()
            if slug:
                slugs.add(slug)
            # Also derive from canonical url as fallback
            url = row.get('url', '').strip()
            if url and not slug:
                derived = url.rstrip('/').split('/')[-1]
                if derived:
                    slugs.add(derived)
        return slugs

    def get_all_articles(self) -> List[Dict]:
        articles = []
        if not os.path.exists(self.csv_path):
            return articles
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, fieldnames=self.header)
                next(reader, None)  # Skip header row
                for row in reader:
                    articles.append(row)
        except Exception as e:
            logger.error("Could not read articles from %s: %s", self.csv_path, e)
        return articles

    def get_covered_products(self) -> List[str]:
        """Returns list of product_names already covered in the database."""
        articles = self.get_all_articles()
        covered = {a.get('project_name') for a in articles if a.get('project_name')}
        logger.info("Found %d existing projects in the database.", len(covered))
        return list(covered)

    def save_scraped_data(self, file_path: str, header: List[str], data: List[List[str]]):
        """Saves a list of lists to a specified CSV file."""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(data)
            logger.info("Successfully saved %d rows to %s", len(data), file_path)
        except Exception as e:
            logger.error("Failed to save data to %s: %s", file_path, e)


class VectorStoreManager:
    def __init__(self, store_path: str):
        self.store_path = store_path
        self.class_name = "ArticleChunk"
        if WEAVIATE_AVAILABLE:
            self.client = self._init_client()
        else:
            self.client = None

    def _init_client(self) -> Optional[object]:
        try:
            host = os.getenv("WEAVIATE_HOST", "localhost")
            port = int(os.getenv("WEAVIATE_PORT", 8080))
            grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", 50051))
            
            client = weaviate.connect_to_local(
                host=host,
                port=port,
                grpc_port=grpc_port
            )
            self._ensure_schema(client)
            return client
        except Exception as e:
            logger.warning(f"Could not initialize Weaviate v4 client: {e}")
            return None

    def _ensure_schema(self, client: object) -> None:
        try:
            import weaviate.classes as wvc
            if not client.collections.exists(self.class_name):
                client.collections.create(
                    name=self.class_name,
                    vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_openai(),
                    properties=[
                        wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="article_id", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="title", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="chunk_index", data_type=wvc.config.DataType.INT),
                    ],
                )
        except Exception as e:
            logger.warning(f"Could not ensure Weaviate schema: {e}")

    def _split_text(self, text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
        if not text:
            return []
        length = len(text)
        if length <= chunk_size:
            return [text]
        chunks: List[str] = []
        start = 0
        while start < length:
            end = min(start + chunk_size, length)
            chunks.append(text[start:end])
            if end == length:
                break
            start = max(0, end - chunk_overlap)
        return chunks

    def add_article(self, article: ArticleDraft, article_id: str):
        if not self.client:
            logger.warning("Vector store not available. Skipping adding article to vector store.")
            return
        try:
            text_content = self._extract_text_from_html(article.content_html)
            chunks = self._split_text(text_content)
            if not chunks:
                return

            collection = self.client.collections.get(self.class_name)
            with collection.batch.dynamic() as batch:
                for idx, chunk in enumerate(chunks):
                    properties = {
                        "text": chunk,
                        "article_id": article_id,
                        "title": article.title,
                        "chunk_index": idx,
                    }
                    batch.add_object(properties=properties)

            logger.info(f"Vector store updated with {len(chunks)} chunks for article ID {article_id}.")
        except Exception as e:
            logger.error(f"Error adding article to vector store: {e}")

    def clear_all_data(self):
        """Removes all data from the Weaviate collection while preserving schema."""
        if not self.client:
            logger.warning("Vector store not available. Cannot clear data.")
            return
        try:
            if self.client.collections.exists(self.class_name):
                self.client.collections.delete(self.class_name)
                logger.info(f"Deleted Weaviate collection '{self.class_name}'.")
            self._ensure_schema(self.client)
            logger.info(f"Recreated Weaviate collection '{self.class_name}' with fresh schema.")
        except Exception as e:
            logger.error(f"Error clearing Weaviate data: {e}")

    def _extract_text_from_html(self, html_content: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', html_content)
        return re.sub(r'\s+', ' ', text).strip()

    def find_similar_articles(self, query_text: str, k: int = 3) -> List[Dict]:
        if not self.client:
            logger.warning("Vector store not available for similarity search.")
            return []
        try:
            collection = self.client.collections.get(self.class_name)
            response = collection.query.near_text(
                query=query_text,
                limit=k,
                return_metadata=["distance"]
            )

            results: List[Dict] = []
            for obj in response.objects:
                properties = obj.properties
                distance = obj.metadata.distance
                
                try:
                    similarity = 1.0 / (1.0 + float(distance))
                except Exception:
                    similarity = 0.0
                
                results.append({
                    'article_id': properties.get('article_id'),
                    'title': properties.get('title'),
                    'relevance_score': similarity,
                    'content_snippet': (properties.get('text') or '')[:200]
                })
            return results
        except Exception as e:
            logger.error(f"Error finding similar articles: {e}")
            return []
