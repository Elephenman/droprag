"""DropRAG 查询增强模块（通用版）

提供:
1. 拼写纠错提示
2. 缩写展开
3. 查询扩展策略
4. 中英文双语扩展
"""

import re
from typing import List, Dict, Set, Optional
from dataclasses import dataclass


# 常见缩写表
COMMON_ABBREVIATIONS: Dict[str, List[str]] = {
    "ai": ["artificial intelligence", "人工智能"],
    "ml": ["machine learning", "机器学习"],
    "dl": ["deep learning", "深度学习"],
    "nlp": ["natural language processing", "自然语言处理"],
    "cv": ["computer vision", "计算机视觉"],
    "api": ["application programming interface"],
    "db": ["database", "数据库"],
    "ui": ["user interface", "用户界面"],
    "ux": ["user experience", "用户体验"],
    "k8s": ["kubernetes"],
    "devops": ["development operations"],
    "sre": ["site reliability engineering"],
    "qa": ["quality assurance", "质量保证"],
    "crm": ["customer relationship management"],
    "erp": ["enterprise resource planning"],
    "saas": ["software as a service"],
    "paas": ["platform as a service"],
    "iaas": ["infrastructure as a service"],
}


@dataclass
class QueryEnhanceConfig:
    expand_abbreviations: bool = True
    add_language_variants: bool = True
    max_expansions: int = 3
    min_term_length: int = 2


class QueryEnhancer:
    """通用查询增强器"""

    def __init__(self, config: Optional[QueryEnhanceConfig] = None):
        self.config = config or QueryEnhanceConfig()
        self._build_abbr_index()

    def _build_abbr_index(self):
        """构建缩写反向索引"""
        self.abbr_to_full: Dict[str, List[str]] = {}
        for abbr, expansions in COMMON_ABBREVIATIONS.items():
            self.abbr_to_full[abbr.lower()] = expansions

    def _tokenize(self, query: str) -> List[str]:
        parts = re.split(r'[\s,;，；]+', query.lower())
        return [p for p in parts if p]

    def expand_abbreviations(self, query: str) -> List[str]:
        """展开缩写"""
        if not self.config.expand_abbreviations:
            return [query]

        tokens = self._tokenize(query)
        expansions: Set[str] = set()

        for token in tokens:
            if len(token) < self.config.min_term_length:
                continue
            full_forms = self.abbr_to_full.get(token)
            if full_forms:
                for full in full_forms[:self.config.max_expansions]:
                    expansions.add(full)

        if not expansions:
            return [query]

        expanded = [query]
        for exp in list(expansions)[:3]:
            expanded.append(f"{query} {exp}")
        return expanded

    def add_language_variants(self, query: str) -> List[str]:
        """添加语言变体"""
        if not self.config.add_language_variants:
            return [query]

        variants = [query]
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in query)
        has_english = any(c.isascii() and c.isalpha() for c in query)

        if has_chinese and has_english:
            return variants  # 已经是混合的

        tokens = self._tokenize(query)
        for token in tokens:
            full_forms = self.abbr_to_full.get(token, [])
            for full in full_forms:
                full_has_chinese = any('\u4e00' <= c <= '\u9fff' for c in full)
                if has_chinese and not full_has_chinese:
                    variants.append(f"{query} {full}")
                elif not has_chinese and full_has_chinese:
                    variants.append(f"{query} {full}")

        return list(set(variants))[:4]

    def enhance(self, query: str) -> Dict:
        """增强查询"""
        tokens = self._tokenize(query)
        found_abbr = []

        for token in tokens:
            full_forms = self.abbr_to_full.get(token)
            if full_forms:
                found_abbr.append({
                    "token": token,
                    "expansions": full_forms[:3],
                })

        expanded = self.expand_abbreviations(query)
        if self.config.add_language_variants:
            variants = self.add_language_variants(query)
            expanded = list(set(expanded + variants))

        return {
            "original": query,
            "expanded": expanded[:5],
            "found_abbreviations": found_abbr,
            "strategy": "abbreviation_expansion" if found_abbr else "none",
        }


_default_enhancer: Optional[QueryEnhancer] = None


def get_enhancer() -> QueryEnhancer:
    global _default_enhancer
    if _default_enhancer is None:
        _default_enhancer = QueryEnhancer()
    return _default_enhancer


def enhance_query(query: str) -> Dict:
    return get_enhancer().enhance(query)
