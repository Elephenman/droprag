"""DropRAG 幻灯片级分块器 - PPTX"""

from typing import List
from droprag.chunker import ChunkerBase, Chunk, make_chunk_metadata
from droprag.loader import LoadedDocument
from droprag.config import ChunkTypeConfig


class SlideChunker(ChunkerBase):
    """幻灯片级分块器 — 每页幻灯片作为一个独立块"""

    file_types = ["pptx"]

    def chunk(self, doc: LoadedDocument, cfg: ChunkTypeConfig) -> List[Chunk]:
        # PPTX 在 loader 阶段已按 "--- 幻灯片 N ---" 分隔
        slides = doc.content.split("--- 幻灯片 ")
        chunks = []

        for i, slide_text in enumerate(slides):
            text = slide_text.strip()
            if not text:
                continue
            # 补回分隔符
            if i > 0:
                text = "--- 幻灯片 " + text

            # 如果单页过大，继续切分
            if len(text) > cfg.chunk_size:
                sub_chunks = self._split_slide(text, cfg)
                for j, sub in enumerate(sub_chunks):
                    meta = make_chunk_metadata(doc, len(chunks), 0, len(sub))
                    meta["slide_index"] = i
                    chunks.append(Chunk(content=sub, metadata=meta))
            else:
                meta = make_chunk_metadata(doc, len(chunks), 0, len(text))
                meta["slide_index"] = i
                chunks.append(Chunk(content=text, metadata=meta))

        # 更新 total_chunks
        for c in chunks:
            c.metadata["total_chunks"] = len(chunks)

        return chunks

    @staticmethod
    def _split_slide(text: str, cfg: ChunkTypeConfig) -> List[str]:
        """对过大的幻灯片文本进行二次切分"""
        parts = text.split("\n\n")
        chunks = []
        current = ""
        for part in parts:
            candidate = current + "\n\n" + part if current else part
            if len(candidate) <= cfg.chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current.strip())
                current = part
        if current.strip():
            chunks.append(current.strip())
        return chunks
