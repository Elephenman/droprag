# -*- mode: python ; coding: utf-8 -*-
"""DropRAG PyInstaller spec — 构建 Windows EXE（精简版）

策略：仅打包核心依赖（FastAPI + sqlite-vec + watchdog），
不打包 torch/transformers/sklearn 等大体积依赖。
Embedding 后端由用户自行安装。
"""

import sys
import os
from pathlib import Path

block_cipher = None

# ── 隐式导入（PyInstaller 无法自动检测的模块） ──
hiddenimports = [
    # FastAPI / uvicorn
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # pydantic
    "pydantic",
    "pydantic.deprecated",
    "pydantic.deprecated.decorator",
    "pydantic_settings",
    # sqlite-vec 原生绑定
    "sqlite_vec",
    # watchdog
    "watchdog",
    "watchdog.observers",
    "watchdog.observers.polling",
    # 数据格式
    "yaml",
    "chardet",
    # 标准库补充
    "email.mime.multipart",
    "email.mime.text",
    # DropRAG loader/chunker 插件（动态导入）
    "droprag.loader.text_loader",
    "droprag.loader.markdown_loader",
    "droprag.loader.pdf_loader",
    "droprag.loader.docx_loader",
    "droprag.loader.xlsx_loader",
    "droprag.loader.csv_loader",
    "droprag.loader.code_loader",
    "droprag.loader.pptx_loader",
    "droprag.loader.notebook_loader",
    "droprag.loader.markup_loader",
    "droprag.loader.data_loader",
    "droprag.chunker.semantic_chunker",
    "droprag.chunker.heading_chunker",
    "droprag.chunker.row_chunker",
    "droprag.chunker.slide_chunker",
    "droprag.chunker.page_chunker",
    "droprag.chunker.function_chunker",
]

# ── 二进制文件（sqlite-vec 的 .dll/.so） ──
sqlite_vec_binaries = []
try:
    import sqlite_vec
    sqlite_vec_dir = os.path.dirname(sqlite_vec.__file__)
    for f in os.listdir(sqlite_vec_dir):
        if f.endswith(('.dll', '.so', '.pyd')):
            src = os.path.join(sqlite_vec_dir, f)
            sqlite_vec_binaries.append((src, 'sqlite_vec'))
            print(f"  [bin] {src} -> sqlite_vec/")
except Exception as e:
    print(f"  [warn] sqlite_vec binary scan failed: {e}")

# ── 数据文件 ──
datas = []
config_yaml = os.path.join(os.path.dirname(SPEC), 'config.yaml')
if os.path.exists(config_yaml):
    datas.append((config_yaml, '.'))

a = Analysis(
    [os.path.join(os.path.dirname(SPEC), 'droprag', 'cli.py')],
    pathex=[os.path.dirname(SPEC)],
    binaries=sqlite_vec_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ── 大体积机器学习库（用户按需安装） ──
        'torch', 'torchvision', 'torchaudio',
        'transformers', 'sentence_transformers', 'tokenizers',
        'sklearn', 'scipy', 'pandas',
        'onnxruntime', 'onnx',
        # ── 大体积可视化/科学库 ──
        'matplotlib', 'PIL', 'pillow', 'cv2', 'opencv',
        'umap', 'numba', 'llvmlite',
        # ── 大体积数据/分布式库 ──
        'dask', 'distributed', 'pyarrow', 'h5py',
        'xarray', 'zarr', 'numcodecs',
        'statsmodels', 'patsy',
        # ── Jupyter/IPython ──
        'IPython', 'jupyter', 'notebook', 'nbformat', 'nbconvert',
        # ── GUI ──
        'tkinter', '_tkinter',
        # ── 其他不需要的 ──
        'pytest', 'py', 'pytest_asyncio',
        'tensorboard', 'zmq',
        'tornado', 'grpc',
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='droprag',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='droprag',
)
