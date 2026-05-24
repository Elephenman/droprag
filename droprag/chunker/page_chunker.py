"""DropRAG 页级分块器 - PDF"""

from typing import List
from droprag.chunker import ChunkerBase, Chunk, split_by_separators, make_chunk_metadata
from droprag.loader import LoadedDocument
from droprag.config import ChunkTypeConfig


class PageChunker(ChunkerBase):
    """页级分块器 — PDF 文本先按段落/语义切分"""

    file_types = ["pdf"]

    def chunk(self, doc: LoadedDocument, cfg: ChunkTypeConfig) -> List[Chunk]:
        raw_chunks = split_by_separators(doc.content, cfg.separators, cfg.chunk_size, cfg.chunk_overlap)
        chunks = []
        for i, text in enumerate(raw_chunks):
            if not text.strip():
                continue
            meta = make_chunk_metadata(doc, i, len(raw_chunks), len(text))
            chunks.append(Chunk(content=text, metadata=meta))
        return chunks
