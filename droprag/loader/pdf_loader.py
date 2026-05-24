"""DropRAG PDF 加载器 - pypdf + PyMuPDF 双引擎"""

import os
from typing import Optional
from droprag.loader import LoaderBase, LoadedDocument, _get_folder_info, _get_file_mtime
from droprag.logging import get_logger

log = get_logger(__name__)


class PdfLoader(LoaderBase):
    extensions = [".pdf"]

    def load(self, filepath: str, base_path: str) -> Optional[LoadedDocument]:
        # 尝试 PyMuPDF（更好的文本提取）
        content = self._load_with_pymupdf(filepath)
        if not content:
            # 回退到 pypdf
            content = self._load_with_pypdf(filepath)
        if not content:
            return None

        folder, subfolder = _get_folder_info(filepath, base_path)
        return LoadedDocument(
            content=content,
            source=filepath,
            filename=os.path.basename(filepath),
            file_type="pdf",
            category="",
            folder=folder,
            subfolder=subfolder,
            file_size=os.path.getsize(filepath),
            file_mtime=_get_file_mtime(filepath),
        )

    def _load_with_pymupdf(self, filepath: str) -> Optional[str]:
        """使用 PyMuPDF 加载"""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(filepath)
            pages = []
            for page in doc:
                text = page.get_text()
                if text.strip():
                    pages.append(text)
            doc.close()
            return "\n\n".join(pages) if pages else None
        except ImportError:
            return None
        except Exception as e:
            log.debug(f"PyMuPDF 加载失败: {filepath} ({e})")
            return None

    def _load_with_pypdf(self, filepath: str) -> Optional[str]:
        """使用 pypdf 加载"""
        try:
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages) if pages else None
        except ImportError:
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(filepath)
                pages = []
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                return "\n\n".join(pages) if pages else None
            except Exception:
                return None
        except Exception as e:
            log.debug(f"pypdf 加载失败: {filepath} ({e})")
            return None
