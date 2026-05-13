import sqlite3
import json
import hashlib
import time
import os
from typing import Optional, Dict, Any, List, Tuple
from viki.config.logger import viki_logger

try:
    import numpy as np
except ImportError:
    np = None

class SemanticCache:
    """
    Tier 3 Optimization: Vector-based semantic cache for bypassing LLM processing.
    Stores query-response pairs and performs similarity lookups.
    """
    def __init__(self, data_dir: str, threshold: float = 0.96):
        self.data_dir = data_dir
        self.threshold = threshold
        self.db_path = os.path.join(self.data_dir, "viki_cache.db")
        os.makedirs(self.data_dir, exist_ok=True)
        self._init_db()
        self._encoder = None
        self._encoder_loaded = False

    def _init_db(self):
        """Initialize cache schema."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute('''CREATE TABLE IF NOT EXISTS semantic_cache (
            query_hash TEXT PRIMARY KEY,
            query_text TEXT,
            response_json TEXT,
            embedding BLOB,
            timestamp REAL,
            hit_count INTEGER DEFAULT 1
        )''')
        conn.commit()
        conn.close()

    @property
    def encoder(self):
        if not self._encoder_loaded:
            from viki.core.embeddings import get_encoder
            self._encoder = get_encoder()
            self._encoder_loaded = True
        return self._encoder

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        if not self.encoder:
            return None
        try:
            emb = self.encoder.encode(text, convert_to_tensor=False)
            if hasattr(emb, "tolist"):
                return emb.tolist()
            return list(emb)
        except Exception as e:
            viki_logger.warning(f"Cache embedding failed: {e}")
            return None

    def lookup(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Lookup a query in the cache. 
        First tries exact hash match (instant), then semantic similarity (if encoder available).
        """
        # 1. Exact Match
        query_hash = hashlib.md5(query.strip().lower().encode()).hexdigest()
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("SELECT response_json, query_text FROM semantic_cache WHERE query_hash = ?", (query_hash,))
        row = cur.fetchone()
        if row:
            viki_logger.info(f"SemanticCache: Exact HIT for '{query[:30]}...'")
            self._record_hit(conn, query_hash)
            conn.close()
            return json.loads(row['response_json'])

        # 2. Semantic Match
        if not self.encoder:
            conn.close()
            return None

        query_emb = self._get_embedding(query)
        if not query_emb:
            conn.close()
            return None

        # Fetch all candidates (limit to recent or high-hit for speed in large cache)
        cur.execute("SELECT query_hash, query_text, response_json, embedding FROM semantic_cache ORDER BY timestamp DESC LIMIT 1000")
        candidates = cur.fetchall()
        
        best_hash = None
        best_score = -1.0
        best_response = None

        q_vec = np.array(query_emb) if np is not None else query_emb

        for cand in candidates:
            if not cand['embedding']:
                continue
            
            try:
                c_emb = np.frombuffer(cand['embedding'], dtype=np.float32) if np is not None else json.loads(cand['embedding'])
                
                if np is not None:
                    # Cosine similarity
                    norm_q = np.linalg.norm(q_vec)
                    norm_c = np.linalg.norm(c_emb)
                    if norm_q > 0 and norm_c > 0:
                        score = np.dot(q_vec, c_emb) / (norm_q * norm_c)
                    else:
                        score = 0
                else:
                    # Fallback list math
                    score = self._manual_cosine(q_vec, c_emb)

                if score > best_score:
                    best_score = score
                    best_hash = cand['query_hash']
                    best_response = cand['response_json']
            except Exception as e:
                viki_logger.debug(f"Similarity check failed for row: {e}")
                continue

        if best_score >= self.threshold:
            viki_logger.info(f"SemanticCache: Semantic HIT (score={best_score:.3f}) for '{query[:30]}...'")
            self._record_hit(conn, best_hash)
            conn.close()
            return json.loads(best_response)

        conn.close()
        return None

    def store(self, query: str, response: Dict[str, Any]):
        """Store a query-response pair in the cache."""
        try:
            query_hash = hashlib.md5(query.strip().lower().encode()).hexdigest()
            query_emb = self._get_embedding(query)
            
            emb_blob = None
            if query_emb:
                if np is not None:
                    emb_blob = np.array(query_emb, dtype=np.float32).tobytes()
                else:
                    emb_blob = json.dumps(query_emb).encode()

            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute('''INSERT OR REPLACE INTO semantic_cache 
                (query_hash, query_text, response_json, embedding, timestamp, hit_count)
                VALUES (?, ?, ?, ?, ?, COALESCE((SELECT hit_count + 1 FROM semantic_cache WHERE query_hash = ?), 1))''',
                (query_hash, query, json.dumps(response), emb_blob, time.time(), query_hash))
            conn.commit()
            conn.close()
        except Exception as e:
            viki_logger.warning(f"Failed to store in SemanticCache: {e}")

    def _record_hit(self, conn, q_hash: str):
        try:
            conn.execute("UPDATE semantic_cache SET hit_count = hit_count + 1, timestamp = ? WHERE query_hash = ?", (time.time(), q_hash))
            conn.commit()
        except Exception:
            pass

    def _manual_cosine(self, v1: List[float], v2: List[float]) -> float:
        import math
        dot = sum(a*b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a*a for a in v1))
        norm2 = math.sqrt(sum(b*b for b in v2))
        if norm1 > 0 and norm2 > 0:
            return dot / (norm1 * norm2)
        return 0.0
