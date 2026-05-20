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
from datetime import datetime
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
    # ── Multi-platform tracking columns ──────────────────────────────────────
    # wp_published_url      — live WordPress permalink (from WP REST API)
    # wp_published_slug     — slug WordPress actually assigned
    # wp_published_title    — title WordPress actually rendered
    # blogger_published_url — live Blogger post URL (from Blogger API)
    # tumblr_published_url  — live Tumblr post URL (from Tumblr API)
    # linkedin_published_path — native JSON file path for LinkedIn
    # medium_published_path   — native JSON file path for Medium
    # platforms_published   — comma-separated: e.g. "wordpress,blogger"
    HEADER = [
        'article_no', 'article_id', 'date', 'title',
        'url',                    # Pre-computed canonical URL (our side)
        'wp_published_url',       # Live WordPress permalink
        'wp_published_slug',      # Slug WordPress actually used
        'wp_published_title',     # Title WordPress actually rendered
        'blogger_published_url',  # Live Blogger post URL
        'tumblr_published_url',   # Live Tumblr post URL
        'linkedin_published_path', # Path to native LinkedIn JSON payload
        'medium_published_path',   # Path to native Medium JSON payload
        'platforms_published',    # Comma-sep list of confirmed platforms
        'short_description', 'keywords', 'project_name', 'article_published'
    ]

    def __init__(self, csv_path: str = Config.CSV_PATH):
        self.csv_path = csv_path
        self.header = self.HEADER  # Instance alias for backward compat
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        if not os.path.exists(self.csv_path):
            self._write_header_only()
        else:
            self._migrate_headers_if_needed()

    def _migrate_headers_if_needed(self) -> None:
        """
        Check if the CSV exists and has all current HEADER fields.
        If any are missing, migrate the CSV while keeping all existing data intact.
        """
        if not os.path.exists(self.csv_path):
            return
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                existing_headers = next(reader, None)
            
            if not existing_headers:
                # File is empty, just write header only
                self._write_header_only()
                return

            # Check if there are missing columns
            missing_columns = [col for col in self.header if col not in existing_headers]
            if not missing_columns:
                return

            logger.info("Migrating articles.csv headers to include missing fields: %s", missing_columns)
            
            # Read all rows as dictionaries using the existing headers
            rows = []
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Pre-populate missing columns with empty string
                    for col in self.header:
                        if col not in row:
                            row[col] = ""
                    rows.append(row)
            
            # Rewrite the file with the new header and all rows
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self.header)
                for row in rows:
                    writer.writerow([row.get(col, "") for col in self.header])
            
            logger.info("Successfully migrated articles.csv with new headers.")
        except Exception as e:
            logger.error("Failed to migrate articles.csv headers: %s", e)

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
        """Save a newly generated article row. Platform columns are empty until publish."""
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
                "",  # wp_published_url
                "",  # wp_published_slug
                "",  # wp_published_title
                "",  # blogger_published_url
                "",  # tumblr_published_url
                "",  # linkedin_published_path
                "",  # medium_published_path
                "",  # platforms_published
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
        After a confirmed WordPress publish, write the live WP URL, slug, rendered
        title, and append 'wordpress' to platforms_published.
        Only called when wp_result.get('id') is non-empty.
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
                # Append 'wordpress' to platforms_published (avoid duplicates)
                platforms = [p.strip() for p in (row.get('platforms_published') or '').split(',') if p.strip()]
                if 'wordpress' not in platforms:
                    platforms.append('wordpress')
                row['platforms_published'] = ','.join(platforms)
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

    def update_article_blogger_data(self, article_id: str, blogger_url: str) -> bool:
        """
        After a confirmed Blogger publish (blogger_result.get('id') is non-empty),
        write the live Blogger URL and append 'blogger' to platforms_published.
        """
        articles = self.get_all_articles()
        updated = False
        new_rows = []
        for row in articles:
            if row.get('article_id') == article_id:
                row['blogger_published_url'] = blogger_url or ""
                row['article_published']     = 'yes'
                platforms = [p.strip() for p in (row.get('platforms_published') or '').split(',') if p.strip()]
                if 'blogger' not in platforms:
                    platforms.append('blogger')
                row['platforms_published'] = ','.join(platforms)
                updated = True
            new_rows.append([row.get(h, "") for h in self.header])

        if updated:
            try:
                with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.header)
                    writer.writerows(new_rows)
                logger.info("Blogger data written for article %s | URL: %s", article_id, blogger_url)
                return True
            except Exception as e:
                logger.error("Failed to write Blogger data for article %s: %s", article_id, e)
                return False
        logger.warning("Article ID %s not found in CSV for Blogger data update.", article_id)
        return False

    def update_article_tumblr_data(self, article_id: str, tumblr_url: str) -> bool:
        """
        After a confirmed Tumblr publish (tumblr_result.get('id') is non-empty),
        write the live Tumblr URL and append 'tumblr' to platforms_published.
        """
        articles = self.get_all_articles()
        updated = False
        new_rows = []
        for row in articles:
            if row.get('article_id') == article_id:
                row['tumblr_published_url'] = tumblr_url or ""
                row['article_published']    = 'yes'
                platforms = [p.strip() for p in (row.get('platforms_published') or '').split(',') if p.strip()]
                if 'tumblr' not in platforms:
                    platforms.append('tumblr')
                row['platforms_published'] = ','.join(platforms)
                updated = True
            new_rows.append([row.get(h, "") for h in self.header])

        if updated:
            try:
                with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.header)
                    writer.writerows(new_rows)
                logger.info("Tumblr data written for article %s | URL: %s", article_id, tumblr_url)
                return True
            except Exception as e:
                logger.error("Failed to write Tumblr data for article %s: %s", article_id, e)
                return False
        logger.warning("Article ID %s not found in CSV for Tumblr data update.", article_id)
        return False

    def update_article_linkedin_data(self, article_id: str, linkedin_path: str) -> bool:
        """
        After a confirmed LinkedIn creation, write the local JSON path to the CSV
        and append 'linkedin' to platforms_published.
        """
        articles = self.get_all_articles()
        updated = False
        new_rows = []
        for row in articles:
            if row.get('article_id') == article_id:
                row['linkedin_published_path'] = linkedin_path or ""
                row['article_published']       = 'yes'
                platforms = [p.strip() for p in (row.get('platforms_published') or '').split(',') if p.strip()]
                if 'linkedin' not in platforms:
                    platforms.append('linkedin')
                row['platforms_published'] = ','.join(platforms)
                updated = True
            new_rows.append([row.get(h, "") for h in self.header])

        if updated:
            try:
                with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.header)
                    writer.writerows(new_rows)
                logger.info("LinkedIn path written for article %s | Path: %s", article_id, linkedin_path)
                return True
            except Exception as e:
                logger.error("Failed to write LinkedIn path for article %s: %s", article_id, e)
                return False
        logger.warning("Article ID %s not found in CSV for LinkedIn path update.", article_id)
        return False

    def update_article_medium_data(self, article_id: str, medium_path: str) -> bool:
        """
        After a confirmed Medium creation, write the local JSON path to the CSV
        and append 'medium' to platforms_published.
        """
        articles = self.get_all_articles()
        updated = False
        new_rows = []
        for row in articles:
            if row.get('article_id') == article_id:
                row['medium_published_path'] = medium_path or ""
                row['article_published']     = 'yes'
                platforms = [p.strip() for p in (row.get('platforms_published') or '').split(',') if p.strip()]
                if 'medium' not in platforms:
                    platforms.append('medium')
                row['platforms_published'] = ','.join(platforms)
                updated = True
            new_rows.append([row.get(h, "") for h in self.header])

        if updated:
            try:
                with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.header)
                    writer.writerows(new_rows)
                logger.info("Medium path written for article %s | Path: %s", article_id, medium_path)
                return True
            except Exception as e:
                logger.error("Failed to write Medium path for article %s: %s", article_id, e)
                return False
        logger.warning("Article ID %s not found in CSV for Medium path update.", article_id)
        return False

    def add_external_article(self, article_name: str, platform: str) -> None:
        """
        Appends a row to articles_external.csv, tracking articles created for
        linkedin or medium. Columns: Sr No, Name of the article, Generated At, Platform.
        """
        dir_path = os.path.dirname(self.csv_path)
        ext_path = os.path.join(dir_path, "articles_external.csv")
        
        # Determine next Sr No
        sr_no = 1
        file_exists = os.path.exists(ext_path)
        if file_exists:
            try:
                with open(ext_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    if len(rows) > 1:
                        # Read the Sr No of the last row and increment
                        last_row = rows[-1]
                        if last_row and last_row[0].isdigit():
                            sr_no = int(last_row[0]) + 1
            except Exception as e:
                logger.warning("Could not read articles_external.csv for Sr No calculation: %s", e)
        
        headers = ['Sr No', 'Name of the article', 'Generated At', 'Platform']
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(ext_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists or os.path.getsize(ext_path) == 0:
                    writer.writerow(headers)
                writer.writerow([sr_no, article_name, now_str, platform])
            logger.info("External article '%s' (%s) logged to %s", article_name, platform, ext_path)
        except Exception as e:
            logger.error("Failed to write to articles_external.csv: %s", e)

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
                    vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_google(
                        model_id="text-embedding-004",
                        api_endpoint="generative-ai"
                    ),
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
