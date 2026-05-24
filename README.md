<div align="center">

# 📂 DropRAG

**Drop files, build your personal RAG — one click, zero config**

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/Elephenman/droprag)
[![Python](https://img.shields.io/badge/python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![VectorDB](https://img.shields.io/badge/vector_db-sqlite--vec-orange.svg)](https://github.com/asg017/sqlite-vec)
[![Framework](https://img.shields.io/badge/framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![File Types](https://img.shields.io/badge/file_types-15%2B-purple.svg)](#-supported-file-types)

拖入文件，自动分类 → 清洗 → 加载 → 分块 → 编码 → 存储。15+ 文件类型，插件化架构，零配置启动。

[快速开始](#-快速开始) · [API 文档](#-api-文档) · [插件开发](#-插件开发) · [配置指南](#-配置指南) · [Docker 部署](#-docker-部署)

</div>

---

## ✨ 核心特性

| 特性 | 描述 |
|:-----|:-----|
| 📂 **拖入即索引** | 文件拖入监控文件夹，3 秒防抖自动触发：分类 → 清洗 → 加载 → 分块 → 编码 → 存储 |
| 🏷️ **自动分类** | 10 大分类（学术论文 / 表格 / 代码 / PPT / 标记 / 结构化数据...），扩展名 + 内容嗅探 |
| 🧩 **插件化架构** | Loader / Chunker 均为可插拔插件，声明式注册，自动发现 |
| 📄 **15+ 文件类型** | PDF / DOCX / XLSX / PPTX / CSV / MD / HTML / JSON / XML / YAML / Code / IPYNB / TXT / TOML / JSONL |
| ⚡ **超轻量** | sqlite-vec 替代 ChromaDB，核心依赖 <1MB 向量库 |
| 🧠 **Auto Embedding** | 自动检测 GPU→local / onnxruntime→ONNX / Ollama→API / 兜底→torch |
| 🔄 **混合检索** | 语义搜索 + 关键词搜索 RRF 融合排序 |
| 🎯 **智能分块** | 语义分块 / 标题分块 / 行级分块 / 幻灯片分块 / 页级分块 / 函数级分块 |
| 🧹 **数据清洗** | PDF 去水印/去页眉、DOCX 去修订/提取表格、XLSX 去空行/展开合并单元格 |
| 📦 **一键打包** | 知识库导出为 .zip，跨设备迁移只需一行命令 |
| 🐳 **Docker 就绪** | 一键 Docker Compose 启动，零配置部署 |

---

## 🏗️ 架构概览

```
                          ┌─────────────┐
                          │  Entry Point │
                          │ CLI / Engine │
                          └──────┬──────┘
                                 │
                      ┌──────────▼──────────┐
                      │      Pipeline       │
                      │  (6-Step Orchestrator)│
                      └──────────┬──────────┘
                                 │
    ┌────────┬────────┬──────────┼──────────┬────────┬────────┐
    ▼        ▼        ▼          ▼          ▼        ▼        ▼
┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐
│Classify││ Clean  ││  Load  ││ Chunk  ││ Embed  ││ Store  ││ Watch  │
│10 类   ││ 6 种   ││ 11 个  ││ 6 个   ││ 3 后端 ││sqlite- ││hot     │
│分类器  ││清洗器  ││Loader  ││Chunker ││+ auto  ││vec     ││folder  │
└────────┘└────────┘└────────┘└────────┘└────────┘└────────┘└────────┘
```

**核心管线流程**：

```
文件拖入 → Watcher 检测 → Pipeline.process_file()
  ├─ 1. Classifier.classify()    →  自动分类 (academic_paper / spreadsheet / code ...)
  ├─ 2. CleanerPipeline.clean()  →  数据清洗 (去水印/去空行/提取表格)
  ├─ 3. LoaderRegistry.load()    →  加载文件 (11 种 Loader 按扩展名匹配)
  ├─ 4. ChunkerRegistry.chunk()  →  智能分块 (6 种 Chunker 按文件类型匹配)
  ├─ 5. Embedder.encode()        →  向量编码 (auto 检测最优后端)
  └─ 6. VectorStore.add()        →  存储 + 索引 (sqlite-vec + 元数据)
```

---

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/Elephenman/droprag.git
cd droprag

# 基础安装（核心功能 + 文本/Markdown/Code 加载）
pip install -e .

# 按需安装可选依赖
pip install -e ".[pdf]"          # PDF 支持
pip install -e ".[office]"       # DOCX / XLSX / PPTX 支持
pip install -e ".[html]"         # HTML 支持
pip install -e ".[onnx]"         # ONNX 轻量推理
pip install -e ".[all-loaders]"  # 所有文件格式

# 或者一步到位
pip install -e ".[all]"
```

### 三步启动

```bash
# 1. 初始化知识库目录
droprag init --dir ./my-knowledge

# 2. 拖入文件到 ./my-knowledge/ 目录
#    （或手动复制文件）

# 3. 构建索引 + 启动服务
droprag build
droprag serve
```

服务默认运行在 `http://127.0.0.1:8766`，启动后访问 `http://127.0.0.1:8766/docs` 查看交互式 API 文档。

### 热文件夹模式

默认开启文件监控，拖入文件自动触发增量索引：

```bash
# 热文件夹默认开启，3 秒防抖
droprag serve

# 新增/修改/删除文件 → 自动增量更新索引
# 无需手动执行 droprag build
```

---

## 📄 支持的文件类型

| 文件类型 | 扩展名 | Loader | Chunker | 分类 | 可选依赖 |
|:---------|:-------|:-------|:--------|:-----|:---------|
| 纯文本 | .txt .log | TextLoader | SemanticChunker | text | — |
| Markdown | .md .rst | MarkdownLoader | HeadingChunker | markup | — |
| PDF | .pdf | PdfLoader | PageChunker | academic_paper / office_doc | pypdf, PyMuPDF |
| Word | .docx | DocxLoader | SemanticChunker | office_doc | python-docx |
| Excel | .xlsx .xls | XlsxLoader | RowChunker | spreadsheet | openpyxl |
| CSV | .csv | CsvLoader | RowChunker | spreadsheet | — |
| PPT | .pptx | PptxLoader | SlideChunker | presentation | python-pptx |
| 代码 | .py .js .ts .R .java .cpp .go .rs ... | CodeLoader | FunctionChunker | code | — |
| Jupyter | .ipynb | NotebookLoader | SemanticChunker | notebook | — |
| HTML | .html .htm | HtmlLoader | SemanticChunker | markup | beautifulsoup4, lxml |
| JSON | .json .jsonl | DataLoader | SemanticChunker | data | — |
| YAML | .yaml .yml | DataLoader | SemanticChunker | data | pyyaml |
| XML | .xml | DataLoader | SemanticChunker | data | — |
| TOML | .toml | DataLoader | SemanticChunker | data | — |

> 📌 标记为 "—" 的可选依赖表示核心依赖已包含，无需额外安装。

---

## 📡 API 文档

### 检索接口

#### `POST /search` — 语义检索

```bash
curl -X POST http://127.0.0.1:8766/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "如何使用 pandas 读取 Excel",
    "level": 2,
    "top_k": 8,
    "category": "code",
    "min_score": 0.3
  }'
```

**三级检索说明：**

| Level | 场景 | top_k | 每块最大字符 | 总字符上限 |
|:------|:-----|:------|:------------|:-----------|
| 1 | 快速概览 | 3 | 200 | 600 |
| 2 | 标准检索 | 8 | 300 | 2500 |
| 3 | 全文返回 | 5 | 无限制 | 无限制 |

#### `POST /hybrid` — 混合检索（语义 + 关键词 RRF 融合）

```bash
curl -X POST http://127.0.0.1:8766/hybrid \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Python 数据分析",
    "level": 2,
    "semantic_weight": 0.7,
    "keyword_weight": 0.3
  }'
```

#### `POST /search_kw` — 关键词检索

```bash
curl -X POST http://127.0.0.1:8766/search_kw \
  -H "Content-Type: application/json" \
  -d '{"keyword": "CellChat", "max_results": 10}'
```

### 管理接口

| 端点 | 方法 | 说明 |
|:-----|:-----|:-----|
| `/status` | GET | 知识库状态（文档数、块数、模型信息、监控状态） |
| `/update` | POST | 增量更新（`force_rebuild: true` 强制全量重建） |
| `/classify` | POST | 文件分类测试（传入路径，返回分类结果） |
| `/pipeline/status` | GET | Pipeline 处理状态 |
| `/health` | GET | 健康检查 |
| `/events` | GET | SSE 实时事件流 |
| `/kb/stats` | GET | 知识库统计信息 |

### 打包接口

| 端点 | 方法 | 说明 |
|:-----|:-----|:-----|
| `/kb/export` | POST | 导出知识库为 .zip |
| `/kb/import` | POST | 导入知识库 .zip |

### 认证

在 `config.yaml` 中设置 `engine.api_key` 后，所有接口需要通过 `X-API-Key` Header 传递 API Key：

```bash
curl -H "X-API-Key: your-secret-key" http://127.0.0.1:8766/status
```

---

## 🧩 插件开发

### 自定义 Loader

```python
# droprag/loader/my_loader.py
from droprag.loader import LoaderBase, LoadedDocument, register_loader

class MyLoader(LoaderBase):
    extensions = [".myext"]  # 声明支持的扩展名

    def load(self, filepath: str, base_path: str) -> LoadedDocument:
        # 读取文件 → 返回 LoadedDocument
        content = open(filepath, "r").read()
        return LoadedDocument(
            content=content,
            source=filepath,
            filename=os.path.basename(filepath),
            file_type="myext",
            category="custom",
            folder="", subfolder="",
            file_size=os.path.getsize(filepath),
            file_mtime="...",
        )

# 注册
register_loader(MyLoader)
```

### 自定义 Chunker

```python
# droprag/chunker/my_chunker.py
from droprag.chunker import ChunkerBase, Chunk, register_chunker

class MyChunker(ChunkerBase):
    file_types = ["myext", "custom"]  # 声明支持的文件类型

    def chunk(self, doc, cfg) -> list[Chunk]:
        # 自定义分块逻辑
        parts = doc.content.split("\n\n")
        return [Chunk(content=p, metadata={...}) for p in parts if p.strip()]

# 注册
register_chunker(MyChunker)
```

### 插件注册

在 `droprag/loader/__init__.py` 的 `discover_loaders()` 中添加导入即可：

```python
try:
    from droprag.loader.my_loader import MyLoader
    register_loader(MyLoader)
except ImportError:
    pass
```

---

## ⚙️ 配置指南

配置文件为 `config.yaml`，支持环境变量覆盖（`DROPRAG_` 前缀）。

### 核心配置项

```yaml
knowledge_base:
  path: "./my-knowledge"                   # 知识库根目录（拖入文件的目标目录）
  watch:
    enabled: true                           # 热文件夹监控（默认开启）
    debounce_seconds: 3.0                   # 防抖秒数
    ignore: [".git", "__pycache__", "*.tmp"] # 忽略模式
  max_file_size_mb: 100                     # 单文件大小上限（超过跳过）

embedding:
  provider: "auto"                          # auto | local | onnx | api
  model: "BAAI/bge-small-zh-v1.5"          # 模型名称
  dimension: 512                            # 向量维度
  batch_size: 32                            # 编码批大小
  # api_url: "http://localhost:11434/api/embeddings"  # API 模式

pipeline:
  clean: true                               # 是否启用数据清洗
  ocr: false                                # 是否启用 OCR

engine:
  host: "127.0.0.1"
  port: 8766
  api_key: null                             # 设置后启用认证

cache:
  enabled: true
  max_query_cache: 100
  query_ttl_seconds: 3600
  max_embedding_cache: 5000
  embedding_ttl_seconds: 86400
```

### Embedding 后端对比

| 后端 | 依赖大小 | 首次启动 | 推理速度 | 适用场景 |
|:-----|:---------|:---------|:---------|:---------|
| `auto` | 自动选择 | — | — | 推荐，自动检测最优方案 |
| `local` | ~500MB (PyTorch) | 慢（模型下载） | 快 | 有 GPU / 高频使用 |
| `onnx` | ~30MB (ONNX Runtime) | 快 | 较快 | CPU 轻量部署 |
| `api` | <1MB (httpx) | 即时 | 取决于网络 | 有远程 Embedding 服务 |

### 可选依赖分组

```bash
pip install -e ".[pdf]"         # PDF 支持：pypdf + PyMuPDF
pip install -e ".[office]"      # Office：python-docx + openpyxl + python-pptx
pip install -e ".[html]"        # HTML：beautifulsoup4 + lxml
pip install -e ".[onnx]"        # ONNX 推理：onnxruntime
pip install -e ".[torch]"       # PyTorch 推理：sentence-transformers + torch
pip install -e ".[api]"         # 远程 API：httpx
pip install -e ".[all-loaders]" # 所有文件格式：pdf + office + html
pip install -e ".[all]"         # 全部可选依赖
```

---

## 🐳 Docker 部署

```bash
# 一键启动
docker compose up -d

# 自定义配置
docker compose up -d -e DROPRAG_CONFIG=/app/config.yaml
```

`docker-compose.yml` 默认配置：

- 端口映射：`8766:8766`
- 知识库挂载：`./data:/app/data`
- 配置挂载：`./config.yaml:/app/config.yaml`
- 自动重启：`unless-stopped`

---

## 📦 知识库打包

```bash
# CLI 打包
droprag pack --output my-kb.zip

# CLI 导入
droprag unpack --input my-kb.zip --dir ./new-knowledge

# 仅导出元数据（不含向量，更小）
droprag pack --output my-kb-lite.zip --no-embeddings

# 包含源文件
droprag pack --output my-kb-full.zip --include-sources --source-dir ./my-knowledge
```

---

## 📁 项目结构

```
DropRAG/
├── droprag/
│   ├── __init__.py              # 包入口，版本号
│   ├── config.py                # pydantic-settings 配置
│   ├── pipeline.py              # 统一处理管线（6 步串联）
│   ├── classifier.py            # 文件自动分类（10 大类 + 内容嗅探）
│   ├── cleaner.py               # 数据清洗管线（6 种清洗策略）
│   ├── engine.py                # FastAPI 服务（REST API + SSE）
│   ├── cli.py                   # CLI 入口（init / serve / build / pack / unpack）
│   ├── packager.py              # 一键打包/导入
│   ├── indexer.py               # 统一索引器
│   ├── vectorstore.py           # sqlite-vec 向量存储
│   ├── embedder.py              # 多后端 Embedding（auto / local / onnx / api）
│   ├── cache.py                 # SQLite 持久化缓存
│   ├── reranker.py              # 上下文感知重排序
│   ├── query_enhancer.py        # 查询增强
│   ├── quality_feedback.py      # 检索质量反馈
│   ├── watcher.py               # 热文件夹监控（watchdog + asyncio）
│   ├── metadata.py              # SQLite 元数据管理
│   ├── search_log.py            # 检索日志
│   ├── logging.py               # 统一日志框架
│   ├── loader/                  # 插件化加载器
│   │   ├── __init__.py          #   LoaderBase + Registry + 自动发现
│   │   ├── text_loader.py       #   .txt .log
│   │   ├── markdown_loader.py   #   .md .rst
│   │   ├── pdf_loader.py        #   .pdf
│   │   ├── docx_loader.py       #   .docx
│   │   ├── xlsx_loader.py       #   .xlsx
│   │   ├── csv_loader.py        #   .csv
│   │   ├── pptx_loader.py       #   .pptx
│   │   ├── code_loader.py       #   .py .js .ts .R .java ...
│   │   ├── notebook_loader.py   #   .ipynb
│   │   ├── markup_loader.py     #   .html .htm
│   │   └── data_loader.py       #   .json .jsonl .xml .yaml .toml
│   └── chunker/                 # 插件化分块器
│       ├── __init__.py          #   ChunkerBase + Registry + 自动发现
│       ├── semantic_chunker.py  #   通用语义分块
│       ├── heading_chunker.py   #   标题级分块（MD/RST）
│       ├── row_chunker.py       #   行级分块（XLSX/CSV）
│       ├── slide_chunker.py     #   幻灯片级分块（PPTX）
│       ├── page_chunker.py      #   页级分块（PDF）
│       └── function_chunker.py  #   函数级分块（代码）
├── tests/
│   └── test_core.py             # 核心模块测试
├── config.yaml                  # 默认配置模板
├── pyproject.toml               # 项目元数据 + 依赖声明
├── Dockerfile                   # Docker 镜像定义
├── docker-compose.yml           # Docker Compose 编排
├── requirements.txt             # pip 依赖清单
├── ARCHITECTURE.md              # 系统架构设计文档
└── DESIGN_PROPOSAL.md           # 设计方案文档
```

---

## 🔄 版本历史

### v0.1.0 (2026-05-24) — 初始发布

- **6 步管线架构**：Classify → Clean → Load → Chunk → Embed → Store
- **10 大文件分类**：扩展名 + 内容嗅探自动分类
- **11 个 Loader 插件**：PDF / DOCX / XLSX / PPTX / CSV / MD / HTML / JSON / XML / YAML / Code / IPYNB / TXT / TOML
- **6 个 Chunker 插件**：语义 / 标题 / 行级 / 幻灯片 / 页级 / 函数级
- **Auto Embedding**：自动检测 GPU → local / onnxruntime → ONNX / Ollama → API
- **数据清洗管线**：PDF 去水印、DOCX 提取表格、XLSX 展开合并单元格
- **热文件夹监控**：3 秒防抖 + asyncio 线程安全
- **一键打包**：知识库导出/导入 .zip
- **混合检索**：语义 + 关键词 RRF 融合
- **三级检索**：快速摘要 → 标准检索 → 全文返回
- **sqlite-vec**：超轻量向量库，核心依赖 <1MB
- **Docker 部署**：Dockerfile + docker-compose.yml

---

## 🤝 致谢

DropRAG 的向量存储、缓存、Embedding、文件监控等核心模块源自 [BioRAG](https://github.com/Elephenman/BioRAG) 项目，在其基础上进行了通用化改造和架构升级。

---

## 📄 License

[MIT License](LICENSE) © 2026 Ye Yongfeng

---

<div align="center">

**DropRAG** — Drop files, get answers 📂✨

</div>
