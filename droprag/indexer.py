"""DropRAG 统一索引管理器

基于 Pipeline 的索引管理，支持全量构建和增量更新。
"""

import hashlib
import json
import os
import time
from typing import List, Dict, Optional, Set
from datetime import datetime

from droprag.config import DropRAGConfig
from droprag.pipeline import Pipeline
from droprag.loader import load_file, get_supported_extensions
from droprag.chunker import chunk_document, chunk_all_documents, Chunk
from droprag.embedder import BaseEmbedder, create_embedder
from droprag.vectorstore import VectorStore
from droprag.metadata import MetadataDB
from droprag.classifier import classify_file
from droprag.logging import get_logger

log = get_logger(__name__)


class FileIndex:
    """文件索引追踪器 (JSON 持久化)"""

    def __init__(self, path: str):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"version": "1.0", "files": {}}

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_file(self, path: str) -> Optional[dict]:
        return self.data["files"].get(path)

    def set_file(self, path: str, info: dict):
        self.data["files"][path] = info

    def remove_file(self, path: str):
        self.data["files"].pop(path, None)

    def all_sources(self) -> Set[str]:
        return set(self.data["files"].keys())

    def update_metadata(self, total_chunks: int):
        self.data["last_update"] = datetime.now().isoformat()
        self.data["total_files"] = len(self.data["files"])
        self.data["total_chunks"] = total_chunks


class Indexer:
    """统一的索引管理器"""

    def __init__(self, config: DropRAGConfig, embedder: BaseEmbedder,
                 vectorstore: VectorStore, metadata_db: MetadataDB):
        self.config = config
        self.embedder = embedder
        self.vectorstore = vectorstore
        self.metadata_db = metadata_db

        data_dir = os.path.abspath(config.data.dir)
        self.file_index = FileIndex(os.path.join(data_dir, "file_index.json"))
        self.pipeline = Pipeline(config, embedder, vectorstore, metadata_db)

    def process_file(self, filepath: str) -> Optional[Dict]:
        """处理单个文件（通过 Pipeline）"""
        result = self.pipeline.process_file(filepath)
        if result:
            # 更新文件索引
            self.file_index.set_file(filepath, {
                "hash": result["hash"],
                "category": result.get("category", ""),
                "chunk_count": result["chunks"],
                "indexed_at": datetime.now().isoformat(),
                "status": "indexed",
            })
        return result

    def remove_file(self, filepath: str) -> int:
        """移除文件"""
        count = self.vectorstore.delete_by_source(filepath)
        self.metadata_db.delete_file(filepath)
        self.file_index.remove_file(filepath)
        return count

    def build_all(self) -> Dict:
        """全量构建索引"""
        start_time = time.time()
        log.info(f"开始全量构建: {self.config.knowledge_base.path}")

        kb_path = self.config.knowledge_base.path
        if not kb_path or not os.path.exists(kb_path):
            return {"error": "知识库路径不存在"}

        # 扫描文件
        files = self.pipeline.scan_files(kb_path)
        if not files:
            return {"error": "未找到任何文件"}

        # 清理旧数据
        all_sources = self.vectorstore.get_all_sources()
        for source in all_sources:
            self.vectorstore.delete_by_source(source)
        self.metadata_db.conn.execute("DELETE FROM files")
        self.metadata_db.conn.commit()

        # 逐文件处理
        new_chunks = 0
        new_files = 0
        for filepath in files:
            result = self.process_file(filepath)
            if result:
                new_files += 1
                new_chunks += result["chunks"]

        # 保存文件索引
        total_chunks = self.vectorstore.count()
        self.file_index.update_metadata(total_chunks)
        self.file_index.save()

        elapsed = time.time() - start_time
        result = {
            "new_files": new_files,
            "new_chunks": new_chunks,
            "total_chunks_after": total_chunks,
            "time_ms": int(elapsed * 1000),
        }
        log.info(f"全量构建完成: {result}")
        return result

    def incremental_update(self, changed_files: Optional[List[str]] = None) -> Dict:
        """增量更新索引"""
        start_time = time.time()

        kb_path = self.config.knowledge_base.path
        if not kb_path or not os.path.exists(kb_path):
            return {"error": "知识库路径不存在"}

        new_files = 0
        updated_files = 0
        deleted_files = 0
        new_chunks = 0

        # 1. 检测删除的文件
        current_files = set(self.pipeline.scan_files(kb_path))
        indexed_sources = self.file_index.all_sources()

        for removed in indexed_sources - current_files:
            count = self.remove_file(removed)
            deleted_files += 1

        # 2. 处理新增/修改的文件
        existing_hashes = self.metadata_db.get_all_hashes()
        files_to_process = changed_files if changed_files else current_files

        for filepath in files_to_process:
            if not os.path.exists(filepath):
                continue

            fhash = self.pipeline._compute_file_hash(filepath)
            old_hash = existing_hashes.get(filepath)

            if old_hash == fhash:
                idx_info = self.file_index.get_file(filepath)
                if idx_info and idx_info.get("status") == "indexed":
                    continue

            result = self.process_file(filepath)
            if result:
                if old_hash:
                    updated_files += 1
                else:
                    new_files += 1
                new_chunks += result["chunks"]

        # 保存文件索引
        total_chunks = self.vectorstore.count()
        self.file_index.update_metadata(total_chunks)
        self.file_index.save()

        elapsed = time.time() - start_time
        result = {
            "new_files": new_files,
            "updated_files": updated_files,
            "deleted_files": deleted_files,
            "new_chunks": new_chunks,
            "total_chunks_after": total_chunks,
            "time_ms": int(elapsed * 1000),
        }
        if new_files or updated_files or deleted_files:
            log.info(f"增量更新完成: {result}")
        return result
