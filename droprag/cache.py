"""DropRAG 持久化缓存层

基于 SQLite 的磁盘缓存，重启不丢失:
1. 查询结果缓存 (带TTL)
2. Embedding 缓存 (持久化，避免重复编码)
"""

import hashlib
import json
import sqlite3
import time
import os
from typing import Dict, Optional, List

from droprag.config import CacheConfig
from droprag.logging import get_logger

log = get_logger(__name__)


class DropRAGCache:
    """基于 SQLite 的持久化缓存"""

    def __init__(self, config: Optional[CacheConfig] = None, db_path: str = None):
        self.config = config or CacheConfig()
        if db_path is None:
            db_path = os.path.join(os.path.abspath("./data"), "cache.db")
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS query_cache (
                cache_key TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                ttl_seconds INTEGER NOT NULL DEFAULT 3600
            );

            CREATE TABLE IF NOT EXISTS embedding_cache (
                text_hash TEXT PRIMARY KEY,
                embedding_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_query_created ON query_cache(created_at);
        """)
        self.conn.commit()
        self._cleanup_expired()

    def _cleanup_expired(self):
        """清理过期的查询缓存"""
        now = time.time()
        self.conn.execute(
            "DELETE FROM query_cache WHERE (created_at + ttl_seconds) < ?",
            (now,),
        )
        emb_ttl = self.config.embedding_ttl_seconds
        if emb_ttl > 0:
            cutoff = now - emb_ttl
            self.conn.execute(
                "DELETE FROM embedding_cache WHERE created_at < ?",
                (cutoff,),
            )
        self.conn.commit()

    # ── 查询缓存 ──

    def _make_query_key(self, query: str, level: int, category: Optional[str],
                        top_k: int, min_score: float) -> str:
        key_str = f"{query}:{level}:{category}:{top_k}:{min_score}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:32]

    def get_query_result(self, query: str, level: int, category: Optional[str],
                         top_k: int, min_score: float) -> Optional[Dict]:
        key = self._make_query_key(query, level, category, top_k, min_score)
        row = self.conn.execute(
            "SELECT result_json, created_at, ttl_seconds FROM query_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        if time.time() - row[1] > row[2]:
            self.conn.execute("DELETE FROM query_cache WHERE cache_key = ?", (key,))
            self.conn.commit()
            return None
        return json.loads(row[0])

    def set_query_result(self, query: str, level: int, category: Optional[str],
                         top_k: int, min_score: float, result: Dict):
        key = self._make_query_key(query, level, category, top_k, min_score)
        self.conn.execute("""
            INSERT OR REPLACE INTO query_cache (cache_key, result_json, created_at, ttl_seconds)
            VALUES (?, ?, ?, ?)
        """, (key, json.dumps(result, ensure_ascii=False), time.time(), self.config.query_ttl_seconds))
        self.conn.commit()

        count = self.conn.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0]
        if count > self.config.max_query_cache:
            excess = count - self.config.max_query_cache
            self.conn.execute("""
                DELETE FROM query_cache WHERE cache_key IN (
                    SELECT cache_key FROM query_cache ORDER BY created_at ASC LIMIT ?
                )
            """, (excess,))
            self.conn.commit()

    # ── Embedding 缓存 ──

    def _make_embedding_key(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def get_embedding(self, text: str) -> Optional[List[float]]:
        key = self._make_embedding_key(text)
        row = self.conn.execute(
            "SELECT embedding_json FROM embedding_cache WHERE text_hash = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def set_embedding(self, text: str, embedding: List[float]):
        key = self._make_embedding_key(text)
        self.conn.execute("""
            INSERT OR REPLACE INTO embedding_cache (text_hash, embedding_json, created_at)
            VALUES (?, ?, ?)
        """, (key, json.dumps(embedding), time.time()))
        self.conn.commit()

        count = self.conn.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
        if count > self.config.max_embedding_cache:
            excess = count - self.config.max_embedding_cache
            self.conn.execute("""
                DELETE FROM embedding_cache WHERE text_hash IN (
                    SELECT text_hash FROM embedding_cache ORDER BY created_at ASC LIMIT ?
                )
            """, (excess,))
            self.conn.commit()

    # ── 管理接口 ──

    def clear_query_cache(self):
        self.conn.execute("DELETE FROM query_cache")
        self.conn.commit()

    def clear_embedding_cache(self):
        self.conn.execute("DELETE FROM embedding_cache")
        self.conn.commit()

    def get_stats(self) -> Dict:
        q_count = self.conn.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0]
        e_count = self.conn.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
        return {
            "query_cache_size": q_count,
            "query_cache_max": self.config.max_query_cache,
            "embedding_cache_size": e_count,
            "embedding_cache_max": self.config.max_embedding_cache,
        }

    def close(self):
        if self.conn:
            self.conn.close()
