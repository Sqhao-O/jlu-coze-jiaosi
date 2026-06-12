"""
向量化模块

使用 coze-coding-dev-sdk EmbeddingClient 将文本转化为向量，
并写入 VectorStore。

注意：embed_texts 对批量输入只返回单个向量化结果，
因此回退到逐个调用 embed_text。
"""

import hashlib
import logging
from typing import List

from knowledge.vector_store import get_vector_store

logger = logging.getLogger(__name__)

# 批量向量化大小（控制并发）
_EMBED_BATCH_SIZE = 10


def _get_embedder():
    """延迟初始化 EmbeddingClient"""
    from coze_coding_dev_sdk import EmbeddingClient
    return EmbeddingClient()


def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def embed_and_store(
    kb_id: str,
    doc_id: str,
    chunks: List[dict],
) -> int:
    """
    将 chunks 向量化并存入 VectorStore。

    Args:
        kb_id: 知识库 ID
        doc_id: 文档 ID
        chunks: [{"id": str, "content": str, "index": int}, ...]

    Returns:
        成功存储的 chunk 数量
    """
    if not chunks:
        return 0

    store = get_vector_store()
    embedder = _get_embedder()

    stored = 0
    # 逐个向量化（embed_texts 批量接口返回值不符合预期）
    for batch_start in range(0, len(chunks), _EMBED_BATCH_SIZE):
        batch = chunks[batch_start : batch_start + _EMBED_BATCH_SIZE]

        ids = []
        emb_list = []
        metas = []
        contents = []

        for chunk in batch:
            try:
                vec = embedder.embed_text(chunk["content"])
            except Exception as e:
                logger.error(f"[Embedder] 向量化失败 (chunk {chunk['id']}): {e}")
                continue

            ids.append(chunk["id"])
            emb_list.append(vec)
            metas.append({
                "doc_id": doc_id,
                "chunk_index": chunk["index"],
                "content_hash": _content_hash(chunk["content"]),
            })
            contents.append(chunk["content"])
            stored += 1

        if ids:
            store.add_vectors(ids, emb_list, metas, contents, kb_id)

    logger.info(f"[Embedder] 存储 {stored}/{len(chunks)} chunks (kb={kb_id}, doc={doc_id})")
    return stored


def retrieve_context(
    query: str,
    kb_id: str,
    top_k: int = 3,
) -> List[dict]:
    """
    检索与 query 最相关的 top_k chunks。

    Args:
        query: 用户查询文本
        kb_id: 知识库 ID
        top_k: 返回最相关的 chunk 数

    Returns:
        [{"content": str, "score": float, "doc_id": str, "chunk_index": int}, ...]
    """
    embedder = _get_embedder()
    store = get_vector_store()

    try:
        query_vec = embedder.embed_text(query)
    except Exception as e:
        logger.error(f"[Embedder] query 向量化失败: {e}")
        return []

    raw_results = store.search(query_vec, kb_id=kb_id, top_k=top_k)

    results = []
    for content, metadata, score in raw_results:
        results.append({
            "content": content,
            "score": score,
            "doc_id": metadata.get("doc_id", ""),
            "chunk_index": metadata.get("chunk_index", 0),
        })

    logger.info(f"[Embedder] 检索到 {len(results)} 条相关内容 (kb={kb_id}, query={query[:30]}...)")
    return results
