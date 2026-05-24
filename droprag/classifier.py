"""DropRAG 文件自动分类器

基于扩展名 + 内容嗅探的智能文件分类。
支持 10 大分类，覆盖 15+ 种文件类型。
"""

import os
from typing import Optional, Dict, List
from droprag.logging import get_logger

log = get_logger(__name__)


class FileClassifier:
    """基于扩展名 + 内容嗅探的智能文件分类"""

    # 分类规则（优先级从高到低）
    CATEGORY_RULES: Dict[str, Dict] = {
        "academic_paper": {
            "extensions": [".pdf"],
            "content_hints": ["abstract", "introduction", "references", "doi",
                              "摘要", "引言", "参考文献"],
            "description": "学术论文",
        },
        "office_doc": {
            "extensions": [".docx", ".doc"],
            "description": "Office 文档",
        },
        "spreadsheet": {
            "extensions": [".xlsx", ".xls", ".csv"],
            "description": "表格数据",
        },
        "presentation": {
            "extensions": [".pptx", ".ppt"],
            "description": "演示文稿",
        },
        "code": {
            "extensions": [".py", ".js", ".ts", ".r", ".R", ".java", ".cpp",
                           ".c", ".go", ".rs", ".rb", ".php", ".swift", ".kt"],
            "description": "代码文件",
        },
        "notebook": {
            "extensions": [".ipynb"],
            "description": "Jupyter 笔记本",
        },
        "markup": {
            "extensions": [".md", ".rst", ".html", ".htm"],
            "description": "标记文档",
        },
        "data": {
            "extensions": [".json", ".jsonl", ".xml", ".yaml", ".yml", ".toml"],
            "description": "结构化数据",
        },
        "text": {
            "extensions": [".txt", ".log"],
            "description": "纯文本",
        },
        "image": {
            "extensions": [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"],
            "description": "图片",
        },
        "ebook": {
            "extensions": [".epub"],
            "description": "电子书",
        },
    }

    # 扩展名 → 分类 快速索引
    _ext_index: Dict[str, str] = {}

    def __init__(self):
        self._build_ext_index()

    def _build_ext_index(self):
        """构建扩展名快速索引"""
        for category, rule in self.CATEGORY_RULES.items():
            for ext in rule["extensions"]:
                self._ext_index[ext.lower()] = category

    def classify(self, filepath: str) -> str:
        """根据文件路径分类

        Args:
            filepath: 文件路径

        Returns:
            分类名称（如 academic_paper / spreadsheet / code...）
        """
        ext = os.path.splitext(filepath)[1].lower()

        # 1. 扩展名匹配
        category = self._ext_index.get(ext)
        if category is None:
            return "other"

        # 2. 内容嗅探（仅对特定类型做深度检测）
        if category == "academic_paper" and os.path.exists(filepath):
            if not self._is_academic_paper(filepath):
                # PDF 但不是论文 → 降级为 office_doc
                return "office_doc"

        return category

    def _is_academic_paper(self, filepath: str) -> bool:
        """内容嗅探：检测 PDF 是否为学术论文"""
        try:
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            # 只读前3页
            text = ""
            for page in reader.pages[:3]:
                page_text = page.extract_text()
                if page_text:
                    text += page_text.lower()

            hints = self.CATEGORY_RULES["academic_paper"].get("content_hints", [])
            hits = sum(1 for hint in hints if hint.lower() in text)
            # 至少匹配2个关键词才认为是论文
            return hits >= 2
        except Exception:
            # 读取失败，保守认为是论文（按扩展名走）
            return True

    def get_category_for_ext(self, ext: str) -> str:
        """获取扩展名对应的分类"""
        return self._ext_index.get(ext.lower(), "other")

    def get_all_supported_extensions(self) -> List[str]:
        """获取所有支持的扩展名"""
        return list(self._ext_index.keys())

    def get_category_description(self, category: str) -> str:
        """获取分类描述"""
        rule = self.CATEGORY_RULES.get(category, {})
        return rule.get("description", category)


# 全局实例
_classifier: Optional[FileClassifier] = None


def get_classifier() -> FileClassifier:
    """获取全局分类器实例"""
    global _classifier
    if _classifier is None:
        _classifier = FileClassifier()
    return _classifier


def classify_file(filepath: str) -> str:
    """快捷函数：分类文件"""
    return get_classifier().classify(filepath)
