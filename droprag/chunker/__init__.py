"""DropRAG 插件化分块器系统

ChunkerBase 基类 + ChunkerRegistry 自动发现注册。
每个 Chunker 声明支持的 file_types，Registry 自动匹配。
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Type

from droprag.loader import LoadedDocument
from droprag.config import ChunkTypeConfig
from droprag.logging import get_logger

log = get_logger(__name__)


@dataclass
class Chunk:
    """分块结果"""
    content: str
    metadata: Dict[str, Any]


class ChunkerBase:
    """分块器基类"""

    # 子类声明支持的 file_type 列表
    file_types: List[str] = []

    def chunk(self, doc: LoadedDocument, cfg: ChunkTypeConfig) -> List[Chunk]:
        """分块文档"""
        raise NotImplementedError


# ── 注册表 ──

_chunkers: Dict[str, ChunkerBase] = {}
_chunker_classes: List[Type[ChunkerBase]] = []


def register_chunker(chunker_class: Type[ChunkerBase]):
    """注册一个 Chunker 类"""
    _chunker_classes.append(chunker_class)
    instance = chunker_class()
    for ft in chunker_class.file_types:
        _chunkers[ft] = instance
    log.debug(f"注册 Chunker: {chunker_class.__name__} → {chunker_class.file_types}")


def get_chunker(file_type: str) -> Optional[ChunkerBase]:
    """根据 file_type 获取 Chunker"""
    return _chunkers.get(file_type)


def chunk_document(doc: LoadedDocument, cfg: ChunkTypeConfig = None,
                   default_cfg: ChunkTypeConfig = None) -> List[Chunk]:
    """根据文件类型自动选择分块器"""
    chunker = get_chunker(doc.file_type)
    if chunker is None:
        chunker = get_chunker("default")
    if chunker is None:
        return []

    actual_cfg = cfg or default_cfg or ChunkTypeConfig()
    return chunker.chunk(doc, actual_cfg)


def chunk_all_documents(docs: List[LoadedDocument], default_cfg: ChunkTypeConfig = None) -> List[Chunk]:
    """批量分块"""
    all_chunks = []
    for doc in docs:
        chunks = chunk_document(doc, default_cfg=default_cfg)
        all_chunks.extend(chunks)
    log.info(f"分块完成: {len(docs)} 文档 → {len(all_chunks)} 个文本块")
    return all_chunks


# ── 通用分块辅助函数 ──

def split_by_separators(text: str, separators: list, chunk_size: int, chunk_overlap: int) -> List[str]:
    """按分隔符递归切分文本"""
    if len(text) <= chunk_size:
        return [text]

    for sep in separators:
        if sep in text:
            parts = text.split(sep)
            chunks = []
            current = ""
            for part in parts:
                candidate = current + sep + part if current else part
                if len(candidate) <= chunk_size:
                    current = candidate
                else:
                    if current:
                        chunks.append(current.strip())
                    if len(part) > chunk_size:
                        for i in range(0, len(part), chunk_size - chunk_overlap):
                            sub = part[i:i + chunk_size]
                            if sub.strip():
                                chunks.append(sub.strip())
                    current = part
            if current.strip():
                chunks.append(current.strip())
            return chunks

    # 没有分隔符能切，按字符硬切
    chunks = []
    for i in range(0, len(text), chunk_size - chunk_overlap):
        sub = text[i:i + chunk_size]
        if sub.strip():
            chunks.append(sub.strip())
    return chunks


def add_overlap(chunks: List[str], overlap: int) -> List[str]:
    """为相邻块添加重叠内容"""
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    result = []
    for i, chunk in enumerate(chunks):
        if i > 0 and overlap > 0:
            prev_tail = chunks[i - 1][-overlap:]
            result.append(prev_tail + chunk)
        else:
            result.append(chunk)
    return result


def make_chunk_metadata(doc: LoadedDocument, chunk_idx: int, total: int,
                        char_count: int, heading: str = "") -> Dict[str, Any]:
    """构造通用 chunk metadata"""
    return {
        "source": doc.source,
        "filename": doc.filename,
        "category": doc.category,
        "file_type": doc.file_type,
        "chunk_id": chunk_idx,
        "total_chunks": total,
        "heading": heading or doc.heading,
        "folder": doc.folder,
        "subfolder": doc.subfolder,
        "char_count": char_count,
    }


# ── 自动发现 ──

def discover_chunkers():
    """自动发现并注册所有 Chunker"""
    from droprag.chunker.semantic_chunker import SemanticChunker
    register_chunker(SemanticChunker)

    from droprag.chunker.heading_chunker import HeadingChunker
    register_chunker(HeadingChunker)

    from droprag.chunker.row_chunker import RowChunker
    register_chunker(RowChunker)

    from droprag.chunker.slide_chunker import SlideChunker
    register_chunker(SlideChunker)

    from droprag.chunker.page_chunker import PageChunker
    register_chunker(PageChunker)

    from droprag.chunker.function_chunker import FunctionChunker
    register_chunker(FunctionChunker)

    log.info(f"Chunker 注册完成: {len(_chunkers)} 种文件类型")


# 模块加载时自动发现
try:
    discover_chunkers()
except Exception:
    pass
