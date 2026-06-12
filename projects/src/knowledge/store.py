"""
知识库元数据存储

使用 JSON 文件持久化知识库和文档的元信息（轻量方案，不依赖数据库表）。
后续可迁移到 PostgreSQL knowledge_bases / knowledge_documents 表。
"""

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


def _writable_dir(base_dir: str, subdir: str) -> str:
    """返回可写目录路径：优先使用项目目录，不可写时降级到 /tmp"""
    target = os.path.join(base_dir, subdir)
    if os.path.isdir(target):
        # 目录已存在，检查是否可写
        if os.access(target, os.W_OK):
            return target
    else:
        # 目录不存在，尝试创建
        try:
            os.makedirs(target, exist_ok=True)
            return target
        except OSError:
            pass
    # 降级到 /tmp
    fallback = os.path.join(tempfile.gettempdir(), "vibe_coding", subdir)
    os.makedirs(fallback, exist_ok=True)
    logger.warning(f"[知识库] 项目目录不可写，降级到: {fallback}")
    return fallback


_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_META_DIR = _writable_dir(_PROJECT_DIR, ".knowledge_meta")


def _meta_path() -> str:
    return os.path.join(_META_DIR, "knowledge_bases.json")


def _load_all() -> dict:
    path = _meta_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_all(data: dict):
    os.makedirs(_META_DIR, exist_ok=True)
    with open(_meta_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==================== 知识库 CRUD ====================

def list_knowledge_bases() -> List[dict]:
    """列出所有知识库"""
    data = _load_all()
    result = []
    for kb_id, kb in data.items():
        result.append({
            "id": kb_id,
            "name": kb.get("name", ""),
            "description": kb.get("description", ""),
            "doc_count": len(kb.get("documents", {})),
            "chunk_count": kb.get("chunk_count", 0),
            "created_at": kb.get("created_at", ""),
            "updated_at": kb.get("updated_at", ""),
        })
    result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return result


def get_knowledge_base(kb_id: str) -> Optional[dict]:
    """获取单个知识库"""
    data = _load_all()
    kb = data.get(kb_id)
    if not kb:
        return None
    return {
        "id": kb_id,
        "name": kb.get("name", ""),
        "description": kb.get("description", ""),
        "doc_count": len(kb.get("documents", {})),
        "chunk_count": kb.get("chunk_count", 0),
        "created_at": kb.get("created_at", ""),
        "updated_at": kb.get("updated_at", ""),
    }


def create_knowledge_base(name: str, description: str = "") -> dict:
    """创建知识库"""
    kb_id = f"kb-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    kb = {
        "name": name,
        "description": description,
        "documents": {},
        "chunk_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    data = _load_all()
    data[kb_id] = kb
    _save_all(data)
    logger.info(f"[知识库] 创建: {kb_id} ({name})")
    return {"id": kb_id, "name": name, "description": description,
            "doc_count": 0, "chunk_count": 0, "created_at": now, "updated_at": now}


def delete_knowledge_base(kb_id: str) -> bool:
    """删除知识库（同时清理向量）"""
    data = _load_all()
    if kb_id not in data:
        return False
    del data[kb_id]
    _save_all(data)

    # 清理向量
    from knowledge.vector_store import get_vector_store
    get_vector_store().delete_by_kb(kb_id)

    logger.info(f"[知识库] 删除: {kb_id}")
    return True


# ==================== 文档 CRUD ====================

def list_documents(kb_id: str) -> List[dict]:
    """列出知识库下的所有文档"""
    data = _load_all()
    kb = data.get(kb_id)
    if not kb:
        return []
    docs = []
    for doc_id, doc in kb.get("documents", {}).items():
        docs.append({
            "id": doc_id,
            "kb_id": kb_id,
            "filename": doc.get("filename", ""),
            "file_size": doc.get("file_size", 0),
            "chunk_count": doc.get("chunk_count", 0),
            "status": doc.get("status", "unknown"),
            "created_at": doc.get("created_at", ""),
        })
    docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return docs


def add_document(kb_id: str, filename: str, file_size: int, chunk_count: int, status: str = "ready") -> Optional[dict]:
    """添加文档记录"""
    data = _load_all()
    kb = data.get(kb_id)
    if not kb:
        return None
    doc_id = f"doc-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    kb["documents"][doc_id] = {
        "filename": filename,
        "file_size": file_size,
        "chunk_count": chunk_count,
        "status": status,
        "created_at": now,
    }
    kb["chunk_count"] = sum(d.get("chunk_count", 0) for d in kb["documents"].values())
    kb["updated_at"] = now
    _save_all(data)
    logger.info(f"[知识库] 文档添加: {doc_id} ({filename}, {chunk_count} chunks)")
    return {"id": doc_id, "kb_id": kb_id, "filename": filename,
            "file_size": file_size, "chunk_count": chunk_count, "status": status, "created_at": now}


def delete_document(kb_id: str, doc_id: str) -> bool:
    """删除文档记录（同时清理向量）"""
    data = _load_all()
    kb = data.get(kb_id)
    if not kb or doc_id not in kb.get("documents", {}):
        return False
    del kb["documents"][doc_id]
    kb["chunk_count"] = sum(d.get("chunk_count", 0) for d in kb["documents"].values())
    kb["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_all(data)

    # 清理向量
    from knowledge.vector_store import get_vector_store
    get_vector_store().delete_by_doc(kb_id, doc_id)

    logger.info(f"[知识库] 文档删除: {doc_id}")
    return True


def update_document_status(kb_id: str, doc_id: str, status: str, chunk_count: int = 0):
    """更新文档状态"""
    data = _load_all()
    kb = data.get(kb_id)
    if not kb or doc_id not in kb.get("documents", {}):
        return
    kb["documents"][doc_id]["status"] = status
    if chunk_count > 0:
        kb["documents"][doc_id]["chunk_count"] = chunk_count
    kb["chunk_count"] = sum(d.get("chunk_count", 0) for d in kb["documents"].values())
    kb["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_all(data)
