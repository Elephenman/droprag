"""DropRAG 向量存储 - sqlite-vec 实现

轻量化向量存储，安装包 <1MB，性能: 10万向量 <20ms。
"""

import struct
import sqlite3
from typing import List, Dict, Optional
from collections import defaultdict

import sqlite_vec
import numpy as np

from droprag.logging import get_logger

log = get_logger(__name__)


def _serialize_f32(vector: List[float]) -> bytes:
    """将 float32 向量序列化为 sqlite-vec 所需的 bytes 格式"""
    return struct.pack(f"{len(vector)}f", *vector)


def _deserialize_f32(data: bytes, dim: int) -> List[float]:
    """从 bytes 反序列化 float32 向量"""
    return list(struct.unpack(f"{dim}f", data))


class VectorStore:
    """基于 sqlite-vec 的向量存储"""

    def __init__(self, db_path: str, dim: int = 512):
        self.db_path = db_path
        self.dim = dim

        import os
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)

        self._init_tables()
        log.info(f"VectorStore 初始化完成 (dim={dim}, path={db_path})")

    def _init_tables(self):
        """创建表结构"""
        self.conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks
            USING vec0(
                chunk_id TEXT PRIMARY KEY,
                embedding float[{self.dim}] distance_metric=cosine
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunk_meta (
                chunk_id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                filename TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                file_type TEXT NOT NULL DEFAULT '',
                heading TEXT NOT NULL DEFAULT '',
                folder TEXT NOT NULL DEFAULT '',
                subfolder TEXT NOT NULL DEFAULT '',
                chunk_index INTEGER NOT NULL DEFAULT 0,
                total_chunks INTEGER NOT NULL DEFAULT 0,
                char_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        self.conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_meta_source ON chunk_meta(source);
            CREATE INDEX IF NOT EXISTS idx_meta_category ON chunk_meta(category);
            CREATE INDEX IF NOT EXISTS idx_meta_file_type ON chunk_meta(file_type);
        """)
        self.conn.commit()

    def add(self, chunks: List[Dict]) -> int:
        """批量添加文档块"""
        if not chunks:
            return 0

        batch_size = 500
        total = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            vec_rows = []
            meta_rows = []

            for chunk in batch:
                meta = chunk.get("metadata", {})
                vec_rows.append((
                    chunk["id"],
                    _serialize_f32(chunk["embedding"]),
                ))
                meta_rows.append((
                    chunk["id"],
                    chunk.get("content", ""),
                    meta.get("source", ""),
                    meta.get("filename", ""),
                    meta.get("category", ""),
                    meta.get("file_type", ""),
                    meta.get("heading", ""),
                    meta.get("folder", ""),
                    meta.get("subfolder", ""),
                    meta.get("chunk_id", 0),
                    meta.get("total_chunks", 0),
                    meta.get("char_count", 0),
                ))

            self.conn.executemany(
                "INSERT OR REPLACE INTO vec_chunks(chunk_id, embedding) VALUES (?, ?)",
                vec_rows,
            )
            self.conn.executemany("""
                INSERT OR REPLACE INTO chunk_meta
                (chunk_id, content, source, filename, category, file_type,
                 heading, folder, subfolder, chunk_index, total_chunks, char_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, meta_rows)

            self.conn.commit()
            total += len(batch)
            log.debug(f"写入向量批次 {i // batch_size + 1}: {len(batch)} 条")

        log.info(f"添加 {total} 个文档块")
        return total

    def search(self, query_embedding: List[float], top_k: int = 10,
               category: Optional[str] = None,
               min_score: float = 0.0) -> List[Dict]:
        """语义搜索"""
        query_bytes = _serialize_f32(query_embedding)

        rows = self.conn.execute("""
            SELECT chunk_id, distance
            FROM vec_chunks
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
        """, (query_bytes, top_k * 3)).fetchall()

        if not rows:
            return []

        chunk_ids = [row[0] for row in rows]
        distances = {row[0]: row[1] for row in rows}

        placeholders = ",".join("?" * len(chunk_ids))
        meta_rows = self.conn.execute(f"""
            SELECT chunk_id, content, source, filename, category,
                   file_type, heading, folder, subfolder,
                   chunk_index, total_chunks, char_count
            FROM chunk_meta
            WHERE chunk_id IN ({placeholders})
        """, chunk_ids).fetchall()

        meta_map = {}
        for row in meta_rows:
            meta_map[row[0]] = {
                "content": row[1],
                "source": row[2],
                "filename": row[3],
                "category": row[4],
                "file_type": row[5],
                "heading": row[6],
                "folder": row[7],
                "subfolder": row[8],
                "chunk_id": row[9],
                "total_chunks": row[10],
                "char_count": row[11],
            }

        results = []
        for chunk_id, distance in rows:
            if distance is None:
                continue
            meta = meta_map.get(chunk_id)
            if meta is None:
                continue
            if category and meta.get("category") != category:
                continue
            score = 1.0 - distance
            if score < min_score:
                continue
            results.append({
                "content": meta["content"],
                "metadata": meta,
                "score": round(score, 4),
            })

        return results[:top_k]

    def search_keyword(self, keyword: str, top_k: int = 10,
                       file_type: Optional[str] = None) -> List[Dict]:
        """关键词搜索（基于 LIKE 模糊匹配）"""
        query = """
            SELECT chunk_id, content, source, filename, category,
                   file_type, heading, folder, subfolder,
                   chunk_index, total_chunks, char_count
            FROM chunk_meta
            WHERE content LIKE ?
        """
        params: list = [f"%{keyword}%"]

        if file_type:
            query += " AND file_type = ?"
            params.append(file_type)

        query += " LIMIT ?"
        params.append(top_k)

        rows = self.conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            results.append({
                "content": row[1],
                "metadata": {
                    "source": row[2], "filename": row[3], "category": row[4],
                    "file_type": row[5], "heading": row[6], "folder": row[7],
                    "subfolder": row[8], "chunk_id": row[9],
                    "total_chunks": row[10], "char_count": row[11],
                },
                "score": 0.5,
                "match_type": "keyword",
            })
        return results

    def hybrid_search(self, query_embedding: List[float], keyword: str,
                      top_k: int = 10, category: Optional[str] = None,
                      min_score: float = 0.0,
                      semantic_weight: float = 0.7, keyword_weight: float = 0.3,
                      rrf_k: int = 60) -> List[Dict]:
        """混合搜索: 语义 + 关键词 RRF 融合"""
        semantic_results = self.search(query_embedding, top_k=top_k * 3,
                                       category=category, min_score=0.0)
        keyword_results = self.search_keyword(keyword, top_k=top_k * 3)
        return self._rrf_merge(
            semantic_results, keyword_results,
            semantic_weight, keyword_weight, rrf_k, top_k, min_score,
        )

    @staticmethod
    def _make_chunk_id(item: Dict, fallback_idx: int, prefix: str) -> str:
        meta = item.get("metadata", {})
        source = meta.get("source", "")
        chunk_id = meta.get("chunk_id")
        if source and chunk_id is not None:
            return f"{source}__{chunk_id}"
        return f"{prefix}_{fallback_idx}"

    def _rrf_merge(self, semantic_results: List[Dict], keyword_results: List[Dict],
                   s_weight: float, k_weight: float, rrf_k: int,
                   top_k: int, min_score: float) -> List[Dict]:
        """Reciprocal Rank Fusion 融合排序"""
        rrf_scores: Dict[str, float] = defaultdict(float)
        chunk_data: Dict[str, Dict] = {}

        for rank, item in enumerate(semantic_results, 1):
            cid = self._make_chunk_id(item, rank, "sem")
            rrf_scores[cid] += s_weight / (rrf_k + rank)
            if cid not in chunk_data:
                chunk_data[cid] = item
            else:
                if item.get("score", 0) > chunk_data[cid].get("score", 0):
                    chunk_data[cid]["score"] = item["score"]

        for rank, item in enumerate(keyword_results, 1):
            cid = self._make_chunk_id(item, rank, "kw")
            rrf_scores[cid] += k_weight / (rrf_k + rank)
            if cid not in chunk_data:
                chunk_data[cid] = item
                chunk_data[cid]["match_types"] = ["keyword"]
            else:
                existing = chunk_data[cid].get("match_types", ["semantic"])
                if "keyword" not in existing:
                    chunk_data[cid]["match_types"] = existing + ["keyword"]

        sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)

        results = []
        for cid in sorted_ids[:top_k]:
            item = chunk_data[cid].copy()
            item["rrf_score"] = round(rrf_scores[cid], 6)
            sem_score = item.get("score", 0)
            if sem_score > 0 and sem_score < min_score:
                continue
            item["match_types"] = item.get("match_types", ["semantic", "keyword"])
            results.append(item)

        return results[:top_k]

    def delete_by_source(self, source: str) -> int:
        """删除指定来源的所有块，返回删除数量"""
        rows = self.conn.execute(
            "SELECT chunk_id FROM chunk_meta WHERE source = ?", (source,)
        ).fetchall()
        chunk_ids = [row[0] for row in rows]
        if not chunk_ids:
            return 0

        self.conn.executemany(
            "DELETE FROM vec_chunks WHERE chunk_id = ?",
            [(cid,) for cid in chunk_ids],
        )
        self.conn.execute("DELETE FROM chunk_meta WHERE source = ?", (source,))
        self.conn.commit()
        return len(chunk_ids)

    def get_all_sources(self) -> set:
        """获取所有已入库的文件路径"""
        rows = self.conn.execute("SELECT DISTINCT source FROM chunk_meta").fetchall()
        return {row[0] for row in rows}

    def count(self) -> int:
        """获取总块数"""
        row = self.conn.execute("SELECT COUNT(*) FROM chunk_meta").fetchone()
        return row[0]

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {"total_chunks": self.count()}

    def get_embeddings_for_umap(self) -> Dict:
        """获取所有向量用于 UMAP 降维"""
        rows = self.conn.execute("""
            SELECT v.embedding, m.source, m.filename, m.category, m.heading, m.content
            FROM vec_chunks v
            JOIN chunk_meta m ON v.chunk_id = m.chunk_id
        """).fetchall()

        embeddings = []
        metadatas = []
        documents = []
        for row in rows:
            emb = _deserialize_f32(row[0], self.dim)
            embeddings.append(emb)
            metadatas.append({
                "source": row[1], "filename": row[2],
                "category": row[3], "heading": row[4],
            })
            documents.append(row[5])

        return {
            "embeddings": embeddings,
            "metadatas": metadatas,
            "documents": documents,
        }

    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()
