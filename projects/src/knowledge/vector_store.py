"""
向量存储抽象层

提供 VectorStore 抽象接口和内存降级实现。
生产环境可替换为 pgvector 实现，开发/预览环境使用 InMemoryVectorStore。
"""

import json
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _writable_dir(base_dir: str, subdir: str) -> str:
    """返回可写目录路径：优先使用项目目录，不可写时降级到 /tmp"""
    target = os.path.join(base_dir, subdir)
    if os.path.isdir(target):
        if os.access(target, os.W_OK):
            return target
    else:
        try:
            os.makedirs(target, exist_ok=True)
            return target
        except OSError:
            pass
    fallback = os.path.join(tempfile.gettempdir(), "vibe_coding", subdir)
    os.makedirs(fallback, exist_ok=True)
    logger.warning(f"[VectorStore] 项目目录不可写，降级到: {fallback}")
    return fallback


class VectorStore(ABC):
    """向量存储抽象接口"""

    @abstractmethod
    def add_vectors(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[dict],
        contents: List[str],
        kb_id: str,
    ) -> int:
        """添加向量，返回添加数量"""
        ...

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        kb_id: str,
        top_k: int = 5,
    ) -> List[Tuple[str, dict, float]]:
        """检索最相似的向量，返回 [(content, metadata, score), ...]"""
        ...

    @abstractmethod
    def delete_by_kb(self, kb_id: str) -> int:
        """删除指定知识库的所有向量，返回删除数量"""
        ...

    @abstractmethod
    def delete_by_doc(self, kb_id: str, doc_id: str) -> int:
        """删除指定文档的所有向量，返回删除数量"""
        ...

    @abstractmethod
    def count(self, kb_id: str) -> int:
        """返回指定知识库的向量数量"""
        ...


class InMemoryVectorStore(VectorStore):
    """
    内存向量存储（开发/预览环境降级方案）

    - 向量数据存储在内存中，使用 numpy 余弦相似度检索
    - 持久化到本地 JSON 文件，重启后自动加载
    - 适用于 < 10k chunks 规模
    """

    def __init__(self, persist_dir: Optional[str] = None):
        self._data: dict = {}  # chunk_id -> {embedding, metadata, content, kb_id}
        if persist_dir:
            self._persist_dir = persist_dir
        else:
            _project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self._persist_dir = _writable_dir(_project_dir, ".knowledge_vectors")
        self._load()

    def _persist_path(self) -> str:
        return os.path.join(self._persist_dir, "vectors.json")

    def _load(self):
        """从文件加载向量数据"""
        path = self._persist_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                # 反序列化：embedding 从 list 恢复
                for chunk_id, item in raw.items():
                    item["embedding"] = np.array(item["embedding"], dtype=np.float32)
                    self._data[chunk_id] = item
                logger.info(f"[VectorStore] 从文件加载 {len(self._data)} 个向量")
            except Exception as e:
                logger.warning(f"[VectorStore] 加载向量文件失败: {e}")
                self._data = {}

    def _save(self):
        """持久化向量数据到文件"""
        os.makedirs(self._persist_dir, exist_ok=True)
        path = self._persist_path()
        try:
            # 序列化：embedding 转为 list
            serializable = {}
            for chunk_id, item in self._data.items():
                serializable[chunk_id] = {
                    "embedding": item["embedding"].tolist()
                    if isinstance(item["embedding"], np.ndarray)
                    else item["embedding"],
                    "metadata": item["metadata"],
                    "content": item["content"],
                    "kb_id": item["kb_id"],
                }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[VectorStore] 持久化向量文件失败: {e}")

    def add_vectors(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[dict],
        contents: List[str],
        kb_id: str,
    ) -> int:
        count = 0
        for chunk_id, emb, meta, content in zip(ids, embeddings, metadatas, contents):
            self._data[chunk_id] = {
                "embedding": np.array(emb, dtype=np.float32),
                "metadata": meta,
                "content": content,
                "kb_id": kb_id,
            }
            count += 1
        self._save()
        logger.info(f"[VectorStore] 添加 {count} 个向量到知识库 {kb_id}")
        return count

    def search(
        self,
        query_embedding: List[float],
        kb_id: str,
        top_k: int = 5,
    ) -> List[Tuple[str, dict, float]]:
        query_vec = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        results = []
        for chunk_id, item in self._data.items():
            if item["kb_id"] != kb_id:
                continue
            chunk_vec = item["embedding"]
            chunk_norm = np.linalg.norm(chunk_vec)
            if chunk_norm == 0:
                continue
            similarity = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))
            results.append((item["content"], item["metadata"], similarity))

        results.sort(key=lambda x: x[2], reverse=True)
        return results[:top_k]

    def delete_by_kb(self, kb_id: str) -> int:
        to_delete = [cid for cid, item in self._data.items() if item["kb_id"] == kb_id]
        for cid in to_delete:
            del self._data[cid]
        self._save()
        logger.info(f"[VectorStore] 删除知识库 {kb_id} 的 {len(to_delete)} 个向量")
        return len(to_delete)

    def delete_by_doc(self, kb_id: str, doc_id: str) -> int:
        to_delete = [
            cid
            for cid, item in self._data.items()
            if item["kb_id"] == kb_id and item["metadata"].get("doc_id") == doc_id
        ]
        for cid in to_delete:
            del self._data[cid]
        self._save()
        logger.info(f"[VectorStore] 删除文档 {doc_id} 的 {len(to_delete)} 个向量")
        return len(to_delete)

    def count(self, kb_id: str) -> int:
        return sum(1 for item in self._data.values() if item["kb_id"] == kb_id)


# 全局单例
_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """获取向量存储实例（当前使用内存降级方案）"""
    global _store
    if _store is None:
        _store = InMemoryVectorStore()
    return _store
