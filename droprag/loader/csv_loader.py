"""DropRAG CSV 加载器 - csv + 编码检测"""

import os
import csv
from typing import Optional
from droprag.loader import LoaderBase, LoadedDocument, _get_folder_info, _get_file_mtime, _try_read
from droprag.logging import get_logger

log = get_logger(__name__)


class CsvLoader(LoaderBase):
    extensions = [".csv"]

    def load(self, filepath: str, base_path: str) -> Optional[LoadedDocument]:
        # 尝试检测编码
        content = _try_read(filepath)
        if content is None:
            return None

        # 解析 CSV 为结构化文本
        try:
            lines = content.split("\n")
            reader = csv.reader(lines)
            rows = []
            for row in reader:
                if not any(cell.strip() for cell in row):
                    continue
                rows.append(" | ".join(row))
            structured = "\n".join(rows)
        except Exception:
            structured = content

        folder, subfolder = _get_folder_info(filepath, base_path)
        return LoadedDocument(
            content=structured,
            source=filepath,
            filename=os.path.basename(filepath),
            file_type="csv",
            category="",
            folder=folder,
            subfolder=subfolder,
            file_size=os.path.getsize(filepath),
            file_mtime=_get_file_mtime(filepath),
        )
