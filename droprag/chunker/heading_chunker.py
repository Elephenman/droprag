"""DropRAG 标题级分块器 - Markdown/RST/DOCX"""

from typing import List
from droprag.chunker import ChunkerBase, Chunk, split_by_separators, make_chunk_metadata
from droprag.loader import LoadedDocument
from droprag.config import ChunkTypeConfig


class HeadingChunker(ChunkerBase):
    """标题级分块器 — 按标题层级切分"""

    file_types = ["md", "rst", "docx"]

    def chunk(self, doc: LoadedDocument, cfg: ChunkTypeConfig) -> List[Chunk]:
        # 先按标题分隔符切
        heading_seps = ["\n## ", "\n### ", "\n#### ", "\n# "]
        raw_chunks = split_by_separators(doc.content, heading_seps + cfg.separators,
                                         cfg.chunk_size, cfg.chunk_overlap)
        chunks = []
        for i, text in enumerate(raw_chunks):
            if not text.strip():
                continue
            # 提取当前块标题
            heading = self._extract_heading(text) or doc.heading
            meta = make_chunk_metadata(doc, i, len(raw_chunks), len(text), heading)
            chunks.append(Chunk(content=text, metadata=meta))
        return chunks

    @staticmethod
    def _extract_heading(text: str) -> str:
        """提取文本块的标题"""
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("#"):
                return line.lstrip("#").strip()
        return ""
