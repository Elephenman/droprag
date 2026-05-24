# DropRAG Dockerfile - 多阶段构建

# Stage 1: 构建阶段
FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -e ".[pdf,office,onnx,api]" 2>/dev/null || \
    pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

# Stage 2: 运行阶段
FROM python:3.12-slim

WORKDIR /app

# 仅复制必要的文件
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/droprag /usr/local/bin/droprag
COPY --from=builder /app/droprag /app/droprag
COPY --from=builder /app/config.yaml /app/config.yaml

# 创建数据目录
RUN mkdir -p /app/data /app/models /app/knowledge

# 环境变量
ENV DROPRAG_CONFIG=/app/config.yaml
ENV PYTHONUNBUFFERED=1

EXPOSE 8766

VOLUME ["/app/data", "/app/models", "/app/knowledge"]

CMD ["droprag", "serve", "--host", "0.0.0.0", "--port", "8766"]
