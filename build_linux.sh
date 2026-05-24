#!/bin/bash
# DropRAG Linux 构建脚本
# 在 Linux 系统上运行，或通过 Docker 交叉编译
#
# 用法:
#   1. 本地 Linux: bash build_linux.sh
#   2. Docker 构建: docker run --rm -v $(pwd):/build -w /build python:3.12-slim bash build_linux.sh

set -e

echo "=== DropRAG Linux Build ==="

# 安装依赖
pip install --quiet pyinstaller

# 安装 DropRAG 核心依赖（不含 torch/sklearn）
pip install --quiet \
    fastapi>=0.100.0 \
    uvicorn[standard]>=0.24.0 \
    pydantic>=2.0.0 \
    pydantic-settings>=2.0.0 \
    sqlite-vec>=0.1.6 \
    numpy>=1.24.0 \
    watchdog>=3.0.0 \
    pyyaml>=6.0 \
    chardet>=5.0.0

# 用 PyInstaller 构建
pyinstaller droprag.spec --clean --noconfirm

# 打包
cd dist
tar czf droprag-0.1.0-linux-x86_64.tar.gz droprag/
echo "Built: dist/droprag-0.1.0-linux-x86_64.tar.gz"
ls -lh droprag-0.1.0-linux-x86_64.tar.gz
