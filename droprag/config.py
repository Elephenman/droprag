"""DropRAG 配置模块 - Pydantic Settings

使用 pydantic-settings 从 YAML / 环境变量加载配置。
环境变量前缀: DROPRAG_ (如 DROPRAG_ENGINE_PORT=8766)
"""

import os
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class EmbeddingConfig(BaseModel):
    """Embedding 模型配置"""
    provider: str = "auto"           # auto | local | onnx | api
    model: str = "BAAI/bge-small-zh-v1.5"
    device: str = "cpu"
    dimension: int = Field(default=512, ge=1)
    batch_size: int = Field(default=32, ge=1)
    model_cache_dir: str = "./models"
    api_url: Optional[str] = None
    api_key: Optional[str] = None


class ChunkTypeConfig(BaseModel):
    """单个分块类型配置"""
    chunk_size: int = Field(default=500, ge=50)
    chunk_overlap: int = Field(default=100, ge=0)
    separators: List[str] = Field(default_factory=lambda: ["\n\n", "\n", " "])


class ChunkingConfig(BaseModel):
    """分块配置汇总 — 通用化，按文件类型"""
    default: ChunkTypeConfig = Field(default_factory=ChunkTypeConfig)
    markdown: ChunkTypeConfig = Field(default_factory=lambda: ChunkTypeConfig(
        separators=["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " "],
    ))
    pdf: ChunkTypeConfig = Field(default_factory=ChunkTypeConfig)
    code: ChunkTypeConfig = Field(default_factory=lambda: ChunkTypeConfig(
        chunk_size=800, chunk_overlap=150,
        separators=["\n# ", "\n\n", "\n"],
    ))
    spreadsheet: ChunkTypeConfig = Field(default_factory=lambda: ChunkTypeConfig(
        chunk_size=300, chunk_overlap=0,
        separators=["\n"],
    ))
    presentation: ChunkTypeConfig = Field(default_factory=lambda: ChunkTypeConfig(
        chunk_size=1000, chunk_overlap=50,
        separators=["\n\n---\n\n", "\n\n", "\n"],
    ))


class RetrievalLevelConfig(BaseModel):
    """检索级别配置"""
    top_k: int = Field(default=3, ge=1)
    max_chars_per_chunk: Optional[int] = None
    max_total_chars: Optional[int] = None


class RetrievalConfig(BaseModel):
    """检索配置汇总"""
    level_1: RetrievalLevelConfig = Field(default_factory=lambda: RetrievalLevelConfig(top_k=3, max_chars_per_chunk=200, max_total_chars=600))
    level_2: RetrievalLevelConfig = Field(default_factory=lambda: RetrievalLevelConfig(top_k=8, max_chars_per_chunk=300, max_total_chars=2500))
    level_3: RetrievalLevelConfig = Field(default_factory=lambda: RetrievalLevelConfig(top_k=5))
    min_similarity: float = Field(default=0.3, ge=0.0, le=1.0)


class EngineConfig(BaseModel):
    """Engine 服务配置"""
    host: str = "127.0.0.1"
    port: int = Field(default=8766, ge=1, le=65535)
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:*", "tauri://localhost"])
    log_level: str = "INFO"
    api_key: Optional[str] = None


class PipelineConfig(BaseModel):
    """管线配置"""
    max_file_size_mb: int = Field(default=100, ge=1)
    enable_cleaning: bool = True
    enable_classification: bool = True
    supported_extensions: List[str] = Field(default_factory=lambda: [
        # 文档
        ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".epub",
        # 表格
        ".xlsx", ".xls", ".csv",
        # 代码
        ".py", ".js", ".ts", ".r", ".R", ".ipynb",
        # 标记
        ".md", ".rst", ".html", ".htm",
        # 数据
        ".json", ".jsonl", ".xml", ".yaml", ".yml", ".toml",
        # 图片
        ".png", ".jpg", ".jpeg", ".bmp",
        # 纯文本
        ".txt", ".log",
    ])


class UmapConfig(BaseModel):
    """UMAP 可视化配置"""
    n_neighbors: int = Field(default=15, ge=2)
    min_dist: float = Field(default=0.1, ge=0.0, le=1.0)
    metric: str = "cosine"
    cache_enabled: bool = True
    cache_max_age_hours: int = 24


class VisualizationConfig(BaseModel):
    """可视化配置汇总"""
    umap: UmapConfig = Field(default_factory=UmapConfig)


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    file: str = "./data/droprag.log"
    max_size_mb: int = Field(default=50, ge=1)
    backup_count: int = Field(default=3, ge=0)


class CacheConfig(BaseModel):
    """缓存配置"""
    enabled: bool = True
    max_query_cache: int = Field(default=100, ge=1)
    query_ttl_seconds: int = Field(default=3600, ge=0)
    max_embedding_cache: int = Field(default=5000, ge=1)
    embedding_ttl_seconds: int = Field(default=86400, ge=0)


class WatchConfig(BaseModel):
    """文件监控配置"""
    enabled: bool = True
    debounce_seconds: float = Field(default=3.0, ge=0.5)
    extra_dirs: List[str] = Field(default_factory=list)
    ignore: List[str] = Field(default_factory=lambda: [
        ".git", ".obsidian", ".trash", "__pycache__", "*.tmp", "*.bak", "*.swp", "*.lock",
    ])


class KnowledgeBaseConfig(BaseModel):
    """知识库配置"""
    path: str = ""
    watch: WatchConfig = Field(default_factory=WatchConfig)
    ignore: List[str] = Field(default_factory=lambda: [".git", ".obsidian", ".trash", "*.tmp", "*.bak", "*/.*"])


class DataConfig(BaseModel):
    """数据目录配置"""
    dir: str = "./data"


class DropRAGConfig(BaseSettings):
    """DropRAG 主配置"""
    knowledge_base: KnowledgeBaseConfig = Field(default_factory=KnowledgeBaseConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    engine: EngineConfig = Field(default_factory=EngineConfig)
    visualization: VisualizationConfig = Field(default_factory=VisualizationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)

    model_config = {
        "env_prefix": "DROPRAG_",
        "env_nested_delimiter": "__",
    }


def load_config(path: str = "config.yaml") -> DropRAGConfig:
    """从 YAML 文件加载配置"""
    import yaml

    if not os.path.exists(path):
        return DropRAGConfig()

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # 兼容旧配置格式
    kb = raw.get("knowledge_base", {})
    if "watch" in kb and isinstance(kb["watch"], bool):
        watch_enabled = kb.pop("watch")
        kb["watch"] = {"enabled": watch_enabled}
    if "ignore" in kb and isinstance(kb["ignore"], list):
        ignore_list = kb.pop("ignore")
        if "watch" not in kb:
            kb["watch"] = {}
        kb["watch"]["ignore"] = ignore_list
        kb["ignore"] = ignore_list

    return DropRAGConfig(**raw)
