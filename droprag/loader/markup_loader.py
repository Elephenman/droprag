"""DropRAG HTML/HTM 加载器 — BeautifulSoup 提取文本"""

import os
from typing import Optional
from droprag.loader import LoaderBase, LoadedDocument, _get_folder_info, _get_file_mtime, _try_read


class HtmlLoader(LoaderBase):
    """HTML/HTM 文件加载器"""

    extensions = [".html", ".htm"]

    def load(self, filepath: str, base_path: str) -> Optional[LoadedDocument]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            # 降级：纯文本读取，去掉标签
            content = _try_read(filepath)
            if content is None:
                return None
            import re
            content = re.sub(r"<[^>]+>", "", content)
        else:
            raw = _try_read(filepath)
            if raw is None:
                return None
            soup = BeautifulSoup(raw, "lxml")
            # 去掉 script / style
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            content = soup.get_text(separator="\n", strip=True)

        if not content.strip():
            return None

        folder, subfolder = _get_folder_info(filepath, base_path)
        filename = os.path.basename(filepath)
        file_type = os.path.splitext(filepath)[1].lstrip(".").lower()

        # 提取 <title>
        heading = ""
        try:
            from bs4 import BeautifulSoup as BS
            raw2 = _try_read(filepath)
            if raw2:
                soup2 = BS(raw2, "lxml")
                title_tag = soup2.find("title")
                if title_tag:
                    heading = title_tag.get_text(strip=True)
        except Exception:
            pass

        return LoadedDocument(
            content=content,
            source=os.path.abspath(filepath),
            filename=filename,
            file_type=file_type,
            category="web_page",
            folder=folder,
            subfolder=subfolder,
            file_size=os.path.getsize(filepath),
            file_mtime=_get_file_mtime(filepath),
            heading=heading,
        )
