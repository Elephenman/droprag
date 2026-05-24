"""DropRAG 统一处理管线

串联: Classify → Clean → Load → Chunk → Embed → Store
"""

import os
import time
from typing import List, Dict, Optional

from droprag.classifier import FileClassifier, classify_file
from droprag.cleaner import CleanerPipeline
from droprag.loader import load_file, get_supported_extensions, LoadedDocument
from droprag.chunker import chunk_document, Chunk
from droprag.embedder import BaseEmbedder
from droprag.vectorstore import VectorStore
from droprag.metadata import MetadataDB
from droprag.config import DropRAGConfig, ChunkTypeConfig
from droprag.logging import get_logger

log = get_logger(__name__)


class Pipeline:
    """统一处理管线: Classify → Clean → Load → Chunk → Embed → Store"""

    def __init__(self, config: DropRAGConfig, embedder: BaseEmbedder,
                 vectorstore: VectorStore, metadata_db: MetadataDB):
        self.config = config
        self.embedder = embedder
        self.vectorstore = vectorstore
        self.metadata_db = metadata_db

        self.classifier = FileClassifier()
        self.cleaner = CleanerPipeline(enabled=config.pipeline.enable_cleaning)

    def process_file(self, filepath: str) -> Optional[Dict]:
        """处理单个文件: 分类→清洗→加载→分块→编码→存储

        Returns:
            处理结果 {"chunks": int, "category": str, "hash": str} 或 None
        """
        if not os.path.exists(filepath):
            return None

        # 文件大小检查
        file_size = os.path.getsize(filepath)
        max_size = self.config.pipeline.max_file_size_mb * 1024 * 1024
        if file_size > max_size:
            log.warning(f"文件过大，跳过: {filepath} ({file_size / 1024 / 1024:.1f}MB > {self.config.pipeline.max_file_size_mb}MB)")
            return None

        try:
            # 1. Classify
            category = self.classifier.classify(filepath) if self.config.pipeline.enable_classification else ""

            # 2. Load
            kb_path = self.config.knowledge_base.path
            doc = load_file(filepath, kb_path, category=category)
            if doc is None:
                return None

            # 填充分类
            if not doc.category:
                doc.category = category

            # 3. Clean
            doc = self.cleaner.clean(doc)

            # 4. Chunk
            chunking_cfg = self._get_chunk_config(doc.file_type)
            chunks = chunk_document(doc, cfg=chunking_cfg)
            if not chunks:
                return None

            # 填充分类
            for c in chunks:
                if not c.metadata.get("category"):
                    c.metadata["category"] = category

            # 5. 删除旧数据
            self.vectorstore.delete_by_source(filepath)

            # 6. Embed
            texts = [c.content for c in chunks]
            embeddings = self.embedder.encode(texts)

            # 7. Store
            vec_chunks = []
            for chunk, emb in zip(chunks, embeddings):
                chunk_id = f"{chunk.metadata['source']}__{chunk.metadata['chunk_id']}"
                vec_chunks.append({
                    "id": chunk_id,
                    "content": chunk.content,
                    "embedding": emb,
                    "metadata": chunk.metadata,
                })
            self.vectorstore.add(vec_chunks)

            # 8. 更新元数据
            fhash = self._compute_file_hash(filepath)
            self.metadata_db.upsert_file(
                source=doc.source, filename=doc.filename, category=category,
                file_type=doc.file_type, folder=doc.folder, subfolder=doc.subfolder,
                file_size=doc.file_size, file_mtime=doc.file_mtime,
                chunk_count=len(chunks),
                char_count=sum(c.metadata.get("char_count", 0) for c in chunks),
                file_hash=fhash,
            )

            return {"chunks": len(chunks), "category": category, "hash": fhash}

        except Exception as e:
            log.error(f"处理文件失败 {filepath}: {e}")
            return None

    def _get_chunk_config(self, file_type: str) -> ChunkTypeConfig:
        """根据文件类型获取分块配置"""
        cfg = self.config.chunking
        type_map = {
            "md": cfg.markdown, "rst": cfg.markdown,
            "pdf": cfg.pdf,
            "xlsx": cfg.spreadsheet, "csv": cfg.spreadsheet,
            "pptx": cfg.presentation,
            "python": cfg.code, "javascript": cfg.code, "typescript": cfg.code,
            "r": cfg.code, "java": cfg.code, "cpp": cfg.code,
        }
        return type_map.get(file_type, cfg.default)

    @staticmethod
    def _compute_file_hash(filepath: str) -> str:
        """计算文件 SHA256 哈希"""
        import hashlib
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                sha256.update(block)
        return sha256.hexdigest()

    def scan_files(self, kb_path: str) -> List[str]:
        """扫描知识库目录，返回所有支持的文件路径"""
        supported = set(get_supported_extensions())
        ignore = set(self.config.knowledge_base.ignore or [])
        files = []

        for root, dirs, filenames in os.walk(kb_path):
            dirs[:] = [d for d in dirs if d not in ignore and not d.startswith(".")]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                ext = os.path.splitext(fn)[1].lower()
                if ext in supported:
                    files.append(os.path.join(root, fn))

        return sorted(files)
