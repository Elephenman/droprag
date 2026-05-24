"""DropRAG Embedding 多后端封装

支持:
1. local (sentence-transformers, 兼容旧版)
2. onnx (onnxruntime, 轻量推荐)
3. api (外部HTTP API, 如 Ollama/OpenAI)
4. auto (自动检测最优后端)
"""

import hashlib
import logging
import platform
from typing import List, Optional
from droprag.config import EmbeddingConfig
from droprag.logging import get_logger

log = get_logger(__name__)


class BaseEmbedder:
    """Embedder 基类"""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._cache = None

    def set_cache(self, cache):
        self._cache = cache

    def encode(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        raise NotImplementedError

    def encode_single(self, text: str) -> List[float]:
        return self.encode([text])[0]

    @property
    def dimension(self) -> int:
        return self.config.dimension

    @property
    def model_name(self) -> str:
        return self.config.model

    def _encode_with_cache(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        """带缓存的编码流程"""
        if batch_size is None:
            batch_size = self.config.batch_size

        results = [None] * len(texts)
        to_encode = []
        to_encode_indices = []

        if self._cache:
            for i, text in enumerate(texts):
                cached = self._cache.get_embedding(text)
                if cached:
                    results[i] = cached
                else:
                    to_encode.append(text)
                    to_encode_indices.append(i)
        else:
            to_encode = texts
            to_encode_indices = list(range(len(texts)))

        if to_encode:
            embeddings = self._do_encode(to_encode, batch_size)
            for idx, text, emb in zip(to_encode_indices, to_encode, embeddings):
                emb_list = list(emb) if hasattr(emb, 'tolist') else emb
                if self._cache:
                    self._cache.set_embedding(text, emb_list)
                results[idx] = emb_list

        return results

    def _do_encode(self, texts: List[str], batch_size: int) -> List[List[float]]:
        raise NotImplementedError


class SentenceTransformerEmbedder(BaseEmbedder):
    """sentence-transformers 本地编码器（PyTorch 后端）"""

    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        import os
        log.info(f"加载 sentence-transformers 模型: {self.config.model}...")
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(
            self.config.model,
            device=self.config.device,
            cache_folder=os.path.abspath(self.config.model_cache_dir),
        )
        log.info(f"模型加载完成 (device={self.config.device})")

    def _do_encode(self, texts: List[str], batch_size: int) -> List[List[float]]:
        self._load_model()
        embeddings = self._model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True,
            show_progress_bar=len(texts) > 100,
        )
        return [emb.tolist() for emb in embeddings]

    def encode(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        self._load_model()
        return self._encode_with_cache(texts, batch_size)


class ONNXEmbedder(BaseEmbedder):
    """ONNX Runtime 编码器（轻量推荐，~30MB vs torch ~800MB）"""

    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self._session = None
        self._tokenizer = None

    def _load_model(self):
        if self._session is not None:
            return
        import os
        model_dir = os.path.abspath(self.config.model_cache_dir)
        onnx_path = os.path.join(model_dir, "model.onnx")

        if not os.path.exists(onnx_path):
            log.info(f"ONNX 模型不存在，自动转换: {self.config.model} -> {onnx_path}")
            self._convert_to_onnx(onnx_path)

        log.info(f"加载 ONNX 模型: {onnx_path}")
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(onnx_path, opts)

        from transformers import AutoTokenizer
        tokenizer_path = os.path.join(model_dir, "tokenizer")
        if not os.path.exists(tokenizer_path):
            tokenizer_path = self.config.model
        self._tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
        log.info("ONNX 模型加载完成")

    def _convert_to_onnx(self, onnx_path: str):
        import os
        os.makedirs(os.path.dirname(onnx_path), exist_ok=True)
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(
            self.config.model,
            cache_folder=os.path.abspath(self.config.model_cache_dir),
        )
        tokenizer_path = os.path.join(os.path.dirname(onnx_path), "tokenizer")
        model[0].tokenizer.save_pretrained(tokenizer_path)
        try:
            from optimum.onnxruntime import ORTModelForFeatureExtraction
            ort_model = ORTModelForFeatureExtraction.from_pretrained(self.config.model, export=True)
            ort_model.save_pretrained(os.path.dirname(onnx_path))
            log.info("ONNX 转换成功（通过 optimum）")
        except ImportError:
            import torch
            dummy = model.tokenize(["test"])
            with torch.no_grad():
                torch.onnx.export(
                    model, (dummy,), onnx_path,
                    input_names=list(dummy.keys()),
                    dynamic_axes={k: {0: "batch"} for k in dummy},
                )
            log.info("ONNX 转换成功（通过 torch.onnx.export）")

    def _do_encode(self, texts: List[str], batch_size: int) -> List[List[float]]:
        self._load_model()
        import numpy as np
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            encoded = self._tokenizer(
                batch, padding=True, truncation=True,
                max_length=512, return_tensors="np",
            )
            outputs = self._session.run(
                None,
                {k: v for k, v in encoded.items() if k in ["input_ids", "attention_mask", "token_type_ids"]},
            )
            attention_mask = encoded["attention_mask"]
            token_embeddings = outputs[0]
            input_mask_expanded = np.expand_dims(attention_mask, -1).astype(float)
            embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1) / np.clip(
                input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None
            )
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            embeddings = embeddings / np.clip(norms, a_min=1e-9, a_max=None)
            all_embeddings.extend(embeddings.tolist())
        return all_embeddings

    def encode(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        self._load_model()
        return self._encode_with_cache(texts, batch_size)


class APIEmbedder(BaseEmbedder):
    """外部 API 编码器"""

    def _do_encode(self, texts: List[str], batch_size: int) -> List[List[float]]:
        import httpx
        url = self.config.api_url
        if not url:
            raise ValueError("API 模式需要配置 embedding.api_url")

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            if "ollama" in url or ":11434" in url:
                for text in batch:
                    resp = httpx.post(url, json={"model": self.config.model, "input": text}, headers=headers, timeout=30)
                    data = resp.json()
                    all_embeddings.append(data.get("embedding", data.get("data", [{}])[0].get("embedding", [])))
            else:
                resp = httpx.post(url, json={"model": self.config.model, "input": batch}, headers=headers, timeout=30)
                data = resp.json()
                for item in data.get("data", []):
                    all_embeddings.append(item.get("embedding", []))
        return all_embeddings

    def encode(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        return self._encode_with_cache(texts, batch_size)


def create_embedder(config: EmbeddingConfig) -> BaseEmbedder:
    """根据配置创建对应的 Embedder 实例"""
    provider = config.provider.lower()

    if provider == "auto":
        return _auto_detect_embedder(config)
    elif provider == "onnx":
        log.info("使用 ONNX 后端")
        return ONNXEmbedder(config)
    elif provider == "api":
        log.info(f"使用 API 后端: {config.api_url}")
        return APIEmbedder(config)
    elif provider == "local":
        try:
            import onnxruntime
            log.info("检测到 onnxruntime，自动切换 ONNX 后端（更轻量）")
            return ONNXEmbedder(config)
        except ImportError:
            log.info("使用 sentence-transformers 后端")
            return SentenceTransformerEmbedder(config)
    else:
        log.warning(f"未知 provider: {provider}，回退到 auto")
        return _auto_detect_embedder(config)


def _auto_detect_embedder(config: EmbeddingConfig) -> BaseEmbedder:
    """自动检测最优 Embedding 后端"""
    # 1. 检测 CUDA
    try:
        import torch
        if torch.cuda.is_available():
            log.info("检测到 CUDA GPU，使用 sentence-transformers 后端")
            config.device = "cuda"
            return SentenceTransformerEmbedder(config)
    except ImportError:
        pass

    # 2. 检测 ONNX Runtime
    try:
        import onnxruntime
        log.info("检测到 onnxruntime，使用 ONNX 后端")
        return ONNXEmbedder(config)
    except ImportError:
        pass

    # 3. 检测 Ollama
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            log.info("检测到 Ollama，使用 API 后端")
            config.provider = "api"
            config.api_url = "http://localhost:11434/api/embeddings"
            return APIEmbedder(config)
    except Exception:
        pass

    # 4. 兜底：尝试 sentence-transformers
    try:
        from sentence_transformers import SentenceTransformer
        log.info("使用 sentence-transformers 后端（兜底）")
        return SentenceTransformerEmbedder(config)
    except ImportError:
        log.warning("无可用的 Embedding 后端！请安装: pip install droprag[onnx] 或 droprag[torch]")
        raise RuntimeError("无可用的 Embedding 后端，请安装 onnxruntime 或 sentence-transformers")
