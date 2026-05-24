"""DropRAG 行级分块器 - 表格数据"""

from typing import List
from droprag.chunker import ChunkerBase, Chunk, make_chunk_metadata
from droprag.loader import LoadedDocument
from droprag.config import ChunkTypeConfig


class RowChunker(ChunkerBase):
    """行级分块器 — 表格数据按行分块，每块附带表头"""

    file_types = ["xlsx", "csv"]

    def chunk(self, doc: LoadedDocument, cfg: ChunkTypeConfig) -> List[Chunk]:
        lines = doc.content.split("\n")
        if not lines:
            return []

        # 检测表头（第一行或第一个 [Sheet: xxx] 后的行）
        header = ""
        header_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("[Sheet:"):
                continue
            header = line.strip()
            header_idx = i
            break

        # 数据行
        data_lines = lines[header_idx + 1:]
        chunk_size = cfg.chunk_size  # 用作每块最大行数
        if chunk_size < 10:
            chunk_size = 50

        chunks = []
        current_batch = []
        batch_idx = 0

        for line in data_lines:
            if not line.strip():
                continue
            current_batch.append(line)

            if len(current_batch) >= chunk_size:
                # 每块附带表头
                block_content = header + "\n" + "\n".join(current_batch) if header else "\n".join(current_batch)
                meta = make_chunk_metadata(doc, batch_idx, 0, len(block_content))
                chunks.append(Chunk(content=block_content, metadata=meta))
                current_batch = []
                batch_idx += 1

        # 剩余行
        if current_batch:
            block_content = header + "\n" + "\n".join(current_batch) if header else "\n".join(current_batch)
            meta = make_chunk_metadata(doc, batch_idx, 0, len(block_content))
            chunks.append(Chunk(content=block_content, metadata=meta))

        # 更新 total_chunks
        for c in chunks:
            c.metadata["total_chunks"] = len(chunks)

        return chunks
