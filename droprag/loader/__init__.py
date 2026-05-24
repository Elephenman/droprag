"""DropRAG 插件化加载器系统

LoaderBase 基类 + LoaderRegistry 自动发现注册。
所有 Loader 声明支持的 extensions，Registry 自动匹配。
"""

import os
from typing import List, Optional, Dict, Type
from dataclasses import dataclass

from droprag.logging import get_logger

log = get_logger(__name__)


@dataclass
class LoadedDocument:
    """加载后的文档对象（通用）"""
    content: str           # 纯文本内容
    source: str            # 完整文件路径
    filename: str          # 文件名
    file_type: str         # 扩展名（不含点）
    category: str          # 自动分类结果
    folder: str            # 一级文件夹
    subfolder: str         # 二级文件夹
    file_size: int         # 字节数
    file_mtime: str        # 修改时间ISO
    heading: str = ""      # 首个标题
    tables: Optional[List[str]] = None   # 提取的表格
    images: Optional[List[dict]] = None  # 图片信息


class LoaderBase:
    """加载器基类"""

    # 子类必须声明支持的扩展名列表（含点，小写）
    extensions: List[str] = []

    def load(self, filepath: str, base_path: str) -> Optional[LoadedDocument]:
        """加载文件，返回 LoadedDocument 或 None"""
        raise NotImplementedError


# ── 注册表 ──

_loaders: Dict[str, LoaderBase] = {}
_loader_classes: List[Type[LoaderBase]] = []


def register_loader(loader_class: Type[LoaderBase]):
    """注册一个 Loader 类"""
    _loader_classes.append(loader_class)
    instance = loader_class()
    for ext in loader_class.extensions:
        _loaders[ext.lower()] = instance
    log.debug(f"注册 Loader: {loader_class.__name__} → {loader_class.extensions}")


def get_loader(ext: str) -> Optional[LoaderBase]:
    """根据扩展名获取 Loader"""
    return _loaders.get(ext.lower())


def load_file(filepath: str, base_path: str, category: str = "") -> Optional[LoadedDocument]:
    """根据扩展名自动选择加载器"""
    ext = os.path.splitext(filepath)[1].lower()
    loader = get_loader(ext)
    if loader is None:
        return None
    return loader.load(filepath, base_path)


def get_supported_extensions() -> List[str]:
    """获取所有支持的扩展名"""
    return list(_loaders.keys())


def _get_folder_info(filepath: str, base_path: str) -> tuple:
    """获取一级和二级文件夹名"""
    rel = os.path.relpath(filepath, base_path)
    parts = rel.replace("\\", "/").split("/")
    folder = parts[0] if len(parts) > 1 else ""
    subfolder = parts[1] if len(parts) > 2 else ""
    return folder, subfolder


def _get_file_mtime(filepath: str) -> str:
    """获取文件修改时间 ISO 格式"""
    import datetime
    mtime = os.path.getmtime(filepath)
    return datetime.datetime.fromtimestamp(mtime).isoformat()


def _try_read(filepath: str, encodings: list = None) -> Optional[str]:
    """尝试多种编码读取文件"""
    if encodings is None:
        encodings = ["utf-8", "gbk", "gb2312", "latin-1"]
    for enc in encodings:
        try:
            with open(filepath, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 用 chardet 检测编码
    try:
        import chardet
        with open(filepath, "rb") as f:
            raw = f.read()
        detected = chardet.detect(raw)
        if detected and detected["encoding"]:
            return raw.decode(detected["encoding"], errors="replace")
    except Exception:
        pass
    return None


# ── 自动发现 ──

def discover_loaders():
    """自动发现并注册所有 Loader"""
    from droprag.loader.text_loader import TextLoader
    register_loader(TextLoader)

    from droprag.loader.markdown_loader import MarkdownLoader
    register_loader(MarkdownLoader)

    from droprag.loader.pdf_loader import PdfLoader
    register_loader(PdfLoader)

    from droprag.loader.code_loader import CodeLoader
    register_loader(CodeLoader)

    from droprag.loader.notebook_loader import NotebookLoader
    register_loader(NotebookLoader)

    # 可选依赖 Loader（安装了才注册）
    try:
        from droprag.loader.docx_loader import DocxLoader
        register_loader(DocxLoader)
    except ImportError:
        pass

    try:
        from droprag.loader.xlsx_loader import XlsxLoader
        register_loader(XlsxLoader)
    except ImportError:
        pass

    try:
        from droprag.loader.csv_loader import CsvLoader
        register_loader(CsvLoader)
    except ImportError:
        pass

    try:
        from droprag.loader.pptx_loader import PptxLoader
        register_loader(PptxLoader)
    except ImportError:
        pass

    try:
        from droprag.loader.markup_loader import HtmlLoader
        register_loader(HtmlLoader)
    except ImportError:
        pass

    try:
        from droprag.loader.data_loader import DataLoader
        register_loader(DataLoader)
    except ImportError:
        pass

    log.info(f"Loader 注册完成: {len(_loaders)} 种扩展名")


# 模块加载时自动发现
try:
    discover_loaders()
except Exception:
    pass
