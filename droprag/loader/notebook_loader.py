"""DropRAG Jupyter Notebook 加载器"""

import os
import json
from typing import Optional
from droprag.loader import LoaderBase, LoadedDocument, _get_folder_info, _get_file_mtime
from droprag.logging import get_logger

log = get_logger(__name__)


class NotebookLoader(LoaderBase):
    extensions = [".ipynb"]

    def load(self, filepath: str, base_path: str) -> Optional[LoadedDocument]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                nb = json.load(f)
        except Exception as e:
            log.debug(f"ipynb 加载失败: {filepath} ({e})")
            return None

        parts = []
        for cell in nb.get("cells", []):
            cell_type = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))
            if cell_type == "markdown" and source.strip():
                parts.append(f"[Markdown]\n{source}")
            elif cell_type == "code" and source.strip():
                parts.append(f"[Code]\n{source}")

        content = "\n\n".join(parts)
        if not content.strip():
            return None

        folder, subfolder = _get_folder_info(filepath, base_path)
        return LoadedDocument(
            content=content,
            source=filepath,
            filename=os.path.basename(filepath),
            file_type="ipynb",
            category="",
            folder=folder,
            subfolder=subfolder,
            file_size=os.path.getsize(filepath),
            file_mtime=_get_file_mtime(filepath),
        )
