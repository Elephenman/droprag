"""DropRAG 代码文件加载器"""

import os
from typing import Optional
from droprag.loader import LoaderBase, LoadedDocument, _get_folder_info, _get_file_mtime, _try_read


class CodeLoader(LoaderBase):
    extensions = [".py", ".js", ".ts", ".r", ".R", ".java", ".cpp", ".c",
                  ".go", ".rs", ".rb", ".php", ".swift", ".kt"]

    # 文件类型映射
    _ext_to_type = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".r": "r", ".R": "r", ".java": "java", ".cpp": "cpp",
        ".c": "c", ".go": "go", ".rs": "rust", ".rb": "ruby",
        ".php": "php", ".swift": "swift", ".kt": "kotlin",
    }

    def load(self, filepath: str, base_path: str) -> Optional[LoadedDocument]:
        content = _try_read(filepath)
        if content is None:
            return None

        ext = os.path.splitext(filepath)[1].lower()
        file_type = self._ext_to_type.get(ext, "code")
        folder, subfolder = _get_folder_info(filepath, base_path)

        # 提取代码注释作为标题
        heading = self._extract_code_heading(content, ext)

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
        )

    @staticmethod
    def _extract_code_heading(content: str, ext: str) -> str:
        """提取代码文件的第一个注释作为标题"""
        for line in content.split("\n"):
            line = line.strip()
            # Python/JS/TS/R: # 注释
            if ext in (".py", ".js", ".ts", ".r", ".R", ".go", ".rs", ".rb", ".swift", ".kt"):
                if line.startswith("# ") and not line.startswith("# !"):
                    return line.lstrip("# ").strip()
            # Java/C/C++: // 或 /* 注释
            elif ext in (".java", ".cpp", ".c", ".php"):
                if line.startswith("// "):
                    return line.lstrip("/ ").strip()
            # 其他
            elif line.startswith("# "):
                return line.lstrip("# ").strip()
        return ""
