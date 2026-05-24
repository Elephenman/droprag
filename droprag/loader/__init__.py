"""DropRAG 插件化加载器系统

双层 Loader 架构:
1. MarkItDown 引擎（微软）— 首选，支持 PDF/DOCX/PPTX/XLSX/HTML/EPUB/Image/Audio
2. 原生 Loader（降级）— MarkItDown 不支持或失败时回退

加载优先级：MarkItDown → 原生 Loader → 失败
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


# ── 注册表（双层） ──

_primary_loaders: Dict[str, LoaderBase] = {}    # MarkItDown 首选层
_fallback_loaders: Dict[str, LoaderBase] = {}   # 原生 Loader 降级层
_loader_classes: List[Type[LoaderBase]] = []
_markitdown_available: bool = False


def register_loader(loader_class: Type[LoaderBase], primary: bool = False):
    """注册一个 Loader 类

    Args:
        loader_class: Loader 类
        primary: 是否为首选 Loader（MarkItDown 层），默认为降级层
    """
    _loader_classes.append(loader_class)
    instance = loader_class()
    target = _primary_loaders if primary else _fallback_loaders
    for ext in loader_class.extensions:
        target[ext.lower()] = instance
    layer = "首选" if primary else "降级"
    log.debug(f"注册 Loader [{layer}]: {loader_class.__name__} → {loader_class.extensions}")


def get_loader(ext: str) -> Optional[LoaderBase]:
    """根据扩展名获取 Loader（首选优先）"""
    loader = _primary_loaders.get(ext.lower())
    if loader:
        return loader
    return _fallback_loaders.get(ext.lower())


def load_file(filepath: str, base_path: str, category: str = "") -> Optional[LoadedDocument]:
    """根据扩展名自动选择加载器（双层降级）

    优先使用 MarkItDown 转换，失败则降级到原生 Loader。
    """
    ext = os.path.splitext(filepath)[1].lower()

    # 1. 尝试 MarkItDown 首选层
    primary = _primary_loaders.get(ext)
    if primary:
        try:
            doc = primary.load(filepath, base_path)
            if doc is not None:
                return doc
        except Exception as e:
            log.debug(f"首选 Loader 失败，降级: {filepath} ({e})")

    # 2. 降级到原生 Loader
    fallback = _fallback_loaders.get(ext)
    if fallback:
        try:
            doc = fallback.load(filepath, base_path)
            if doc is not None:
                return doc
        except Exception as e:
            log.debug(f"降级 Loader 也失败: {filepath} ({e})")

    return None


def get_supported_extensions() -> List[str]:
    """获取所有支持的扩展名（合并两层）"""
    all_exts = set(_primary_loaders.keys()) | set(_fallback_loaders.keys())
    return sorted(all_exts)


def get_loader_info() -> Dict:
    """获取当前 Loader 注册信息（调试用）"""
    return {
        "markitdown_available": _markitdown_available,
        "primary_extensions": sorted(_primary_loaders.keys()),
        "fallback_extensions": sorted(_fallback_loaders.keys()),
        "total_extensions": len(set(_primary_loaders.keys()) | set(_fallback_loaders.keys())),
    }


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
    """自动发现并注册所有 Loader（双层架构）

    注册顺序:
    1. 原生 Loader（降级层）— 始终注册
    2. MarkItDown Loader（首选层）— 可选，覆盖原生 Loader 支持的格式
    """
    global _markitdown_available

    # ── 降级层：原生 Loader ──
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

    # ── 首选层：MarkItDown ──
    try:
        from droprag.loader.markitdown_loader import MarkItDownLoader
        register_loader(MarkItDownLoader, primary=True)
        _markitdown_available = True
        log.info("MarkItDown 引擎已注册为首选 Loader")
    except ImportError:
        _markitdown_available = False
        log.info("markitdown 未安装，使用原生 Loader 作为唯一引擎")

    primary_count = len(_primary_loaders)
    fallback_count = len(_fallback_loaders)
    total = len(set(_primary_loaders.keys()) | set(_fallback_loaders.keys()))
    log.info(f"Loader 注册完成: 首选 {primary_count} / 降级 {fallback_count} / 总计 {total} 种扩展名")


# 模块加载时自动发现
try:
    discover_loaders()
except Exception:
    pass
