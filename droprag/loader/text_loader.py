"""DropRAG 纯文本加载器"""

import os
from typing import Optional
from droprag.loader import LoaderBase, LoadedDocument, _get_folder_info, _get_file_mtime, _try_read


class TextLoader(LoaderBase):
    extensions = [".txt", ".log"]

    def load(self, filepath: str, base_path: str) -> Optional[LoadedDocument]:
        content = _try_read(filepath)
        if content is None:
            return None
        folder, subfolder = _get_folder_info(filepath, base_path)
        return LoadedDocument(
            content=content,
            source=filepath,
            filename=os.path.basename(filepath),
            file_type="txt",
            category="",
            folder=folder,
            subfolder=subfolder,
            file_size=os.path.getsize(filepath),
            file_mtime=_get_file_mtime(filepath),
        )
