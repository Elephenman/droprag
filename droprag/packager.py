"""DropRAG 一键打包/分享

将知识库（索引 + 元数据 + 配置）打包为 .zip，
支持导入已打包的知识库到新环境。
"""

import os
import json
import shutil
import zipfile
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any

from droprag.logging import get_logger
from droprag.config import DropRAGConfig

log = get_logger(__name__)


class Packager:
    """知识库打包/导入器"""

    MANIFEST_FILE = "droprag_manifest.json"

    def __init__(self, data_dir: str = None, config_path: str = None):
        if config_path:
            from droprag.config import load_config
            self.settings = load_config(config_path)
        else:
            self.settings = DropRAGConfig()
        self.data_dir = data_dir or self.settings.engine.data_dir

    def export_kb(self, output_path: str = None, include_embeddings: bool = False,
                  include_config: bool = True, include_source_files: bool = False,
                  source_dir: str = None) -> str:
        """打包知识库

        Args:
            output_path: 输出 zip 路径，默认 data_dir 同级目录
            include_embeddings: 是否包含向量数据（较大）
            include_config: 是否包含配置文件
            include_source_files: 是否包含源文件
            source_dir: 源文件目录（include_source_files=True 时需要）

        Returns:
            打包文件路径
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(
                os.path.dirname(self.data_dir),
                f"droprag_kb_{timestamp}.zip"
            )

        manifest = {
            "version": "0.1.0",
            "created_at": datetime.now().isoformat(),
            "data_dir": os.path.basename(self.data_dir),
            "include_embeddings": include_embeddings,
            "include_source_files": include_source_files,
            "files": [],
        }

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. 元数据数据库
            metadata_db = os.path.join(self.data_dir, "metadata.db")
            if os.path.exists(metadata_db):
                arcname = f"{os.path.basename(self.data_dir)}/metadata.db"
                zf.write(metadata_db, arcname)
                manifest["files"].append(arcname)

            # 2. 向量数据库
            if include_embeddings:
                vec_db = os.path.join(self.data_dir, "droprag.db")
                if os.path.exists(vec_db):
                    arcname = f"{os.path.basename(self.data_dir)}/droprag.db"
                    zf.write(vec_db, arcname)
                    manifest["files"].append(arcname)

            # 3. 缓存数据库
            cache_db = os.path.join(self.data_dir, "cache.db")
            if os.path.exists(cache_db):
                arcname = f"{os.path.basename(self.data_dir)}/cache.db"
                zf.write(cache_db, arcname)
                manifest["files"].append(arcname)

            # 4. 配置文件
            if include_config:
                config_yaml = os.path.join(os.path.dirname(self.data_dir), "config.yaml")
                if os.path.exists(config_yaml):
                    arcname = "config.yaml"
                    zf.write(config_yaml, arcname)
                    manifest["files"].append(arcname)

            # 5. 源文件
            if include_source_files and source_dir and os.path.isdir(source_dir):
                for root, dirs, files in os.walk(source_dir):
                    # 跳过隐藏目录和 __pycache__
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                    for f in files:
                        filepath = os.path.join(root, f)
                        rel = os.path.relpath(filepath, os.path.dirname(source_dir))
                        arcname = f"sources/{rel}"
                        zf.write(filepath, arcname)
                        manifest["files"].append(arcname)

            # 6. 写入 manifest
            zf.writestr(self.MANIFEST_FILE, json.dumps(manifest, indent=2, ensure_ascii=False))

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        log.info(f"知识库已打包: {output_path} ({size_mb:.1f} MB)")
        return output_path

    def import_kb(self, zip_path: str, target_dir: str = None,
                  overwrite: bool = False, merge: bool = False) -> Dict[str, Any]:
        """导入知识库

        Args:
            zip_path: 打包文件路径
            target_dir: 目标目录，默认为当前 data_dir
            overwrite: 是否覆盖已有数据
            merge: 是否合并（保留已有数据，仅添加新的）

        Returns:
            导入结果摘要
        """
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"打包文件不存在: {zip_path}")

        target = target_dir or self.data_dir
        os.makedirs(target, exist_ok=True)

        result = {"imported_files": [], "skipped_files": [], "errors": []}

        with zipfile.ZipFile(zip_path, "r") as zf:
            # 读取 manifest
            if self.MANIFEST_FILE in zf.namelist():
                manifest = json.loads(zf.read(self.MANIFEST_FILE))
                log.info(f"导入知识库 v{manifest.get('version', '?')}, "
                         f"创建于 {manifest.get('created_at', '?')}")
            else:
                manifest = {}

            for name in zf.namelist():
                if name == self.MANIFEST_FILE:
                    continue

                # 解压目标路径
                if name.startswith(f"{manifest.get('data_dir', 'data')}/"):
                    # 数据库文件 → 放到 target_dir
                    basename = os.path.basename(name)
                    dest = os.path.join(target, basename)
                else:
                    dest = os.path.join(os.path.dirname(target), name)

                # 检查是否已存在
                if os.path.exists(dest) and not overwrite and not merge:
                    result["skipped_files"].append(name)
                    continue

                os.makedirs(os.path.dirname(dest), exist_ok=True)
                try:
                    with zf.open(name) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                    result["imported_files"].append(name)
                except Exception as e:
                    result["errors"].append({"file": name, "error": str(e)})

        log.info(f"导入完成: {len(result['imported_files'])} 文件, "
                 f"{len(result['skipped_files'])} 跳过, "
                 f"{len(result['errors'])} 错误")
        return result

    def get_kb_stats(self) -> Dict[str, Any]:
        """获取知识库统计信息"""
        stats = {
            "data_dir": self.data_dir,
            "exists": os.path.isdir(self.data_dir),
            "databases": {},
            "total_size_mb": 0,
        }

        if not stats["exists"]:
            return stats

        for db_name in ["droprag.db", "metadata.db", "cache.db", "search_logs.db"]:
            db_path = os.path.join(self.data_dir, db_name)
            if os.path.exists(db_path):
                size = os.path.getsize(db_path)
                stats["databases"][db_name] = {
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 2),
                }
                stats["total_size_mb"] += size / (1024 * 1024)

        stats["total_size_mb"] = round(stats["total_size_mb"], 2)
        return stats
