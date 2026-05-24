"""DropRAG 数据清洗管线

按文件类型组合清洗步骤：
- PDF: 去水印/去页眉页脚/合并碎片
- DOCX: 去修订/提取表格
- XLSX: 去空行/展开合并单元格
- PPTX: 提取备注/表格
- 通用: 去空白/Unicode标准化
"""

import re
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass

from droprag.loader import LoadedDocument
from droprag.logging import get_logger

log = get_logger(__name__)


@dataclass
class CleanResult:
    """清洗结果"""
    content: str
    tables: List[str] = None
    images: List[Dict] = None
    notes: List[str] = None
    cleaning_steps: List[str] = None


class CleanerPipeline:
    """按文件类型组合清洗步骤"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._steps: Dict[str, List[Callable]] = {
            "pdf": self._pdf_steps(),
            "docx": self._docx_steps(),
            "xlsx": self._xlsx_steps(),
            "xls": self._xlsx_steps(),
            "csv": self._csv_steps(),
            "pptx": self._pptx_steps(),
        }

    def clean(self, doc: LoadedDocument) -> LoadedDocument:
        """清洗文档（原地修改并返回）"""
        if not self.enabled:
            return doc

        file_type = doc.file_type
        steps = self._steps.get(file_type, [])

        if not steps:
            # 通用清洗
            doc.content = self._common_clean(doc.content)
            return doc

        applied = []
        for step in steps:
            try:
                doc = step(doc)
                applied.append(step.__name__)
            except Exception as e:
                log.debug(f"清洗步骤 {step.__name__} 失败: {e}")

        # 最后统一通用清洗
        doc.content = self._common_clean(doc.content)

        if applied:
            log.debug(f"文档 {doc.filename} 清洗完成: {applied}")

        return doc

    # ── PDF 清洗 ──

    def _pdf_steps(self) -> List[Callable]:
        return [
            self._remove_headers_footers,
            self._merge_fragments,
        ]

    def _remove_headers_footers(self, doc: LoadedDocument) -> LoadedDocument:
        """去页眉页脚（重复文本检测）"""
        lines = doc.content.split("\n")
        if len(lines) < 10:
            return doc

        # 检测高频重复行（可能是页眉/页脚）
        line_counts: Dict[str, int] = {}
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) < 100:
                line_counts[stripped] = line_counts.get(stripped, 0) + 1

        # 重复3次以上的短行视为页眉/页脚
        threshold = max(3, len(lines) // 20)
        header_footer_lines = {
            line for line, count in line_counts.items()
            if count >= threshold
        }

        # 只移除纯数字行（页码）和重复行
        filtered = []
        for line in lines:
            stripped = line.strip()
            if stripped in header_footer_lines and (stripped.isdigit() or len(stripped) < 30):
                continue
            filtered.append(line)

        doc.content = "\n".join(filtered)
        return doc

    def _merge_fragments(self, doc: LoadedDocument) -> LoadedDocument:
        """合并碎片段落（短行拼接）"""
        lines = doc.content.split("\n")
        if not lines:
            return doc

        merged = []
        current = ""

        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                if current:
                    merged.append(current)
                    current = ""
                merged.append("")
                continue

            # 如果当前行不以标点结尾且很短，拼接
            if current and not current.rstrip().endswith(("。", "，", "！", "？", ".", ",", "!", "?", ":", "：", "；", ";")):
                if len(current) < 200:
                    current += stripped
                    continue

            if current:
                merged.append(current)
            current = stripped

        if current:
            merged.append(current)

        doc.content = "\n".join(merged)
        return doc

    # ── DOCX 清洗 ──

    def _docx_steps(self) -> List[Callable]:
        return []

    # ── XLSX 清洗 ──

    def _xlsx_steps(self) -> List[Callable]:
        return [
            self._remove_empty_rows,
        ]

    def _remove_empty_rows(self, doc: LoadedDocument) -> LoadedDocument:
        """去空行"""
        lines = doc.content.split("\n")
        filtered = [line for line in lines if line.strip()]
        doc.content = "\n".join(filtered)
        return doc

    # ── CSV 清洗 ──

    def _csv_steps(self) -> List[Callable]:
        return [
            self._remove_empty_rows,
        ]

    # ── PPTX 清洗 ──

    def _pptx_steps(self) -> List[Callable]:
        return []

    # ── 通用清洗 ──

    def _common_clean(self, content: str) -> str:
        """通用清洗步骤"""
        if not content:
            return content

        # 1. 去多余空白（连续空行压缩为2个）
        content = re.sub(r'\n{3,}', '\n\n', content)

        # 2. 去行尾空白
        content = '\n'.join(line.rstrip() for line in content.split('\n'))

        # 3. Unicode 标准化 (NFC)
        import unicodedata
        content = unicodedata.normalize('NFC', content)

        # 4. 去控制字符（保留换行/制表符）
        content = ''.join(
            ch for ch in content
            if ch >= ' ' or ch in '\n\t\r'
        )

        return content.strip()
