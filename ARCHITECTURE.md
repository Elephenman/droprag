# DropRAG 系统架构设计

> 架构师：高见远（Gao） | 基于 PRD/设计方案 v1.0 | 2026-05-24

---

## 一、架构总览

```
┌──────────────────────────────────────────────────────────┐
│                    Entry Points                          │
│  ┌────────┐  ┌─────────────────┐  ┌──────────────────┐  │
│  │  CLI   │  │  FastAPI Engine │  │  (GUI P2: 未来)  │  │
│  └───┬────┘  └────────┬────────┘  └──────────────────┘  │
│      └────────────────┼─────────────────────┘           │
└───────────────────────┼──────────────────────────────────┘
                        │
              ┌─────────▼─────────┐
              │   Pipeline Engine  │
              │   (统一处理管线)    │
              └─────────┬─────────┘
                        │
    ┌───────────┬───────┴───────┬───────────┬───────────┐
    ▼           ▼               ▼           ▼           ▼
┌────────┐ ┌─────────┐ ┌────────────┐ ┌─────────┐ ┌───────┐
│Classify│ │  Clean  │ │Load+Chunk  │ │ Embed   │ │ Store │
│分类器   │ │ 清洗器  │ │加载+分块    │ │编码器   │ │向量库  │
└────────┘ └─────────┘ └────────────┘ └─────────┘ └───────┘
                        │
              ┌─────────▼─────────┐
              │  Hot Folder Watch │
              │  (watchdog+防抖)  │
              └───────────────────┘
```

**核心设计原则**：
1. **插件化**：Loader / Chunker 均为可插拔插件，自动发现注册
2. **管线化**：Pipeline 串联 Classify → Clean → Load → Chunk → Embed → Store
3. **零配置优先**：默认值覆盖 90% 场景，用户不改配置就能跑
4. **bioRAG 核心复用**：vectorstore / cache / embedder / watcher / logging 原样复用

---

## 二、文件列表与职责

### 项目根目录

| 文件 | 来源 | 职责 |
|:-----|:-----|:-----|
| `pyproject.toml` | 新建 | 项目元数据、依赖、CLI入口 |
| `requirements.txt` | 新建 | pip 兼容依赖清单 |
| `config.yaml` | 新建 | 默认配置模板 |
| `Dockerfile` | 改编自bioRAG | 多阶段 Docker 构建 |
| `docker-compose.yml` | 改编自bioRAG | Docker Compose |
| `README.md` | 新建 | 项目文档 |

### dropRAG/ 包

| 文件 | 来源 | 复用度 | 职责 |
|:-----|:-----|:-------|:-----|
| `__init__.py` | 新建 | - | 包初始化，版本号 |
| `config.py` | 改编自bioRAG | 80% | pydantic-settings 配置，去掉生信硬编码，增加auto嵌入 |
| `pipeline.py` | **新建** | - | 统一处理管线引擎，串联6步 |
| `classifier.py` | **新建** | - | 文件自动分类（扩展名+内容嗅探） |
| `cleaner.py` | **新建** | - | 数据清洗管线（去水印/去页眉/OCR/表格提取） |
| `vectorstore.py` | 复制自bioRAG | 95% | sqlite-vec 向量存储，去掉生信metadata |
| `cache.py` | 复制自bioRAG | 95% | SQLite 持久缓存 |
| `embedder.py` | 改编自bioRAG | 90% | 多后端编码器 + auto-detect 逻辑 |
| `indexer.py` | 改编自bioRAG | 80% | 统一索引管理，接入 pipeline |
| `watcher.py` | 改编自bioRAG | 85% | 热文件夹监控，扩展支持更多文件类型 |
| `engine.py` | 改编自bioRAG | 70% | FastAPI 服务，通用化端点 |
| `reranker.py` | 改编自bioRAG | 80% | 上下文感知重排序，通用化权重 |
| `query_enhancer.py` | **重写** | 20% | 通用查询扩展（拼写纠错/缩写展开，去掉生信同义词） |
| `quality_feedback.py` | 改编自bioRAG | 70% | 检索质量反馈，通用化建议 |
| `metadata.py` | 改编自bioRAG | 90% | SQLite 元数据管理，微调 schema |
| `search_log.py` | 复制自bioRAG | 95% | 检索日志记录 |
| `logging.py` | 复制自bioRAG | 100% | 统一日志 |
| `cli.py` | 改编自bioRAG | 80% | CLI 入口，增加 `init` 命令 |
| `packager.py` | **新建** | - | 一键打包/分享（P1） |

### dropRAG/loader/ 插件化加载器

| 文件 | 职责 | 优先级 |
|:-----|:-----|:-------|
| `__init__.py` | LoaderBase 基类 + 自动发现注册 | P0 |
| `text_loader.py` | .txt / .log 纯文本 | P0 |
| `markdown_loader.py` | .md / .rst 标记文档 | P0 |
| `pdf_loader.py` | .pdf (pypdf + PyMuPDF 双引擎) | P0 |
| `docx_loader.py` | .docx (python-docx) | P0 |
| `xlsx_loader.py` | .xlsx / .xls (openpyxl) | P0 |
| `csv_loader.py` | .csv (csv + 编码检测) | P0 |
| `code_loader.py` | .py / .js / .ts / .r / .R 代码文件 | P0 |
| `notebook_loader.py` | .ipynb Jupyter笔记本 | P1 |
| `pptx_loader.py` | .pptx (python-pptx) | P0 |
| `markup_loader.py` | .html / .htm (BeautifulSoup) | P2 |
| `data_loader.py` | .json / .jsonl / .xml / .yaml / .toml | P1 |
| `image_loader.py` | .png / .jpg 图片 (OCR/VLM) | P2 |
| `epub_loader.py` | .epub (ebooklib) | P2 |

### dropRAG/chunker/ 插件化分块器

| 文件 | 职责 | 优先级 |
|:-----|:-----|:-------|
| `__init__.py` | ChunkerBase 基类 + 自动发现注册 | P0 |
| `semantic_chunker.py` | 通用语义分块（递归分隔符） | P0 |
| `heading_chunker.py` | 标题级分块（MD/RST/DOCX） | P0 |
| `row_chunker.py` | 行级分块（XLSX/CSV表格） | P0 |
| `slide_chunker.py` | 幻灯片级分块（PPTX） | P0 |
| `page_chunker.py` | 页级分块（PDF） | P0 |
| `function_chunker.py` | 函数级分块（代码） | P1 |

---

## 三、核心数据结构

### LoadedDocument（通用文档对象）

```python
@dataclass
class LoadedDocument:
    content: str           # 纯文本内容
    source: str            # 完整文件路径
    filename: str          # 文件名
    file_type: str         # 扩展名（不含点）
    category: str          # 自动分类结果（如 academic_paper / spreadsheet / code...）
    folder: str            # 一级文件夹
    subfolder: str         # 二级文件夹
    file_size: int         # 字节数
    file_mtime: str        # 修改时间ISO
    heading: str = ""      # 首个标题
    tables: List[str] = None  # 提取的表格（结构化文本）
    images: List[dict] = None # 图片信息 [{page, path, description}]
```

### Chunk（分块结果）

```python
@dataclass
class Chunk:
    content: str
    metadata: Dict[str, Any]  # source/filename/category/file_type/heading/...
```

---

## 四、接口设计（类图）

```
┌────────────────────────┐
│      LoaderBase        │
│────────────────────────│
│ + extensions: List[str]│
│ + load(path, base) → LoadedDocument │
│────────────────────────│
│ 类方法: discover()     │
└────────────────────────┘
          ▲
    ┌─────┼──────┬───────┬────────┐
    │     │      │       │        │
PdfLoader DocxLoader XlsxLoader ... TextLoader

┌────────────────────────┐
│      ChunkerBase       │
│────────────────────────│
│ + file_types: List[str]│
│ + chunk(doc, cfg) → List[Chunk] │
│────────────────────────│
│ 类方法: discover()     │
└────────────────────────┘
          ▲
    ┌─────┼──────┬──────────┬──────────┐
    │     │      │          │          │
Semantic Heading   Row      Slide     Page
Chunker  Chunker  Chunker  Chunker   Chunker

┌────────────────────────┐
│      FileClassifier    │
│────────────────────────│
│ + classify(path) → str │
│ + get_category(ext, content) → str │
└────────────────────────┘

┌────────────────────────┐
│    CleanerPipeline     │
│────────────────────────│
│ + clean(doc) → LoadedDocument │
│ + _steps_for_type(file_type) → List[Callable] │
└────────────────────────┘

┌────────────────────────┐
│        Pipeline        │
│────────────────────────│
│ + process_file(path) → Dict │
│ + process_all() → Dict     │
│ 流程: Classify→Clean→Load→Chunk→Embed→Store │
└────────────────────────┘
```

---

## 五、程序调用流程（时序图）

### 5.1 单文件处理流程

```
用户拖入文件 → HotFolder检测
    │
    ▼
Watcher.on_created(filepath)
    │
    ▼
Pipeline.process_file(filepath)
    │
    ├─1─→ Classifier.classify(filepath) → category
    │
    ├─2─→ CleanerPipeline.clean(doc) → cleaned_doc
    │
    ├─3─→ LoaderRegistry.load(filepath) → LoadedDocument
    │
    ├─4─→ ChunkerRegistry.chunk(doc, cfg) → List[Chunk]
    │
    ├─5─→ Embedder.encode(texts) → List[Vector]
    │
    └─6─→ VectorStore.add(chunks) → indexed
```

### 5.2 检索流程

```
用户查询 → Engine /search
    │
    ▼
QueryEnhancer.enhance(query) → expanded
    │
    ▼
Embedder.encode_single(query) → query_vector
    │
    ▼
VectorStore.search/hybrid_search → raw_results
    │
    ▼
Reranker.rerank(results, query) → ranked
    │
    ▼
QualityFeedback.analyze(query, results) → hints
    │
    ▼
返回 JSON
```

---

## 六、任务分解（按实现顺序）

### T1: 项目骨架 + pyproject.toml
- 创建目录结构
- pyproject.toml（依赖分组）
- requirements.txt
- `__init__.py`

### T2: 复用模块迁移（改包名）
- `logging.py` → 原样复制，改 biorag → droprag
- `cache.py` → 原样复制，改 biorag → droprag
- `vectorstore.py` → 复制，去掉生信 metadata 字段（category 留作通用分类）
- `search_log.py` → 原样复制
- `metadata.py` → 复制，微调 schema

### T3: 配置模块 config.py
- 改编自 bioRAG
- 去掉 categories 硬编码、ChunkTypeConfig 生信字段
- 增加 PipelineConfig、ClassifierConfig
- 去掉 r_code chunking 配置，增加通用 file_type chunking 映射

### T4: 文件分类器 classifier.py
- 新建，基于扩展名的分类引擎
- 10 大分类规则
- 内容嗅探（PDF 关键词检测学术论文）

### T5: 数据清洗器 cleaner.py
- 新建，按文件类型组合清洗步骤
- PDF: 去水印/去页眉页脚/合并碎片
- DOCX: 去修订/提取表格
- XLSX: 去空行/展开合并单元格
- PPTX: 提取备注/表格
- 通用: 去空白/Unicode标准化

### T6: 插件化 Loader 系统 loader/
- `__init__.py`: LoaderBase + LoaderRegistry 自动发现
- P0 加载器: text/markdown/pdf/docx/xlsx/csv/code/pptx
- P1 加载器: notebook
- 统一输出 LoadedDocument

### T7: 插件化 Chunker 系统 chunker/
- `__init__.py`: ChunkerBase + ChunkerRegistry 自动发现
- P0 分块器: semantic/heading/row/slide/page
- P1 分块器: function
- 每种分块器声明支持的 file_types

### T8: Embedder 适配 embedder.py
- 改编自 bioRAG
- 增加 auto-detect 逻辑
- 保留 local/onnx/api 三后端

### T9: 统一管线 pipeline.py
- 新建
- 串联 Classify → Clean → Load → Chunk → Embed → Store
- process_file() / process_all()
- 与 Indexer 集成

### T10: 索引管理器 indexer.py
- 改编自 bioRAG
- 接入 Pipeline 处理流程
- 保留 build_all / incremental_update / process_file

### T11: 热文件夹监控 watcher.py
- 改编自 bioRAG
- 扩展支持文件类型到 15+ 种
- 增加归档回调

### T12: 查询增强 + 重排序 + 质量反馈
- query_enhancer.py: 重写为通用版（去生信同义词，加拼写纠错）
- reranker.py: 改编，通用化权重
- quality_feedback.py: 改编，通用化建议

### T13: FastAPI Engine engine.py
- 改编自 bioRAG
- 通用化端点
- 增加 /classify（文件分类测试）/ /pipeline/status 端点

### T14: CLI cli.py
- 改编自 bioRAG
- 增加 `init` 命令（交互式引导）
- 保留 serve / build 命令

### T15: 配置模板 + Docker + README
- config.yaml 默认模板
- Dockerfile 多阶段构建
- docker-compose.yml
- README.md 专业文档

---

## 七、依赖包列表

### 核心依赖（必须）
```
fastapi>=0.100.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
sqlite-vec>=0.1.6
numpy>=1.24.0
watchdog>=3.0.0
pyyaml>=6.0
chardet>=5.0.0          # 编码检测（CSV/文本）
```

### 可选依赖分组
```toml
[project.optional-dependencies]
pdf = ["pypdf>=3.0.0", "PyMuPDF>=1.23.0"]
office = ["python-docx>=0.8.11", "openpyxl>=3.1.0", "python-pptx>=0.6.21"]
ocr = ["pytesseract>=0.3.10", "Pillow>=10.0.0"]
epub = ["ebooklib>=0.18"]
html = ["beautifulsoup4>=4.12.0", "lxml>=4.9.0"]
onnx = ["onnxruntime>=1.16.0"]
torch = ["sentence-transformers>=2.2.0", "torch>=2.0.0"]
api = ["httpx>=0.25.0"]
viz = ["umap-learn>=0.5.0", "scikit-learn>=1.3.0"]
all-loaders = ["droprag[pdf,office,html]"]
all = ["droprag[pdf,office,ocr,epub,html,onnx,api,viz]"]
dev = ["pytest>=7.0.0", "pytest-asyncio>=0.21.0", "httpx>=0.25.0"]
```

---

## 八、共享知识（跨文件约定）

1. **包名**：`droprag`（全小写，import 时用 `from droprag.xxx import yyy`）
2. **日志**：统一用 `from droprag.logging import get_logger` + `log = get_logger(__name__)`
3. **配置**：环境变量前缀 `DROPRAG_`（如 `DROPRAG_ENGINE_PORT=8766`）
4. **数据目录**：默认 `./data/`，含 droprag.db / metadata.db / cache.db / search_logs.db
5. **向量维度**：默认 512（bge-small-zh-v1.5），auto 模式根据模型自动调整
6. **分类字段**：chunk_meta.category 存储自动分类结果（如 academic_paper/spreadsheet/code...）
7. **Loader 注册**：每个 Loader 子类声明 `extensions` 类属性，LoaderRegistry 自动发现
8. **Chunker 注册**：每个 Chunker 子类声明 `file_types` 类属性，ChunkerRegistry 自动发现
9. **默认端口**：8766（避免与 bioRAG 的 8765 冲突）
10. **兼容性**：保留 bioRAG 的旧配置格式兼容逻辑

---

## 九、待明确事项

1. OCR 引擎选择：pytesseract vs PaddleOCR？P2 阶段再定，先 pytesseract
2. GUI 框架：PySide6 vs Web UI？P2 阶段再定
3. 是否支持网络路径（SMB/NFS）？暂不支持
4. 文件大小上限？默认 100MB，超过跳过
5. 中文分词增强：jieba？P1 考虑
