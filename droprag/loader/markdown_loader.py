"""DropRAG Markdown 加载器"""

import os
from typing import Optional
from droprag.loader import LoaderBase, LoadedDocument, _get_folder_info, _get_file_mtime, _try_read


class MarkdownLoader(LoaderBase):
    extensions = [".md", ".rmd", ".rst"]

    def load(self, filepath: str, base_path: str) -> Optional[LoadedDocument]:
        content = _try_read(filepath)
        if content is None:
            return None
        folder, subfolder = _get_folder_info(filepath, base_path)
        heading = self._extract_first_heading(content)
        ext = os.path.splitext(filepath)[1].lower().lstrip(".")
        if ext == "rmd":
            ext = "md"
        elif ext == "rst":
            ext = "rst"
        else:
            ext = "md"
        return LoadedDocument(
            content=content,
            source=filepath,
            filename=os.path.basename(filepath),
            file_type=ext,
            category="",
            folder=folder,
            subfolder=subfolder,
            file_size=os.path.getsize(filepath),
            file_mtime=_get_file_mtime(filepath),
            heading=heading,
        )

    @staticmethod
    def _extract_first_heading(content: str) -> str:
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("#"):
                return line.lstrip("#").strip()
        return ""
