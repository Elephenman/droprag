"""DropRAG 检索质量反馈系统（通用版）"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class QualityThresholds:
    low_score: float = 0.4
    very_low_score: float = 0.3
    min_results: int = 2
    min_keyword_hits: int = 1


def analyze_quality(query: str, results: List[Dict],
                    thresholds: Optional[QualityThresholds] = None) -> Dict:
    if thresholds is None:
        thresholds = QualityThresholds()

    if not results:
        return {
            "quality": "poor", "score": 0.0,
            "issues": ["no_results"],
            "suggestions": ["未找到相关结果，尝试使用不同关键词", "检查拼写是否正确", "使用更通用的术语"],
        }

    scores = [r.get("score", 0) for r in results]
    avg_score = sum(scores) / len(scores)
    min_score = min(scores)
    issues = []
    suggestions = []

    if min_score < thresholds.very_low_score:
        issues.append("very_low_score")
        suggestions.extend(["尝试使用更具体的关键词", "检查是否存在拼写错误"])
    elif min_score < thresholds.low_score:
        issues.append("low_score")
        suggestions.append("结果相关性较低，建议尝试不同关键词")

    if len(results) < thresholds.min_results:
        issues.append("few_results")
        suggestions.append("结果较少，尝试放宽检索条件")

    quality = "good" if not issues else ("poor" if len(issues) >= 2 or "very_low_score" in issues else "fair")

    return {
        "quality": quality, "score": round(avg_score, 4),
        "min_score": round(min_score, 4), "result_count": len(results),
        "issues": issues, "suggestions": list(set(suggestions))[:3],
    }


def _extract_terms(query: str) -> List[str]:
    terms = [w.lower() for w in re.findall(r'[a-zA-Z][a-zA-Z0-9_-]*', query)]
    terms.extend(re.findall(r'[\u4e00-\u9fff]{2,}', query))
    return terms


def generate_quality_report(search_logs_db, days: int = 7) -> Dict:
    try:
        recent = search_logs_db.get_recent_stats(days) if hasattr(search_logs_db, 'get_recent_stats') else {}
        low_score = search_logs_db.get_low_score_queries(days, threshold=0.4) if hasattr(search_logs_db, 'get_low_score_queries') else []

        avg_similarity = recent.get('avg_similarity', 0)
        total = recent.get('total_searches', 0)

        if avg_similarity >= 0.7:
            overall_quality = "excellent"
        elif avg_similarity >= 0.6:
            overall_quality = "good"
        elif avg_similarity >= 0.5:
            overall_quality = "fair"
        else:
            overall_quality = "poor"

        return {
            "period_days": days, "overall_quality": overall_quality,
            "total_searches": total, "avg_similarity": avg_similarity,
            "low_score_rate": round(recent.get('low_score_count', 0) / max(total, 1), 3),
            "problematic_queries": low_score[:5],
        }
    except Exception as e:
        return {"error": str(e), "period_days": days}


def get_search_hints(query: str, results: List[Dict]) -> Dict:
    quality = analyze_quality(query, results)
    hints = {"quality_level": quality["quality"], "quality_score": quality["score"]}
    if quality["issues"]:
        hints["issues"] = quality["issues"]
        hints["suggestions"] = quality["suggestions"]
    return hints
