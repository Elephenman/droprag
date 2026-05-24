"""DropRAG 上下文感知重排序模块

策略:
1. 关键词匹配密度加权
2. 标题/heading 匹配加分
3. 上下文连贯性（相邻 chunk 加分）
4. 多样性去重（同源文件限制）
"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class RerankConfig:
    keyword_density_weight: float = 0.25
    heading_match_weight: float = 0.35
    context_coherence_weight: float = 0.15
    diversity_penalty: float = 0.1
    max_same_source: int = 2
    base_score_scale: float = 10.0


def _tokenize(text: str) -> List[str]:
    tokens = []
    for word in re.findall(r'[a-zA-Z0-9_\-\.]+', text):
        tokens.append(word.lower())
    for seg in re.findall(r'[一-鿿]+', text):
        tokens.append(seg)
    return tokens


def _keyword_density_score(query_tokens: List[str], content: str) -> float:
    if not query_tokens:
        return 0.0
    content_lower = content.lower()
    hits = sum(1 for t in query_tokens if t in content_lower)
    return min(hits / len(query_tokens), 1.0)


def _heading_match_score(query_tokens: List[str], heading: str) -> float:
    if not heading:
        return 0.0
    heading_lower = heading.lower()
    hits = sum(1 for t in query_tokens if t in heading_lower)
    if hits == 0:
        return 0.0
    return 1.0 if hits >= len(query_tokens) else hits / len(query_tokens)


def _context_coherence_score(chunk_id: int, total_chunks: int,
                             source: str, results: List[Dict],
                             result_idx: int) -> float:
    if total_chunks <= 1:
        return 0.0
    score = 0.0
    for i, r in enumerate(results):
        if i == result_idx:
            continue
        r_source = r.get("source", r.get("metadata", {}).get("source", ""))
        r_chunk_id = r.get("chunk_id", r.get("metadata", {}).get("chunk_id", 0))
        if r_source == source and abs(r_chunk_id - chunk_id) <= 1:
            score += 0.5
    return min(score, 1.0)


def rerank(results: List[Dict], query: str,
           config: Optional[RerankConfig] = None) -> List[Dict]:
    if not results:
        return results

    cfg = config or RerankConfig()
    query_tokens = _tokenize(query)

    base_scores = []
    for r in results:
        base = r.get("rrf_score", r.get("score", 0.5))
        if base <= 0.1:
            base = base * cfg.base_score_scale
        base_scores.append(base)

    max_bonus = cfg.keyword_density_weight + cfg.heading_match_weight + cfg.context_coherence_weight
    rerank_scores = []
    source_count: Dict[str, int] = {}

    for i, r in enumerate(results):
        content = r.get("content", "")
        meta = r.get("metadata", {})
        heading = r.get("heading", meta.get("heading", ""))
        source = r.get("source", meta.get("source", ""))
        chunk_id = r.get("chunk_id", meta.get("chunk_id", 0))
        total_chunks = r.get("total_chunks", meta.get("total_chunks", 0))

        kd = _keyword_density_score(query_tokens, content)
        hm = _heading_match_score(query_tokens, heading)
        cc = _context_coherence_score(chunk_id, total_chunks, source, results, i)
        bonus = min(kd * cfg.keyword_density_weight + hm * cfg.heading_match_weight + cc * cfg.context_coherence_weight, max_bonus)

        source_count[source] = source_count.get(source, 0) + 1
        if source_count[source] > cfg.max_same_source:
            penalty = cfg.diversity_penalty * (source_count[source] - cfg.max_same_source)
            bonus = max(0, bonus - penalty)

        final_score = base_scores[i] + bonus
        rerank_scores.append({
            "final_score": final_score,
            "base_score": round(base_scores[i], 4),
            "keyword_density": round(kd, 3),
            "heading_match": round(hm, 3),
            "context_coherence": round(cc, 3),
        })

    indexed = list(range(len(results)))
    indexed.sort(key=lambda i: rerank_scores[i]["final_score"], reverse=True)

    reranked = []
    for i in indexed:
        r = results[i].copy()
        r["rerank_score"] = round(rerank_scores[i]["final_score"], 4)
        r["rerank_details"] = {
            "keyword_density": rerank_scores[i]["keyword_density"],
            "heading_match": rerank_scores[i]["heading_match"],
            "context_coherence": rerank_scores[i]["context_coherence"],
        }
        reranked.append(r)

    return reranked
