"""DropRAG 函数级分块器 - 代码文件

增强版：支持 Python class 级别分块、缩进感知切分、
多种语言的函数定义模式匹配。
"""

import re
from typing import List, Tuple, Optional
from droprag.chunker import ChunkerBase, Chunk, split_by_separators, make_chunk_metadata
from droprag.loader import LoadedDocument
from droprag.config import ChunkTypeConfig


class FunctionChunker(ChunkerBase):
    """函数级分块器 — 代码文件按函数/类定义切分"""

    file_types = ["python", "javascript", "typescript", "r", "java", "cpp", "c",
                  "go", "rust", "ruby", "php", "swift", "kotlin", "code"]

    # 不同语言的函数/类定义正则
    _func_patterns = {
        "python": [
            re.compile(r'^(?:class\s+\w+.*?:)', re.MULTILINE),      # class 定义
            re.compile(r'^(?:async\s+)?def\s+\w+', re.MULTILINE),   # 函数定义
        ],
        "javascript": [
            re.compile(r'^(?:export\s+)?(?:default\s+)?class\s+\w+', re.MULTILINE),
            re.compile(r'^(?:async\s+)?function\s*\*?\s+\w+', re.MULTILINE),
            re.compile(r'^(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?(?:function|\()', re.MULTILINE),
        ],
        "typescript": [
            re.compile(r'^(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+\w+', re.MULTILINE),
            re.compile(r'^(?:export\s+)?(?:async\s+)?function\s+\w+', re.MULTILINE),
            re.compile(r'^(?:const|let|var)\s+\w+\s*:\s*\w+', re.MULTILINE),
        ],
        "r": [
            re.compile(r'^\w+\s*<?-\s*function\s*\(', re.MULTILINE),
            re.compile(r'^set(?:Class|Method|Generic|RefClass|GroupGeneric)\s*\(', re.MULTILINE),
        ],
        "java": [
            re.compile(r'^(?:public|private|protected)\s+(?:abstract\s+)?(?:class|interface|enum)\s+\w+', re.MULTILINE),
            re.compile(r'^(?:public|private|protected|static)\s+(?:<[^>]+>\s+)?\w+(?:\[\])*\s+\w+\s*\(', re.MULTILINE),
        ],
        "cpp": [
            re.compile(r'^(?:class|struct|enum)\s+\w+', re.MULTILINE),
            re.compile(r'^(?:\w+(?:::\w+)*\s+)+\w+\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*\{', re.MULTILINE),
        ],
        "c": [
            re.compile(r'^(?:typedef\s+)?(?:struct|enum)\s+\w+', re.MULTILINE),
            re.compile(r'^(?:static\s+)?(?:\w+\s+)+\w+\s*\([^)]*\)\s*\{', re.MULTILINE),
        ],
        "go": [
            re.compile(r'^func\s+(?:\(\w+\s+\*?\w+\)\s+)?\w+', re.MULTILINE),
            re.compile(r'^type\s+\w+\s+struct', re.MULTILINE),
        ],
        "rust": [
            re.compile(r'^(?:pub\s+)?(?:async\s+)?fn\s+\w+', re.MULTILINE),
            re.compile(r'^(?:pub\s+)?(?:struct|enum|trait|impl)\s+\w+', re.MULTILINE),
        ],
    }

    # Python 缩进感知：基于缩进级别分割
    _indent_languages = {"python"}

    def chunk(self, doc: LoadedDocument, cfg: ChunkTypeConfig) -> List[Chunk]:
        file_type = doc.file_type
        patterns = self._func_patterns.get(file_type)

        if patterns:
            if file_type in self._indent_languages:
                func_parts = self._split_python(doc.content, patterns)
            else:
                func_parts = self._split_by_patterns(doc.content, patterns)
        else:
            func_parts = [doc.content]

        # 对每个函数块，如果太大继续切
        raw_chunks = []
        for heading_text, part in func_parts:
            if len(part) <= cfg.chunk_size:
                raw_chunks.append((heading_text, part))
            else:
                sub = split_by_separators(part, cfg.separators, cfg.chunk_size, cfg.chunk_overlap)
                for s in sub:
                    raw_chunks.append((heading_text, s))

        chunks = []
        for i, (heading_text, text) in enumerate(raw_chunks):
            if not text.strip():
                continue
            heading = doc.heading or heading_text
            meta = make_chunk_metadata(doc, i, len(raw_chunks), len(text), heading)
            chunks.append(Chunk(content=text, metadata=meta))
        return chunks

    def _split_python(self, content: str, patterns: list) -> List[Tuple[str, str]]:
        """Python 缩进感知分割 — 基于缩进级别切分 class/method"""
        lines = content.split("\n")
        blocks: List[Tuple[str, str]] = []

        # 找到所有 class/def 起始行
        starts: List[Tuple[int, str]] = []
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            for pattern in patterns:
                if pattern.match(stripped):
                    name = stripped.rstrip(":").strip()[:80]
                    starts.append((i, name))
                    break

        if not starts:
            return [("", content)]

        # 按缩进级别分割
        for idx, (start_line, name) in enumerate(starts):
            # 当前块的缩进
            first_line = lines[start_line]
            base_indent = len(first_line) - len(first_line.lstrip())

            # 找到当前块的结束
            end_line = len(lines)
            if idx + 1 < len(starts):
                next_start = starts[idx + 1][0]
                # 向后搜索，找到缩进回到 base_indent 或更低的位置
                for j in range(start_line + 1, next_start + 1):
                    if j >= len(lines):
                        break
                    line = lines[j]
                    if line.strip() and not line.strip().startswith("#"):
                        current_indent = len(line) - len(line.lstrip())
                        if current_indent <= base_indent and j > start_line + 1:
                            end_line = j
                            break
                else:
                    end_line = next_start
            else:
                # 最后一个块到文件末尾
                pass

            block_text = "\n".join(lines[start_line:end_line])
            blocks.append((name, block_text))

        # 补充块之前的前导代码（imports, 全局变量等）
        first_block_start = starts[0][0] if starts else 0
        if first_block_start > 0:
            preamble = "\n".join(lines[:first_block_start])
            if preamble.strip():
                blocks.insert(0, ("(module header)", preamble))

        return blocks

    def _split_by_patterns(self, content: str, patterns: list) -> List[Tuple[str, str]]:
        """通用模式匹配分割"""
        # 合并所有匹配位置
        all_matches: List[Tuple[int, str]] = []
        for pattern in patterns:
            for m in pattern.finditer(content):
                name = m.group(0).strip()[:80]
                all_matches.append((m.start(), name))

        # 按位置排序
        all_matches.sort(key=lambda x: x[0])

        if not all_matches:
            return [("", content)]

        parts = []
        for idx, (start, name) in enumerate(all_matches):
            if idx + 1 < len(all_matches):
                end = all_matches[idx + 1][0]
            else:
                end = len(content)
            block_text = content[start:end]
            if block_text.strip():
                parts.append((name, block_text))

        # 补充前导部分
        first_start = all_matches[0][0]
        if first_start > 0:
            preamble = content[:first_start]
            if preamble.strip():
                parts.insert(0, ("(header)", preamble))

        return parts
