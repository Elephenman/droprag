"""DropRAG CLI 入口

Usage:
    droprag init [--dir DIR]
    droprag serve [--host HOST] [--port PORT] [--config CONFIG]
    droprag build [--config CONFIG] [--force]
"""

import argparse
import sys
import os


def main():
    parser = argparse.ArgumentParser(
        prog="droprag",
        description="DropRAG - Drop files, build your personal RAG knowledge base",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # init 命令
    init_parser = subparsers.add_parser("init", help="初始化 DropRAG 项目")
    init_parser.add_argument("--dir", default="./knowledge", help="知识库目录 (默认: ./knowledge)")
    init_parser.add_argument("--config", default="config.yaml", help="配置文件路径")

    # serve 命令
    serve_parser = subparsers.add_parser("serve", help="启动 RAG 服务")
    serve_parser.add_argument("--host", default=None, help="监听地址 (默认: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=None, help="监听端口 (默认: 8766)")
    serve_parser.add_argument("--config", default="config.yaml", help="配置文件路径")

    # build 命令
    build_parser = subparsers.add_parser("build", help="构建向量索引")
    build_parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    build_parser.add_argument("--force", action="store_true", help="强制全量重建")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "init":
        _cmd_init(args)
    elif args.command == "serve":
        _cmd_serve(args)
    elif args.command == "build":
        _cmd_build(args)


def _cmd_init(args):
    """初始化项目"""
    kb_dir = os.path.abspath(args.dir)
    config_path = args.config

    # 创建知识库目录
    os.makedirs(kb_dir, exist_ok=True)
    print(f"知识库目录已创建: {kb_dir}")

    # 创建默认配置
    config_content = f"""knowledge_base:
  path: "{kb_dir.replace(chr(92), '/')}"
  watch:
    enabled: true
    debounce_seconds: 3.0

data:
  dir: "./data"

embedding:
  provider: "auto"
  model: "BAAI/bge-small-zh-v1.5"
  device: "cpu"
  dimension: 512
  batch_size: 32
  model_cache_dir: "./models"

chunking:
  default:
    chunk_size: 500
    chunk_overlap: 100
  markdown:
    chunk_size: 500
    chunk_overlap: 100
  pdf:
    chunk_size: 500
    chunk_overlap: 100
  code:
    chunk_size: 800
    chunk_overlap: 150
  spreadsheet:
    chunk_size: 300
    chunk_overlap: 0
  presentation:
    chunk_size: 1000
    chunk_overlap: 50

retrieval:
  level_1:
    top_k: 3
    max_chars_per_chunk: 200
    max_total_chars: 600
  level_2:
    top_k: 8
    max_chars_per_chunk: 300
    max_total_chars: 2500
  level_3:
    top_k: 5

pipeline:
  max_file_size_mb: 100
  enable_cleaning: true
  enable_classification: true

engine:
  host: "127.0.0.1"
  port: 8766
  log_level: "INFO"

logging:
  level: "INFO"
  file: "./data/droprag.log"

cache:
  enabled: true
  max_query_cache: 100
  query_ttl_seconds: 3600
  max_embedding_cache: 5000
  embedding_ttl_seconds: 86400
"""

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_content)
    print(f"配置文件已创建: {config_path}")

    # 创建数据目录
    os.makedirs("./data", exist_ok=True)
    os.makedirs("./models", exist_ok=True)

    print(f"""
DropRAG 项目已初始化！

下一步:
  1. 将文件拖入 {kb_dir}
  2. 运行: droprag build --config {config_path}
  3. 启动: droprag serve --config {config_path}
  4. 搜索: curl -X POST http://localhost:8766/search -H "Content-Type: application/json" -d '{{"query": "你的问题"}}'
""")


def _cmd_serve(args):
    """启动服务"""
    os.environ["DROPRAG_CONFIG"] = args.config
    from droprag.config import load_config
    config = load_config(args.config)
    host = args.host or config.engine.host
    port = args.port or config.engine.port

    import uvicorn
    from droprag.engine import app
    uvicorn.run(app, host=host, port=port)


def _cmd_build(args):
    """构建索引"""
    from droprag.config import load_config
    from droprag.indexer import Indexer
    from droprag.embedder import create_embedder
    from droprag.vectorstore import VectorStore
    from droprag.metadata import MetadataDB
    from droprag.logging import setup_logging

    config = load_config(args.config)
    setup_logging(config.logging.level, config.logging.file)

    data_dir = os.path.abspath(config.data.dir)
    os.makedirs(data_dir, exist_ok=True)

    embedder = create_embedder(config.embedding)
    vectorstore = VectorStore(os.path.join(data_dir, "droprag.db"), config.embedding.dimension)
    metadata_db = MetadataDB(os.path.join(data_dir, "metadata.db"))

    indexer = Indexer(config, embedder, vectorstore, metadata_db)
    result = indexer.build_all() if args.force else indexer.incremental_update()
    print(f"构建结果: {result}")

    metadata_db.close()


if __name__ == "__main__":
    main()
