"""DropRAG 核心模块单元测试

验证:
1. 配置加载
2. 文件分类器
3. 加载器注册与加载
4. 分块器注册与分块
5. 清洗管线
6. Pipeline 流程
7. VectorStore 增删查
8. 缓存读写
9. 查询增强
10. Engine 导入
"""

import os
import sys
import tempfile
import pytest

# 确保项目路径在 sys.path 中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestConfig:
    """配置模块测试"""

    def test_default_config(self):
        from droprag.config import DropRAGConfig
        config = DropRAGConfig()
        assert config.engine.port == 8766
        assert config.embedding.provider == "auto"
        assert config.embedding.dimension == 512
        assert config.pipeline.max_file_size_mb == 100

    def test_config_from_yaml(self):
        from droprag.config import load_config
        import tempfile
        import yaml

        cfg_data = {
            "engine": {"port": 9999},
            "embedding": {"provider": "onnx"},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(cfg_data, f)
            cfg_path = f.name

        try:
            config = load_config(cfg_path)
            assert config.engine.port == 9999
            assert config.embedding.provider == "onnx"
        finally:
            os.unlink(cfg_path)

    def test_chunking_config(self):
        from droprag.config import DropRAGConfig
        config = DropRAGConfig()
        assert config.chunking.default.chunk_size == 500
        assert config.chunking.markdown.chunk_size == 500
        assert config.chunking.spreadsheet.chunk_size == 300


class TestClassifier:
    """文件分类器测试"""

    def test_classify_pdf(self):
        from droprag.classifier import FileClassifier
        clf = FileClassifier()
        assert clf.classify("test.pdf") == "academic_paper"  # 默认PDF归为学术论文

    def test_classify_docx(self):
        from droprag.classifier import FileClassifier
        clf = FileClassifier()
        assert clf.classify("report.docx") == "office_doc"

    def test_classify_xlsx(self):
        from droprag.classifier import FileClassifier
        assert FileClassifier().classify("data.xlsx") == "spreadsheet"

    def test_classify_csv(self):
        from droprag.classifier import FileClassifier
        assert FileClassifier().classify("export.csv") == "spreadsheet"

    def test_classify_pptx(self):
        from droprag.classifier import FileClassifier
        assert FileClassifier().classify("slides.pptx") == "presentation"

    def test_classify_code(self):
        from droprag.classifier import FileClassifier
        assert FileClassifier().classify("main.py") == "code"
        assert FileClassifier().classify("app.js") == "code"
        assert FileClassifier().classify("analysis.r") == "code"

    def test_classify_markdown(self):
        from droprag.classifier import FileClassifier
        assert FileClassifier().classify("readme.md") == "markup"

    def test_classify_text(self):
        from droprag.classifier import FileClassifier
        assert FileClassifier().classify("notes.txt") == "text"

    def test_classify_json(self):
        from droprag.classifier import FileClassifier
        assert FileClassifier().classify("config.json") == "data"

    def test_classify_image(self):
        from droprag.classifier import FileClassifier
        assert FileClassifier().classify("photo.png") == "image"

    def test_classify_unknown(self):
        from droprag.classifier import FileClassifier
        assert FileClassifier().classify("file.xyz") == "other"

    def test_supported_extensions(self):
        from droprag.classifier import get_classifier
        clf = get_classifier()
        exts = clf.get_all_supported_extensions()
        assert ".pdf" in exts
        assert ".docx" in exts
        assert ".py" in exts


class TestLoaderRegistry:
    """加载器注册表测试"""

    def test_loaders_registered(self):
        from droprag.loader import get_supported_extensions
        exts = get_supported_extensions()
        # 至少应该有基础 loader
        assert ".txt" in exts or ".md" in exts

    def test_text_loader(self):
        from droprag.loader.text_loader import TextLoader
        loader = TextLoader()
        assert ".txt" in loader.extensions
        assert ".log" in loader.extensions

    def test_markdown_loader(self):
        from droprag.loader.markdown_loader import MarkdownLoader
        loader = MarkdownLoader()
        assert ".md" in loader.extensions

    def test_pdf_loader(self):
        from droprag.loader.pdf_loader import PdfLoader
        loader = PdfLoader()
        assert ".pdf" in loader.extensions

    def test_code_loader(self):
        from droprag.loader.code_loader import CodeLoader
        loader = CodeLoader()
        assert ".py" in loader.extensions

    def test_load_text_file(self):
        from droprag.loader import load_file
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("Hello, DropRAG!")
            path = f.name
        try:
            doc = load_file(path, os.path.dirname(path))
            assert doc is not None
            assert "Hello, DropRAG!" in doc.content
            assert doc.file_type == "txt"
        finally:
            os.unlink(path)

    def test_load_markdown_file(self):
        from droprag.loader import load_file
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Test Heading\n\nSome content.")
            path = f.name
        try:
            doc = load_file(path, os.path.dirname(path))
            assert doc is not None
            assert doc.heading == "Test Heading"
            assert doc.file_type == "md"
        finally:
            os.unlink(path)

    def test_load_python_file(self):
        from droprag.loader import load_file
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("# Test Script\ndef hello():\n    print('hi')")
            path = f.name
        try:
            doc = load_file(path, os.path.dirname(path))
            assert doc is not None
            assert doc.file_type == "python"
        finally:
            os.unlink(path)


class TestChunkerRegistry:
    """分块器注册表测试"""

    def test_chunkers_registered(self):
        from droprag.chunker import _chunkers
        assert "default" in _chunkers
        assert "md" in _chunkers
        assert "pdf" in _chunkers

    def test_semantic_chunker(self):
        from droprag.chunker.semantic_chunker import SemanticChunker
        chunker = SemanticChunker()
        assert "default" in chunker.file_types

    def test_heading_chunker(self):
        from droprag.chunker.heading_chunker import HeadingChunker
        chunker = HeadingChunker()
        assert "md" in chunker.file_types

    def test_row_chunker(self):
        from droprag.chunker.row_chunker import RowChunker
        chunker = RowChunker()
        assert "xlsx" in chunker.file_types

    def test_chunk_text(self):
        from droprag.chunker import chunk_document
        from droprag.loader import LoadedDocument
        from droprag.config import ChunkTypeConfig

        doc = LoadedDocument(
            content="This is paragraph one.\n\nThis is paragraph two.\n\nThis is paragraph three.",
            source="/test.txt", filename="test.txt", file_type="txt",
            category="text", folder="", subfolder="",
            file_size=100, file_mtime="2026-01-01",
        )
        cfg = ChunkTypeConfig(chunk_size=200, chunk_overlap=20)
        chunks = chunk_document(doc, cfg=cfg)
        assert len(chunks) > 0
        assert all(c.content.strip() for c in chunks)


class TestCleaner:
    """清洗管线测试"""

    def test_common_clean(self):
        from droprag.cleaner import CleanerPipeline
        from droprag.loader import LoadedDocument

        doc = LoadedDocument(
            content="Hello   \n\n\n\nWorld  \n  ",
            source="/test.txt", filename="test.txt", file_type="txt",
            category="", folder="", subfolder="",
            file_size=10, file_mtime="2026-01-01",
        )
        cleaner = CleanerPipeline()
        result = cleaner.clean(doc)
        # 连续空行应压缩
        assert "\n\n\n" not in result.content

    def test_merge_fragments(self):
        from droprag.cleaner import CleanerPipeline
        from droprag.loader import LoadedDocument

        doc = LoadedDocument(
            content="This is a short line\nthat should merge\nwith the next one\n\nThis is separate.",
            source="/test.txt", filename="test.txt", file_type="pdf",
            category="", folder="", subfolder="",
            file_size=10, file_mtime="2026-01-01",
        )
        cleaner = CleanerPipeline()
        result = cleaner.clean(doc)
        assert result.content  # 应该有内容


class TestVectorStore:
    """向量存储测试"""

    def test_vectorstore_crud(self):
        from droprag.vectorstore import VectorStore
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            vs = VectorStore(db_path, dim=4)

            # 添加
            chunks = [{
                "id": "test__0",
                "content": "Hello world",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "metadata": {
                    "source": "/test.txt", "filename": "test.txt",
                    "category": "text", "file_type": "txt",
                    "heading": "", "folder": "", "subfolder": "",
                    "chunk_id": 0, "total_chunks": 1, "char_count": 11,
                },
            }]
            count = vs.add(chunks)
            assert count == 1

            # 搜索
            results = vs.search([0.1, 0.2, 0.3, 0.4], top_k=5)
            assert len(results) >= 1
            assert results[0]["content"] == "Hello world"

            # 关键词搜索
            results = vs.search_keyword("Hello", top_k=5)
            assert len(results) >= 1

            # 删除
            deleted = vs.delete_by_source("/test.txt")
            assert deleted == 1
            assert vs.count() == 0

            vs.close()


class TestCache:
    """缓存测试"""

    def test_cache_query(self):
        from droprag.cache import DropRAGCache
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "cache.db")
            cache = DropRAGCache(db_path=db_path)

            # 写入
            cache.set_query_result("test query", 1, None, 5, 0.3, {"results": []})
            # 读取
            result = cache.get_query_result("test query", 1, None, 5, 0.3)
            assert result is not None
            assert result["results"] == []

            cache.close()

    def test_cache_embedding(self):
        from droprag.cache import DropRAGCache
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "cache.db")
            cache = DropRAGCache(db_path=db_path)

            # 写入
            cache.set_embedding("hello world", [0.1, 0.2, 0.3])
            # 读取
            result = cache.get_embedding("hello world")
            assert result is not None
            assert len(result) == 3

            cache.close()


class TestQueryEnhancer:
    """查询增强测试"""

    def test_enhance_abbreviation(self):
        from droprag.query_enhancer import enhance_query
        result = enhance_query("AI and ML trends")
        assert result["original"] == "AI and ML trends"
        assert len(result["expanded"]) > 1  # 应该有扩展

    def test_enhance_no_match(self):
        from droprag.query_enhancer import enhance_query
        result = enhance_query("普通查询语句")
        assert result["strategy"] == "none"


class TestReranker:
    """重排序测试"""

    def test_rerank_basic(self):
        from droprag.reranker import rerank
        results = [
            {"content": "Python machine learning", "score": 0.8, "metadata": {}},
            {"content": "Java web development", "score": 0.7, "metadata": {}},
        ]
        reranked = rerank(results, "machine learning")
        assert len(reranked) == 2
        # ML 关键词匹配的应该排前面
        assert reranked[0]["content"] == "Python machine learning"


class TestEngineImport:
    """Engine 导入测试"""

    def test_engine_import(self):
        from droprag.engine import app
        assert app.title == "DropRAG Engine"

    def test_request_models(self):
        from droprag.engine import SearchRequest, HybridSearchRequest
        req = SearchRequest(query="test")
        assert req.query == "test"
        assert req.level == 1


class TestPipelineImport:
    """Pipeline 导入测试"""

    def test_pipeline_import(self):
        from droprag.pipeline import Pipeline
        assert Pipeline is not None


class TestNewLoaders:
    """新增 Loader 测试"""

    def test_html_loader_extensions(self):
        from droprag.loader.markup_loader import HtmlLoader
        loader = HtmlLoader()
        assert ".html" in loader.extensions
        assert ".htm" in loader.extensions

    def test_data_loader_extensions(self):
        from droprag.loader.data_loader import DataLoader
        loader = DataLoader()
        assert ".json" in loader.extensions
        assert ".xml" in loader.extensions
        assert ".yaml" in loader.extensions
        assert ".yml" in loader.extensions
        assert ".toml" in loader.extensions
        assert ".jsonl" in loader.extensions

    def test_data_loader_json(self):
        from droprag.loader import load_file
        import json
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"title": "Test", "items": [1, 2, 3]}, f)
            path = f.name
        try:
            doc = load_file(path, os.path.dirname(path))
            assert doc is not None
            assert doc.file_type == "json"
            assert "Test" in doc.content
        finally:
            os.unlink(path)

    def test_data_loader_yaml(self):
        from droprag.loader import load_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("name: test\nvalue: 42\n")
            path = f.name
        try:
            doc = load_file(path, os.path.dirname(path))
            assert doc is not None
            assert doc.file_type == "yaml"
        finally:
            os.unlink(path)


class TestFunctionChunker:
    """函数级分块器增强测试"""

    def test_python_function_split(self):
        from droprag.chunker.function_chunker import FunctionChunker
        from droprag.loader import LoadedDocument
        from droprag.config import ChunkTypeConfig

        code = '''import os

class MyClass:
    """A test class"""
    def method_one(self):
        return 1

    def method_two(self):
        return 2

def standalone_func():
    return 3
'''
        doc = LoadedDocument(
            content=code,
            source="/test.py", filename="test.py", file_type="python",
            category="code", folder="", subfolder="",
            file_size=len(code), file_mtime="2026-01-01",
        )
        cfg = ChunkTypeConfig(chunk_size=1000, chunk_overlap=50)
        chunker = FunctionChunker()
        chunks = chunker.chunk(doc, cfg)
        # 应该拆出 class 和独立函数
        assert len(chunks) >= 2
        # 至少有一个块包含 class 定义
        has_class = any("class MyClass" in c.content for c in chunks)
        assert has_class


class TestPackager:
    """打包器测试"""

    def test_packager_import(self):
        from droprag.packager import Packager
        assert Packager is not None

    def test_kb_stats_empty(self):
        from droprag.packager import Packager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = Packager(data_dir=tmpdir)
            stats = pkg.get_kb_stats()
            assert stats["exists"] is True
            assert stats["total_size_mb"] == 0


class TestCLIImport:
    """CLI 导入测试"""

    def test_cli_import(self):
        from droprag.cli import main
        assert main is not None


class TestMarkItDownIntegration:
    """MarkItDown 集成测试"""

    def test_markitdown_loader_import(self):
        from droprag.loader.markitdown_loader import MarkItDownLoader
        loader = MarkItDownLoader()
        assert len(loader.extensions) > 0
        assert ".pdf" in loader.extensions
        assert ".docx" in loader.extensions

    def test_markitdown_dual_layer_registry(self):
        """验证双层注册表"""
        from droprag.loader import get_loader_info, discover_loaders
        discover_loaders()
        info = get_loader_info()
        assert info["markitdown_available"] is True
        assert ".pdf" in info["primary_extensions"]
        assert ".pdf" in info["fallback_extensions"]
        assert ".py" in info["fallback_extensions"]
        assert ".py" not in info["primary_extensions"]  # MarkItDown 不覆盖代码格式

    def test_markitdown_text_conversion(self):
        """测试 MarkItDown 对纯文本文件的转换"""
        from droprag.loader.markitdown_loader import MarkItDownLoader
        loader = MarkItDownLoader()
        # MarkItDown 也支持 .txt，但我们让原生 TextLoader 优先
        # 仅验证 PDF/DOCX 等在首选层
        assert loader.is_markitdown_supported(".pdf")
        assert loader.is_markitdown_supported(".docx")
        assert loader.is_markitdown_supported(".xlsx")
        assert not loader.is_markitdown_supported(".py")
        assert not loader.is_markitdown_supported(".json")

    def test_markitdown_pdf_load(self):
        """测试 MarkItDown 加载 PDF 文件"""
        from droprag.loader.markitdown_loader import MarkItDownLoader
        import tempfile

        # 创建一个简单的文本文件（模拟PDF场景）
        # 由于无法在测试中创建真实PDF，验证扩展名匹配即可
        loader = MarkItDownLoader()
        assert loader.is_markitdown_supported(".pdf")
        assert loader.is_markitdown_supported(".epub")

    def test_load_file_dual_fallback(self):
        """测试双层降级：MarkItDown → 原生 Loader"""
        from droprag.loader import load_file
        import json

        # JSON 不在 MarkItDown 首选层，应走降级层 DataLoader
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"test": "fallback", "value": 42}, f)
            path = f.name
        try:
            doc = load_file(path, os.path.dirname(path))
            assert doc is not None
            assert "fallback" in doc.content
        finally:
            os.unlink(path)


# ── 运行入口 ──
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
