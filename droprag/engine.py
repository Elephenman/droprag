"""DropRAG FastAPI Engine 服务

v0.1.0 - 通用版
- sqlite-vec 向量存储
- 多后端 Embedding (auto/local/onnx/api)
- 热文件夹监控
- SQLite 持久化缓存
- API Key 认证
- SSE 事件推送
- 15+ 文件类型支持
"""

import os
import time
import json
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from droprag.config import load_config, DropRAGConfig
from droprag.embedder import create_embedder, BaseEmbedder
from droprag.vectorstore import VectorStore
from droprag.metadata import MetadataDB
from droprag.search_log import SearchLogDB
from droprag.indexer import Indexer
from droprag.cache import DropRAGCache
from droprag.reranker import rerank
from droprag.query_enhancer import enhance_query
from droprag.quality_feedback import get_search_hints, generate_quality_report
from droprag.classifier import classify_file, get_classifier
from droprag import watcher
from droprag.logging import setup_logging, get_logger

log = get_logger(__name__)

# ===== 全局状态 =====
_config: Optional[DropRAGConfig] = None
_embedder: Optional[BaseEmbedder] = None
_vectorstore: Optional[VectorStore] = None
_metadata_db: Optional[MetadataDB] = None
_search_log: Optional[SearchLogDB] = None
_cache: Optional[DropRAGCache] = None
_indexer: Optional[Indexer] = None
_start_time: float = 0
_event_loop: Optional[asyncio.AbstractEventLoop] = None


# ===== 请求模型 =====
class SearchRequest(BaseModel):
    query: str
    level: int = 1
    top_k: Optional[int] = None
    category: Optional[str] = None
    min_score: float = 0.3


class SearchKwRequest(BaseModel):
    keyword: str
    file_type: Optional[str] = None
    max_results: int = 10


class EnhanceRequest(BaseModel):
    query: str


class CacheClearRequest(BaseModel):
    query_only: bool = False
    force_rebuild: bool = False


class HybridSearchRequest(BaseModel):
    query: str
    level: int = 1
    top_k: Optional[int] = None
    category: Optional[str] = None
    min_score: float = 0.3
    semantic_weight: float = 0.7
    keyword_weight: float = 0.3


class UpdateRequest(BaseModel):
    force_rebuild: bool = False


# ===== API Key 认证 =====
async def verify_api_key(request: Request):
    if _config is None or _config.engine.api_key is None:
        return
    key = request.headers.get("X-API-Key", "")
    if key != _config.engine.api_key:
        raise HTTPException(401, "Invalid API Key")


# ===== Lifespan =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _embedder, _vectorstore, _metadata_db, _search_log, _cache, _indexer, _start_time, _event_loop

    _start_time = time.time()
    _event_loop = asyncio.get_event_loop()

    config_path = os.environ.get("DROPRAG_CONFIG", "config.yaml")
    for try_path in [config_path, os.path.join(os.path.dirname(__file__), "..", "config.yaml")]:
        if os.path.exists(try_path):
            _config = load_config(try_path)
            break
    if _config is None:
        _config = DropRAGConfig()

    setup_logging(_config.logging.level, _config.logging.file)
    log.info(f"DropRAG Engine 启动中...")
    log.info(f"知识库路径: {_config.knowledge_base.path}")

    data_dir = os.path.abspath(_config.data.dir)
    os.makedirs(data_dir, exist_ok=True)

    # 缓存
    if _config.cache.enabled:
        cache_path = os.path.join(data_dir, "cache.db")
        _cache = DropRAGCache(_config.cache, db_path=cache_path)

    # Embedding
    _embedder = create_embedder(_config.embedding)
    if _cache:
        _embedder.set_cache(_cache)

    # 向量库
    db_path = os.path.join(data_dir, "droprag.db")
    _vectorstore = VectorStore(db_path, _config.embedding.dimension)

    # 元数据
    meta_path = os.path.join(data_dir, "metadata.db")
    _metadata_db = MetadataDB(meta_path)

    # 检索日志
    log_path = os.path.join(data_dir, "search_logs.db")
    _search_log = SearchLogDB(log_path)

    # 索引器
    _indexer = Indexer(_config, _embedder, _vectorstore, _metadata_db)

    # 首次运行
    if _vectorstore.count() == 0:
        log.info("首次运行，开始构建向量库...")
        result = _indexer.build_all()
        log.info(f"构建完成: {result}")

    chunk_count = _vectorstore.count()
    log.info(f"DropRAG Engine 启动完成！({chunk_count} 个文本块)")

    # 热文件夹监控
    if _config.knowledge_base.watch.enabled and _config.knowledge_base.path:
        watch_paths = [_config.knowledge_base.path]
        if _config.knowledge_base.watch.extra_dirs:
            watch_paths.extend(_config.knowledge_base.watch.extra_dirs)

        def on_file_change(changed_files: List[str]):
            try:
                future = asyncio.run_coroutine_threadsafe(
                    _async_incremental_update(changed_files), _event_loop
                )
                future.result(timeout=30)
            except Exception as e:
                log.error(f"增量更新失败: {e}")

        ignore_set = set(_config.knowledge_base.watch.ignore) if _config.knowledge_base.watch.ignore else None
        success = watcher.start_watching(
            watch_paths=watch_paths,
            update_callback=on_file_change,
            ignore_patterns=ignore_set,
            debounce_seconds=_config.knowledge_base.watch.debounce_seconds,
        )
        if success:
            log.info("文件监控已启动（热文件夹模式）")

    yield

    watcher.stop_watching()
    for db in [_metadata_db, _search_log, _vectorstore, _cache]:
        if db:
            db.close()
    log.info("DropRAG Engine 已停止")


async def _async_incremental_update(changed_files: List[str]):
    if _indexer is None:
        return
    result = _indexer.incremental_update(changed_files=changed_files)
    await watcher.publish_event({
        "type": "index_updated",
        "data": result,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })


# ===== 应用创建 =====
app = FastAPI(title="DropRAG Engine", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== API 端点 =====

@app.get("/health")
async def health():
    return {
        "status": "running",
        "version": "0.1.0",
        "uptime_seconds": int(time.time() - _start_time),
    }


@app.post("/search")
async def search(req: SearchRequest, _auth=Depends(verify_api_key)):
    """语义检索"""
    if _vectorstore is None or _embedder is None:
        raise HTTPException(503, "Engine 未就绪")

    start = time.time()
    level = req.level
    level_cfg = {
        1: _config.retrieval.level_1,
        2: _config.retrieval.level_2,
        3: _config.retrieval.level_3,
    }.get(level, _config.retrieval.level_1)

    top_k = req.top_k or level_cfg.top_k
    max_chars = level_cfg.max_chars_per_chunk

    if _cache:
        cached = _cache.get_query_result(req.query, level, req.category, top_k, req.min_score)
        if cached:
            cached["cache_hit"] = True
            return cached

    query_embedding = _embedder.encode_single(req.query)
    results = _vectorstore.search(query_embedding=query_embedding, top_k=top_k * 2,
                                   category=req.category, min_score=req.min_score)
    results = rerank(results, req.query)
    results = results[:top_k]

    for r in results:
        if max_chars and level != 3 and len(r["content"]) > max_chars:
            r["content"] = r["content"][:max_chars] + "...(截断)"
        meta = r.pop("metadata", {})
        r["source"] = meta.get("filename", "")
        r["category"] = meta.get("category", "")
        r["heading"] = meta.get("heading", "")
        r["chunk_id"] = meta.get("chunk_id", 0)
        r["total_chunks"] = meta.get("total_chunks", 0)

    elapsed_ms = int((time.time() - start) * 1000)
    scores = [r["score"] for r in results]
    avg_score = sum(scores) / len(scores) if scores else 0

    if _search_log:
        sources = [r.get("source", "") for r in results]
        _search_log.log_search(
            query=req.query, level=level, category=req.category,
            top_k=top_k, results_count=len(results),
            avg_score=avg_score, min_score=min(scores) if scores else 0,
            max_score=max(scores) if scores else 0,
            time_ms=elapsed_ms, sources=sources,
        )

    response = {
        "query": req.query, "level": level, "results": results,
        "total_searched": _vectorstore.count(), "time_ms": elapsed_ms,
        "cache_hit": False, "quality_hints": get_search_hints(req.query, results),
        "stats": {"avg_score": round(avg_score, 4), "result_count": len(results)},
    }

    if _cache:
        _cache.set_query_result(req.query, level, req.category, top_k, req.min_score, response)
    return response


@app.post("/search_kw")
async def search_keyword(req: SearchKwRequest, _auth=Depends(verify_api_key)):
    if _vectorstore is None:
        raise HTTPException(503, "Engine 未就绪")
    results = _vectorstore.search_keyword(keyword=req.keyword, top_k=req.max_results, file_type=req.file_type)
    return {"keyword": req.keyword, "results": results, "total_matches": len(results)}


@app.post("/hybrid")
async def hybrid_search(req: HybridSearchRequest, _auth=Depends(verify_api_key)):
    if _vectorstore is None or _embedder is None:
        raise HTTPException(503, "Engine 未就绪")

    start = time.time()
    level_cfg = {
        1: _config.retrieval.level_1,
        2: _config.retrieval.level_2,
        3: _config.retrieval.level_3,
    }.get(req.level, _config.retrieval.level_1)
    top_k = req.top_k or level_cfg.top_k

    query_embedding = _embedder.encode_single(req.query)
    results = _vectorstore.hybrid_search(
        query_embedding=query_embedding, keyword=req.query,
        top_k=top_k * 2, category=req.category, min_score=req.min_score,
        semantic_weight=req.semantic_weight, keyword_weight=req.keyword_weight,
    )
    results = rerank(results, req.query)
    results = results[:top_k]

    for r in results:
        meta = r.pop("metadata", {})
        r["source"] = meta.get("filename", "")
        r["category"] = meta.get("category", "")
        r["heading"] = meta.get("heading", "")

    elapsed_ms = int((time.time() - start) * 1000)
    return {
        "query": req.query, "level": req.level, "mode": "hybrid",
        "results": results, "total_searched": _vectorstore.count(),
        "time_ms": elapsed_ms,
    }


@app.get("/status")
async def status(_auth=Depends(verify_api_key)):
    if _metadata_db is None:
        raise HTTPException(503, "Engine 未就绪")
    total_stats = _metadata_db.get_total_stats()
    cat_stats = _metadata_db.get_category_stats()
    watch_status = "active" if watcher.is_watching() else "inactive"

    data_dir = os.path.abspath(_config.data.dir)
    db_size = 0
    for root, dirs, files in os.walk(data_dir):
        for f in files:
            db_size += os.path.getsize(os.path.join(root, f))

    return {
        "total_documents": total_stats["total_documents"],
        "total_chunks": _vectorstore.count(),
        "db_size_mb": round(db_size / (1024 * 1024), 1),
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "embedding_model": _config.embedding.model,
        "embedding_provider": _config.embedding.provider,
        "categories": cat_stats,
        "engine_status": "running",
        "uptime_seconds": int(time.time() - _start_time),
        "watch_status": watch_status,
        "cache": _cache.get_stats() if _cache else None,
    }


@app.post("/update")
async def update(req: UpdateRequest, _auth=Depends(verify_api_key)):
    if _indexer is None:
        raise HTTPException(503, "Engine 未就绪")
    if req.force_rebuild:
        return _indexer.build_all()
    return _indexer.incremental_update()


@app.post("/rebuild")
async def rebuild(_auth=Depends(verify_api_key)):
    if _indexer is None:
        raise HTTPException(503, "Engine 未就绪")
    return _indexer.build_all()


@app.post("/cache/clear")
async def cache_clear(req: CacheClearRequest = CacheClearRequest(), _auth=Depends(verify_api_key)):
    if _cache is None:
        return {"status": "no_cache"}
    if req.query_only:
        _cache.clear_query_cache()
        return {"status": "ok", "cleared": "query_cache"}
    _cache.clear_query_cache()
    _cache.clear_embedding_cache()
    return {"status": "ok", "cleared": "all"}


@app.post("/enhance")
async def enhance(req: EnhanceRequest, _auth=Depends(verify_api_key)):
    return enhance_query(req.query)


@app.get("/classify")
async def classify(filepath: str, _auth=Depends(verify_api_key)):
    """文件分类测试"""
    return {"filepath": filepath, "category": classify_file(filepath)}


@app.get("/quality/report")
async def quality_report(days: int = 7, _auth=Depends(verify_api_key)):
    if _search_log is None:
        raise HTTPException(503, "Engine 未就绪")
    return generate_quality_report(_search_log, days)


@app.get("/events")
async def events(_auth=Depends(verify_api_key)):
    """SSE 事件流"""
    queue = watcher.subscribe_events()

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            watcher.unsubscribe_events(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def main():
    import uvicorn
    config_path = os.environ.get("DROPRAG_CONFIG", "config.yaml")
    global _config
    _config = load_config(config_path)
    uvicorn.run(app, host=_config.engine.host, port=_config.engine.port)
