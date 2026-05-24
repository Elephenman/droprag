"""DropRAG MarkItDown 统一转换加载器

微软 MarkItDown 引擎：将 PDF/DOCX/PPTX/XLSX/HTML/EPUB/Image/Audio 等
文件统一转换为 Markdown，作为 DropRAG 的首选文档转换引擎。

优先级：MarkItDown → 原有 Loader（降级回退）
"""

import os
from typing import Optional, List

from droprag.loader import LoaderBase, LoadedDocument, _get_folder_info, _get_file_mtime
from droprag.logging import get_logger

log = get_logger(__name__)

# MarkItDown 支持且值得优先使用的格式
MARKITDOWN_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".epub",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp",
    ".wav", ".mp3",
    ".msg",  # Outlook
}


class MarkItDownLoader(LoaderBase):
    """基于微软 MarkItDown 的统一文档转换加载器

    将各种文件格式统一转为 Markdown，保留文档结构（标题、表格、列表等），
    专为 LLM/RAG 管道优化。
    """

    extensions = list(MARKITDOWN_EXTENSIONS)

    def __init__(self):
        self._md = None

    @property
    def md(self):
        """懒加载 MarkItDown 实例"""
        if self._md is None:
            try:
                from markitdown import MarkItDown
                self._md = MarkItDown(enable_plugins=False)
                log.info("MarkItDown 引擎已加载")
            except ImportError:
                log.warning("markitdown 未安装，请运行: pip install markitdown[pdf,docx,pptx,xlsx]")
                raise
        return self._md

    def load(self, filepath: str, base_path: str) -> Optional[LoadedDocument]:
        """使用 MarkItDown 转换文件为 Markdown"""
        try:
            result = self.md.convert(filepath)
        except Exception as e:
            log.debug(f"MarkItDown 转换失败: {filepath} ({e})")
            return None

        if not result or not result.text_content or not result.text_content.strip():
            log.debug(f"MarkItDown 输出为空: {filepath}")
            return None

        content = result.text_content.strip()

        # 从 Markdown 内容提取首个标题
        heading = self._extract_heading(content)

        # 提取表格（Markdown 格式的表格）
        tables = self._extract_tables(content)

        # 确定文件类型标签
        ext = os.path.splitext(filepath)[1].lower()
        file_type = ext.lstrip(".")

        folder, subfolder = _get_folder_info(filepath, base_path)
        return LoadedDocument(
            content=content,
            source=filepath,
            filename=os.path.basename(filepath),
            file_type=file_type,
            category="",
            folder=folder,
            subfolder=subfolder,
            file_size=os.path.getsize(filepath),
            file_mtime=_get_file_mtime(filepath),
            heading=heading,
            tables=tables if tables else None,
        )

    @staticmethod
    def _extract_heading(content: str) -> str:
        """从 Markdown 内容提取首个标题"""
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("#"):
                return line.lstrip("# ").strip()
        return ""

    @staticmethod
    def _extract_tables(content: str) -> List[str]:
        """提取 Markdown 格式的表格块"""
        tables = []
        current_table = []
        in_table = False

        for line in content.split("\n"):
            stripped = line.strip()
            if "|" in stripped and stripped.startswith("|"):
                if not in_table:
                    in_table = True
                current_table.append(stripped)
            else:
                if in_table and current_table:
                    tables.append("\n".join(current_table))
                    current_table = []
                    in_table = False

        if current_table:
            tables.append("\n".join(current_table))

        return tables

    @staticmethod
    def is_markitdown_supported(ext: str) -> bool:
        """检查扩展名是否被 MarkItDown 优先支持"""
        return ext.lower() in MARKITDOWN_EXTENSIONS
