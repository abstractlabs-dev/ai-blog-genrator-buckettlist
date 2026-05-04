"""
RelatedArticleFinder
====================
Finds the top-N most semantically similar published articles for a given article.

Strategy
--------
1. Load all rows from articles.csv where wp_published_url is populated.
2. Encode "title + short_description" for each row using a fast sentence-transformer
   model (all-MiniLM-L6-v2, ~80 MB, runs on CPU in <1 s for 10 k articles).
3. Compute cosine similarity against the current article's title + description.
4. Return the top-K matches (excluding self) as [{title, url, score}].

Fallback
--------
If sentence-transformers is not installed, falls back to Jaccard similarity on
tokenised title words — no crash, slightly lower quality.

No external database required — purely CSV + in-memory vectors.
"""
from __future__ import annotations

import logging
import os
import re
import csv
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy dependency
# ---------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer, util as st_util
    import torch  # bundled with sentence-transformers
    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False
    logger.warning(
        "sentence-transformers not installed. "
        "RelatedArticleFinder will use keyword-overlap fallback. "
        "Install with: pip install sentence-transformers"
    )


# ---------------------------------------------------------------------------
# Model singleton — loaded once per process
# ---------------------------------------------------------------------------
_MODEL: Optional["SentenceTransformer"] = None

def _get_model() -> Optional["SentenceTransformer"]:
    global _MODEL
    if not _ST_AVAILABLE:
        return None
    if _MODEL is None:
        try:
            logger.info("Loading sentence-transformer model 'all-MiniLM-L6-v2' …")
            _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Sentence-transformer model loaded.")
        except Exception as exc:
            logger.warning("Failed to load sentence-transformer model: %s", exc)
    return _MODEL


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------
class RelatedArticleFinder:
    """
    Finds semantically related articles from the published CSV records.

    Usage
    -----
    finder = RelatedArticleFinder(csv_path=Config.CSV_PATH)
    related = finder.find(title="Best Bungee Jumping Rishikesh", top_k=3)
    # → [{"title": "...", "url": "...", "score": 0.87}, ...]
    """

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self._corpus: List[Dict] = []  # published articles with url populated
        self._corpus_texts: List[str] = []
        self._corpus_embeddings = None  # torch.Tensor or None
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find(
        self,
        title: str,
        short_description: str = "",
        top_k: int = 3,
        min_score: float = 0.25,
    ) -> List[Dict]:
        """
        Return up to *top_k* related articles similar to the given title.

        Args:
            title:             Title of the current article (used as the query).
            short_description: Brief description for richer semantic match.
            top_k:             Maximum number of related articles to return.
            min_score:         Minimum similarity score (0-1) to include.

        Returns:
            List of dicts: [{"title": str, "url": str, "score": float}]
        """
        if not self._loaded:
            self._load_corpus()

        if not self._corpus:
            logger.debug("No published articles in corpus yet — skipping related search.")
            return []

        query = self._build_text(title, short_description)

        if _ST_AVAILABLE and _get_model() is not None:
            return self._find_semantic(query, top_k, min_score, title)
        else:
            return self._find_jaccard(query, top_k, min_score, title)

    # ------------------------------------------------------------------
    # Internal: corpus loading
    # ------------------------------------------------------------------

    def _load_corpus(self) -> None:
        """Load all published articles (wp_published_url != '') from CSV."""
        self._corpus = []
        self._corpus_texts = []
        self._corpus_embeddings = None
        self._loaded = True

        if not os.path.exists(self.csv_path):
            logger.debug("CSV not found at %s — corpus empty.", self.csv_path)
            return

        try:
            with open(self.csv_path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    url = (row.get("wp_published_url") or "").strip()
                    if not url:
                        # Fall back to pre-computed canonical url
                        url = (row.get("url") or "").strip()
                    if not url:
                        continue  # skip unpublished
                    self._corpus.append({
                        "title": (row.get("title") or "").strip(),
                        "url": url,
                        "short_description": (row.get("short_description") or "").strip(),
                        "keywords": (row.get("keywords") or "").strip(),
                    })
        except Exception as exc:
            logger.error("RelatedArticleFinder: failed to read CSV: %s", exc)
            return

        self._corpus_texts = [
            self._build_text(a["title"], a["short_description"])
            for a in self._corpus
        ]

        # Pre-compute embeddings once if sentence-transformers is available
        if _ST_AVAILABLE and _get_model() is not None and self._corpus_texts:
            try:
                model = _get_model()
                self._corpus_embeddings = model.encode(
                    self._corpus_texts, convert_to_tensor=True, show_progress_bar=False
                )
                logger.info(
                    "RelatedArticleFinder: encoded %d published articles.", len(self._corpus)
                )
            except Exception as exc:
                logger.warning("Failed to pre-encode corpus: %s", exc)

    def reload(self) -> None:
        """Force reload the corpus from disk (call after new WP publishes)."""
        self._loaded = False
        self._load_corpus()

    # ------------------------------------------------------------------
    # Internal: similarity strategies
    # ------------------------------------------------------------------

    def _find_semantic(
        self, query: str, top_k: int, min_score: float, original_title: str
    ) -> List[Dict]:
        """Cosine similarity via sentence-transformers."""
        try:
            model = _get_model()
            query_emb = model.encode(query, convert_to_tensor=True)
            scores = st_util.cos_sim(query_emb, self._corpus_embeddings)[0]

            # Convert to python list
            score_list = scores.tolist()
            ranked = sorted(
                enumerate(score_list), key=lambda x: x[1], reverse=True
            )

            results = []
            for idx, score in ranked:
                if len(results) >= top_k:
                    break
                article = self._corpus[idx]
                # Exclude self (exact title match)
                if article["title"].lower().strip() == original_title.lower().strip():
                    continue
                if score < min_score:
                    break
                results.append({
                    "title": article["title"],
                    "url": article["url"],
                    "score": round(float(score), 4),
                })
            return results

        except Exception as exc:
            logger.warning("Semantic search failed: %s — falling back to Jaccard.", exc)
            return self._find_jaccard(query, top_k, min_score, original_title)

    def _find_jaccard(
        self, query: str, top_k: int, min_score: float, original_title: str
    ) -> List[Dict]:
        """
        Keyword-overlap fallback. Jaccard similarity on tokenised title words.
        Works with zero ML dependencies.
        """
        query_tokens = set(re.findall(r'\b\w{3,}\b', query.lower()))
        if not query_tokens:
            return []

        scored = []
        for article in self._corpus:
            if article["title"].lower().strip() == original_title.lower().strip():
                continue
            doc_tokens = set(
                re.findall(r'\b\w{3,}\b', (article["title"] + " " + article["short_description"]).lower())
            )
            if not doc_tokens:
                continue
            intersection = len(query_tokens & doc_tokens)
            union = len(query_tokens | doc_tokens)
            score = intersection / union if union else 0.0
            if score >= min_score:
                scored.append((score, article))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"title": a["title"], "url": a["url"], "score": round(s, 4)}
            for s, a in scored[:top_k]
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_text(title: str, description: str) -> str:
        parts = [p.strip() for p in [title, description] if p and p.strip()]
        return ". ".join(parts)
