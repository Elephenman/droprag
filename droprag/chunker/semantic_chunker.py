"""DropRAG 通用语义分块器 - 递归分隔符切分"""

from typing import List
from droprag.chunker import ChunkerBase, Chunk, split_by_separators, make_chunk_metadata
from droprag.loader import LoadedDocument
from droprag.config import ChunkTypeConfig


class SemanticChunker(ChunkerBase):
    """通用语义分块器（递归分隔符切分），作为默认分块器"""

    file_types = ["default", "txt", "log", "epub"]

    def chunk(self, doc: LoadedDocument, cfg: ChunkTypeConfig) -> List[Chunk]:
        raw_chunks = split_by_separators(doc.content, cfg.separators, cfg.chunk_size, cfg.chunk_overlap)
        chunks = []
        for i, text in enumerate(raw_chunks):
            if not text.strip():
                continue
            meta = make_chunk_metadata(doc, i, len(raw_chunks), len(text))
            chunks.append(Chunk(content=text, metadata=meta))
        return chunks
