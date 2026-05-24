"""DropRAG 结构化数据加载器 — JSON/JSONL/XML/YAML/TOML"""

import os
import json
from typing import Optional
from droprag.loader import LoaderBase, LoadedDocument, _get_folder_info, _get_file_mtime, _try_read


class DataLoader(LoaderBase):
    """结构化数据文件加载器 (JSON/JSONL/XML/YAML/TOML)"""

    extensions = [".json", ".jsonl", ".xml", ".yaml", ".yml", ".toml"]

    # 分类映射
    _category_map = {
        ".json": "data_json",
        ".jsonl": "data_jsonl",
        ".xml": "data_xml",
        ".yaml": "data_yaml",
        ".yml": "data_yaml",
        ".toml": "data_toml",
    }

    def load(self, filepath: str, base_path: str) -> Optional[LoadedDocument]:
        ext = os.path.splitext(filepath)[1].lower()
        content = self._extract(filepath, ext)
        if content is None or not content.strip():
            return None

        folder, subfolder = _get_folder_info(filepath, base_path)
        filename = os.path.basename(filepath)
        file_type = ext.lstrip(".")

        heading = self._extract_heading(filepath, ext)

        return LoadedDocument(
            content=content,
            source=os.path.abspath(filepath),
            filename=filename,
            file_type=file_type,
            category=self._category_map.get(ext, "data"),
            folder=folder,
            subfolder=subfolder,
            file_size=os.path.getsize(filepath),
            file_mtime=_get_file_mtime(filepath),
            heading=heading,
        )

    def _extract(self, filepath: str, ext: str) -> Optional[str]:
        """按文件类型提取文本"""
        if ext in (".json", ".jsonl"):
            return self._load_json(filepath, ext)
        elif ext == ".xml":
            return self._load_xml(filepath)
        elif ext in (".yaml", ".yml"):
            return self._load_yaml(filepath)
        elif ext == ".toml":
            return self._load_toml(filepath)
        return None

    def _load_json(self, filepath: str, ext: str) -> Optional[str]:
        """加载 JSON/JSONL"""
        raw = _try_read(filepath)
        if raw is None:
            return None
        try:
            if ext == ".jsonl":
                # JSONL: 逐行解析，合并为文本
                lines = []
                for line in raw.strip().split("\n"):
                    line = line.strip()
                    if line:
                        obj = json.loads(line)
                        lines.append(self._flatten(obj))
                return "\n---\n".join(lines)
            else:
                obj = json.loads(raw)
                return self._flatten(obj)
        except json.JSONDecodeError:
            return raw  # 降级为纯文本

    def _load_xml(self, filepath: str) -> Optional[str]:
        """加载 XML — 提取所有文本节点"""
        raw = _try_read(filepath)
        if raw is None:
            return None
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(raw)
            texts = []
            for elem in root.iter():
                if elem.text and elem.text.strip():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    texts.append(f"[{tag}] {elem.text.strip()}")
                if elem.tail and elem.tail.strip():
                    texts.append(elem.tail.strip())
            return "\n".join(texts)
        except Exception:
            # 降级：去掉标签
            import re
            return re.sub(r"<[^>]+>", " ", raw)

    def _load_yaml(self, filepath: str) -> Optional[str]:
        """加载 YAML"""
        raw = _try_read(filepath)
        if raw is None:
            return None
        try:
            import yaml
            obj = yaml.safe_load(raw)
            if obj is None:
                return raw
            return self._flatten(obj)
        except ImportError:
            return raw  # 无 yaml 库降级为纯文本
        except Exception:
            return raw

    def _load_toml(self, filepath: str) -> Optional[str]:
        """加载 TOML"""
        raw = _try_read(filepath)
        if raw is None:
            return None
        try:
            import tomllib  # Python 3.11+
            obj = tomllib.loads(raw)
            return self._flatten(obj)
        except ImportError:
            try:
                import tomli
                obj = tomli.loads(raw)
                return self._flatten(obj)
            except ImportError:
                return raw
        except Exception:
            return raw

    def _flatten(self, obj, prefix: str = "", depth: int = 0) -> str:
        """递归展平结构化数据为可读文本，限制深度"""
        if depth > 6:
            return str(obj)
        if isinstance(obj, dict):
            lines = []
            for k, v in obj.items():
                key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, (dict, list)):
                    lines.append(f"{key}:")
                    lines.append(self._flatten(v, key, depth + 1))
                else:
                    lines.append(f"{key}: {v}")
            return "\n".join(lines)
        elif isinstance(obj, list):
            lines = []
            for i, item in enumerate(obj[:200]):  # 最多200条
                if isinstance(item, (dict, list)):
                    lines.append(self._flatten(item, f"{prefix}[{i}]", depth + 1))
                else:
                    lines.append(f"- {item}")
            if len(obj) > 200:
                lines.append(f"... ({len(obj) - 200} more items)")
            return "\n".join(lines)
        else:
            return str(obj)

    def _extract_heading(self, filepath: str, ext: str) -> str:
        """尝试提取标题"""
        try:
            if ext == ".json":
                raw = _try_read(filepath)
                if raw:
                    obj = json.loads(raw)
                    if isinstance(obj, dict):
                        for key in ("title", "name", "heading", "id"):
                            if key in obj:
                                return str(obj[key])[:120]
            elif ext == ".xml":
                import xml.etree.ElementTree as ET
                raw = _try_read(filepath)
                if raw:
                    root = ET.fromstring(raw)
                    for tag in ("title", "name", "heading"):
                        elem = root.find(f".//{tag}")
                        if elem is not None and elem.text:
                            return elem.text.strip()[:120]
        except Exception:
            pass
        return ""
