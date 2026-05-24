# DropRAG 设计方案

> 让所有人一键搭建专属 RAG — 拖入文件，自动分类、清洗、向量化，实时更新

---

## 一、项目定位

**DropRAG** = Drop + RAG。用户只需把文件拖进一个文件夹，系统自动完成一切。

**核心差异 vs bioRAG**：

| 维度 | bioRAG | DropRAG |
|:-----|:-------|:--------|
| 目标用户 | 生信课题组 | **任何人**（律师、教师、运营、开发者…） |
| 文件类型 | 5种（md/R/pdf/ipynb/py） | **15+种**（+docx/xlsx/pptx/csv/json/xml/html/txt/epub/images…） |
| 文件分类 | 手动配目录映射 | **自动识别 + 智能分类** |
| 数据清洗 | 基本分块 | **深度清洗**（去水印/去页眉页脚/OCR/表格提取/图片描述） |
| 入口 | CLI + API | **桌面 GUI**（系统托盘）+ CLI + API |
| 分享 | 无 | **一键打包**（数据库+元数据+摘要导出） |
| Embedding | 需配置 | **自动选最优**（检测硬件→选模型→下载→缓存） |

---

## 二、bioRAG 可复用资产清单

### ✅ 直接复用（改包名 + 通用化）

| 模块 | 复用度 | 改动 |
|:-----|:-------|:-----|
| `vectorstore.py` (sqlite-vec) | **95%** | 几乎原样复用，去掉生信特化的 metadata 字段 |
| `cache.py` (SQLite持久缓存) | **95%** | 原样复用 |
| `embedder.py` (多后端) | **90%** | 增加 auto-detect 智能选择逻辑 |
| `watcher.py` (热文件夹) | **85%** | 增加文件分类后的归档回调 |
| `config.py` (pydantic-settings) | **80%** | 去掉 categories/分块策略硬编码，改为自动推断 |
| `indexer.py` (统一索引) | **80%** | 去掉生信 category 逻辑，增加文件分类步骤 |
| `engine.py` (FastAPI) | **70%** | 去掉生信特化端点，增加通用管理端点 |
| `logging.py` | **100%** | 原样复用 |
| `cli.py` | **80%** | 增加 `init` 命令（交互式引导创建项目） |
| `metadata.py` / `search_log.py` | **90%** | 微调 schema |

### 🔧 需要重写

| 模块 | 原因 |
|:-----|:-----|
| `loader.py` | **核心重写**：从5种扩展到15+种，增加 docx/xlsx/pptx/csv/json/html/epub/图片OCR |
| `chunker.py` | **大幅改造**：增加表格行级分块、幻灯片级分块、代码函数级分块等策略 |
| `reranker.py` | 通用化：去掉生信硬编码权重，增加可配置权重 |
| `query_enhancer.py` | 去掉生信同义词，改为通用扩展（拼写纠错/缩写展开） |
| `quality_feedback.py` | 通用化 |

### 🆕 全新模块

| 模块 | 功能 |
|:-----|:-----|
| `classifier.py` | **文件自动分类**：基于扩展名+内容+目录结构的智能分类 |
| `cleaner.py` | **数据清洗管线**：去水印、去页眉页脚、OCR、表格提取、图片描述 |
| `gui.py` | **桌面 GUI**：PySide6 系统托盘应用，拖拽文件、状态监控、检索界面 |
| `packager.py` | **一键打包**：数据库+元数据+摘要导出为可分享的 .dropbag 文件 |
| `pipeline.py` | **统一处理管线**：File → Classify → Clean → Chunk → Embed → Store |

---

## 三、系统架构

```
                    ┌─────────────────────────────────────────┐
                    │            DropRAG Desktop              │
                    │  ┌──────────┐  ┌──────────┐  ┌──────┐  │
                    │  │ 系统托盘  │  │  Web UI  │  │ CLI  │  │
                    │  │ (PySide6) │  │(FastAPI) │  │      │  │
                    │  └─────┬────┘  └─────┬────┘  └──┬───┘  │
                    │        └──────────┬──┴──────────┘       │
                    └───────────────────┼─────────────────────┘
                                        │
                              ┌─────────▼─────────┐
                              │   Pipeline Engine  │
                              │  (统一处理管线)      │
                              └─────────┬─────────┘
                                        │
        ┌───────────┬───────────┬───────┴───────┬───────────┬───────────┐
        ▼           ▼           ▼               ▼           ▼           ▼
  ┌──────────┐┌──────────┐┌──────────┐  ┌──────────┐┌──────────┐┌──────────┐
  │Classifier││ Cleaner  ││  Loader  │  │ Chunker  ││ Embedder ││  Store   │
  │文件分类   ││数据清洗   ││文档加载   │  │智能分块   ││多后端编码 ││sqlite-vec│
  └──────────┘└──────────┘└──────────┘  └──────────┘└──────────┘└──────────┘
                                                  │
                                        ┌─────────▼─────────┐
                                        │  Hot Folder Watch  │
                                        │  (watchdog+防抖)   │
                                        └───────────────────┘
```

---

## 四、核心流程

```
用户拖入文件 → HotFolder 检测
                    │
                    ▼
            ┌──────────────┐
            │ 1. Classify  │  扩展名 → 内容嗅探 → 自动归类
            │   文件分类    │  (doc/xls/ppt/pdf/md/code/data/image)
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ 2. Clean     │  去水印/去页眉页脚/去空行
            │   数据清洗    │  图片→OCR/描述 | 表格→结构化 | PDF→段落合并
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ 3. Load      │  按文件类型调用对应 Loader
            │   文档加载    │  统一输出 LoadedDocument
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ 4. Chunk     │  按类型选择分块策略
            │   智能分块    │  MD→标题级 | Code→函数级 | 表格→行级 | PPT→页级
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ 5. Embed     │  自动选最优后端
            │   向量编码    │  GPU→local | CPU→onnx | 无模型→api
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ 6. Store     │  sqlite-vec + FTS5 + 元数据
            │   存储索引    │  缓存embedding + 查询结果
            └──────────────┘
```

---

## 五、文件类型支持矩阵

| 类型 | 扩展名 | Loader | Cleaner | Chunker 策略 | 优先级 |
|:-----|:-------|:-------|:--------|:-------------|:-------|
| **文档** | .pdf | pypdf / PyMuPDF | 去水印、合并碎片段落 | 段落级 + 语义切分 | P0 |
| | .docx | python-docx | 去修订标记、提取表格/图片 | 标题级 + 表格独立块 | P0 |
| | .pptx | python-pptx | 提取备注、表格 | 幻灯片级（每页一块） | P1 |
| | .epub | ebooklib | 去CSS/排版标记 | 章节级 | P2 |
| **表格** | .xlsx / .xls | openpyxl | 去空行、合并单元格展开 | 行级（每行一块+表头） | P0 |
| | .csv | csv模块 | 去空行、编码修复 | 行级 | P0 |
| **代码** | .py / .js / .ts | 文本读取 | 去注释（可选） | 函数/类级 | P1 |
| | .r / .R | 文本读取 | — | 函数级（已有） | P1 |
| | .ipynb | JSON解析 | 去输出（可选） | Cell级 | P1 |
| **标记** | .md / .rst | 文本读取 | — | 标题级（已有） | P0 |
| | .html / .htm | BeautifulSoup | 去标签、提取正文 | 段落级 | P2 |
| **数据** | .json / .jsonl | JSON解析 | — | 对象级/数组级 | P1 |
| | .xml | xml.etree | 去命名空间 | 元素级 | P2 |
| | .yaml / .toml | 对应解析器 | — | 键值级 | P2 |
| **图片** | .png / .jpg / .bmp | OCR / VLM描述 | 降噪（可选） | 整图一块 | P2 |
| **纯文本** | .txt / .log | 文本读取 | 去空行 | 段落级 | P0 |

---

## 六、文件自动分类设计

```python
# classifier.py — 自动分类引擎

class FileClassifier:
    """基于扩展名 + 内容嗅探的智能文件分类"""

    # 分类规则（优先级从高到低）
    CATEGORY_RULES = {
        "academic_paper": {
            "extensions": [".pdf"],
            "content_hints": ["abstract", "introduction", "references", "doi"],
            "description": "学术论文"
        },
        "office_doc": {
            "extensions": [".docx", ".doc"],
            "description": "Office 文档"
        },
        "spreadsheet": {
            "extensions": [".xlsx", ".xls", ".csv"],
            "description": "表格数据"
        },
        "presentation": {
            "extensions": [".pptx", ".ppt"],
            "description": "演示文稿"
        },
        "code": {
            "extensions": [".py", ".js", ".ts", ".r", ".R", ".java", ".cpp"],
            "description": "代码文件"
        },
        "notebook": {
            "extensions": [".ipynb"],
            "description": "Jupyter 笔记本"
        },
        "markup": {
            "extensions": [".md", ".rst", ".html"],
            "description": "标记文档"
        },
        "data": {
            "extensions": [".json", ".jsonl", ".xml", ".yaml", ".toml", ".csv"],
            "description": "结构化数据"
        },
        "text": {
            "extensions": [".txt", ".log"],
            "description": "纯文本"
        },
        "image": {
            "extensions": [".png", ".jpg", ".jpeg", ".bmp", ".tiff"],
            "description": "图片"
        },
    }

    def classify(self, filepath: str) -> str:
        """返回文件分类名称"""
        # 1. 扩展名匹配
        # 2. 内容嗅探（PDF 前几页关键词等）
        # 3. 默认 "other"
```

---

## 七、数据清洗管线

```python
# cleaner.py — 通用数据清洗

class CleanerPipeline:
    """按文件类型组合清洗步骤"""

    # PDF 清洗
    PDF_STEPS = [
        "remove_headers_footers",   # 去页眉页脚（重复文本检测）
        "remove_watermarks",        # 去水印（模式匹配 + PyMuPDF 注释移除）
        "merge_fragments",          # 合并碎片段落（短行拼接）
        "fix_encoding",             # 修复编码问题
    ]

    # DOCX 清洗
    DOCX_STEPS = [
        "remove_track_changes",     # 去修订标记
        "extract_tables",           # 提取表格为结构化文本
        "extract_images",           # 提取图片 + 生成占位描述
    ]

    # XLSX 清洗
    XLSX_STEPS = [
        "drop_empty_rows",          # 去空行
        "merge_cells_expand",       # 展开合并单元格
        "detect_header",            # 智能检测表头行
        "normalize_types",          # 统一数据类型
    ]

    # PPTX 清洗
    PPTX_STEPS = [
        "extract_notes",            # 提取备注
        "extract_tables",           # 提取幻灯片内表格
        "flatten_groups",           # 展开组合对象
    ]

    # 通用
    COMMON_STEPS = [
        "remove_excess_whitespace", # 去多余空白
        "normalize_unicode",        # Unicode 标准化
        "strip_control_chars",      # 去控制字符
    ]
```

---

## 八、Embedding 自动选型

```python
# embedder.py 新增 auto 模式

class AutoEmbedder:
    """自动选择最优 Embedding 后端"""

    def detect_best_backend(self) -> str:
        """检测环境，返回最优后端"""
        # 1. 检测 CUDA
        if self._has_cuda():
            return "local"  # GPU 可用，走 sentence-transformers

        # 2. 检测 ONNX Runtime
        if self._has_onnxruntime():
            return "onnx"   # CPU 轻量方案

        # 3. 检测 Ollama
        if self._has_ollama():
            return "api"    # 本地 Ollama 服务

        # 4. 兜底：下载最小 ONNX 模型
        return "onnx"       # 自动下载 ~30MB ONNX 模型

    def auto_select_model(self) -> str:
        """自动选模型（中文优先 bge，英文 all-MiniLM）"""
        # 检测系统语言 + 首批文档语言
        # 中文 → BAAI/bge-small-zh-v1.5 (512d, ~100MB)
        # 英文 → all-MiniLM-L6-v2 (384d, ~80MB)
        # 多语言 → paraphrase-multilingual-MiniLM-L12-v2 (384d, ~470MB)
```

---

## 九、项目结构

```
DropRAG/
├── dropRAG/
│   ├── __init__.py
│   ├── config.py              # [复用80%] pydantic-settings
│   ├── pipeline.py            # [新] 统一处理管线 (Classify→Clean→Load→Chunk→Embed→Store)
│   ├── classifier.py          # [新] 文件自动分类
│   ├── cleaner.py             # [新] 数据清洗管线
│   ├── loader/                # [重写] 插件化 Loader 系统
│   │   ├── __init__.py        #   LoaderBase + 自动发现
│   │   ├── pdf_loader.py      #   PyMuPDF + pypdf 双引擎
│   │   ├── docx_loader.py     #   python-docx
│   │   ├── xlsx_loader.py     #   openpyxl
│   │   ├── pptx_loader.py     #   python-pptx
│   │   ├── csv_loader.py      #   csv + 编码检测
│   │   ├── code_loader.py     #   通用代码（函数级解析）
│   │   ├── notebook_loader.py #   ipynb
│   │   ├── markup_loader.py   #   md / rst / html
│   │   ├── data_loader.py     #   json / xml / yaml / toml
│   │   ├── image_loader.py    #   OCR / VLM 描述
│   │   ├── epub_loader.py     #   ebooklib
│   │   └── text_loader.py     #   纯文本兜底
│   ├── chunker/               # [重写] 插件化 Chunker
│   │   ├── __init__.py        #   ChunkerBase + 自动发现
│   │   ├── semantic_chunker.py#   语义分块（通用）
│   │   ├── heading_chunker.py #   标题级分块（MD/RST）
│   │   ├── function_chunker.py#   函数级分块（代码）
│   │   ├── row_chunker.py     #   行级分块（表格）
│   │   ├── slide_chunker.py   #   幻灯片级分块（PPT）
│   │   └── page_chunker.py    #   页级分块（PDF）
│   ├── embedder.py            # [复用90%] + auto-detect
│   ├── vectorstore.py         # [复用95%] sqlite-vec
│   ├── cache.py               # [复用95%] SQLite 持久缓存
│   ├── indexer.py             # [复用80%] + 分类步骤
│   ├── watcher.py             # [复用85%] + 归档回调
│   ├── engine.py              # [复用70%] + 通用管理端点
│   ├── reranker.py            # [复用50%] 通用化权重
│   ├── query_enhancer.py      # [重写] 通用扩展
│   ├── quality_feedback.py    # [复用60%]
│   ├── metadata.py            # [复用90%] 微调 schema
│   ├── search_log.py          # [复用90%]
│   ├── logging.py             # [复用100%]
│   ├── cli.py                 # [复用80%] + init 命令
│   ├── packager.py            # [新] 一键打包/分享
│   └── gui/                   # [新] 桌面 GUI (P2)
│       ├── __init__.py
│       ├── tray.py            #   系统托盘
│       ├── main_window.py     #   主窗口
│       └── search_widget.py   #   检索组件
├── config.yaml
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 十、依赖规划

### 核心依赖（必须，~30MB）

```
fastapi>=0.100.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
sqlite-vec>=0.1.6
numpy>=1.24.0
watchdog>=3.0.0
pyyaml>=6.0
```

### 按需加载（optional-dependencies 分组）

| 分组 | 包 | 大小 | 用途 |
|:-----|:---|:-----|:-----|
| `pdf` | pypdf / PyMuPDF | ~5MB | PDF 加载 |
| `office` | python-docx, openpyxl, python-pptx | ~10MB | Office 文件 |
| `ocr` | pytesseract + Pillow | ~20MB | 图片 OCR |
| `epub` | ebooklib | ~1MB | EPUB 电子书 |
| `onnx` | onnxruntime | ~30MB | ONNX 轻量推理 |
| `torch` | sentence-transformers + torch | ~800MB | GPU 本地推理 |
| `api` | httpx | ~1MB | 远程 API 推理 |
| `viz` | umap-learn + scikit-learn | ~200MB | UMAP 可视化 |
| `gui` | PySide6 | ~100MB | 桌面 GUI |
| `all-loaders` | pdf+office+ocr+epub | ~35MB | 全部文件类型支持 |

用户默认安装核心包，按需 `pip install dropRAG[pdf,office,onnx]` 即可。

---

## 十一、实现优先级

### P0 — MVP（核心可用，~1周）

1. 项目骨架 + pyproject.toml
2. 复用 bioRAG 的 vectorstore/cache/embedder/watcher/config/logging
3. 新建 pipeline.py + classifier.py
4. 重写 loader 为插件系统：PDF + DOCX + XLSX + PPTX + CSV + MD + TXT + Code
5. 重写 chunker 为插件系统：语义/标题/行级/幻灯片级
6. 新建 cleaner.py（PDF去水印/去页脚 + 表格提取）
7. Engine API（search/hybrid/status/update/events）
8. CLI：`dropRAG init` / `serve` / `build`
9. Docker

### P1 — 增强（~1周）

10. Embedding auto-detect + 首次引导
11. JSON/XML/YAML/HTML/EPUB 加载器
12. 图片 OCR/VLM 描述
13. 代码函数级分块
14. 一键打包 packager.py
15. 中文文档 + README

### P2 — 桌面化（~2周）

16. PySide6 系统托盘
17. 拖拽文件 GUI
18. Web UI 检索界面
19. 模型管理面板

---

## 十二、从 bioRAG 迁移策略

**不是 Fork，是抽取核心 + 重建外壳**：

1. **直接复制**（改包名 dropRAG）：
   - `vectorstore.py` → 去掉生信 metadata
   - `cache.py` → 原样
   - `embedder.py` → 增加 auto 模式
   - `watcher.py` → 增加归档回调
   - `config.py` → 去掉 categories 硬编码
   - `logging.py` → 原样
   - `metadata.py` / `search_log.py` → 微调 schema

2. **重写**（保留设计思路）：
   - `loader.py` → 插件化 loader/ 目录
   - `chunker.py` → 插件化 chunker/ 目录
   - `indexer.py` → 增加 pipeline 串联
   - `engine.py` → 通用化端点

3. **全新**：
   - `classifier.py` / `cleaner.py` / `pipeline.py` / `packager.py` / `gui/`

**bioRAG 保持独立维护**，DropRAG 不替代它。生信特化的逻辑（同义词扩展、R代码分块等）留在 bioRAG。
