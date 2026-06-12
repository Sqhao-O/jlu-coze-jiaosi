"""
知识库管理 API 路由

提供知识库 CRUD、文档上传、向量检索等接口。
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from knowledge import store
from knowledge.parser import extract_text
from knowledge.chunker import split_into_chunks
from knowledge.embedder import embed_and_store, retrieve_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])


# ==================== 知识库 CRUD ====================

@router.get("")
async def list_knowledge_bases():
    """列出所有知识库"""
    try:
        return store.list_knowledge_bases()
    except Exception as e:
        logger.error(f"[知识库] 列表查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"知识库列表查询失败: {str(e)}")


@router.post("")
async def create_knowledge_base(name: str = Form(...), description: str = Form("")):
    """创建知识库"""
    if not name.strip():
        raise HTTPException(status_code=400, detail="知识库名称不能为空")
    try:
        return store.create_knowledge_base(name.strip(), description.strip())
    except Exception as e:
        logger.error(f"[知识库] 创建失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"知识库创建失败: {str(e)}")


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    """删除知识库"""
    try:
        if not store.delete_knowledge_base(kb_id):
            raise HTTPException(status_code=404, detail="知识库不存在")
        return {"status": "deleted", "kb_id": kb_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[知识库] 删除失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"知识库删除失败: {str(e)}")


# ==================== 文档管理 ====================

@router.get("/{kb_id}/documents")
async def list_documents(kb_id: str):
    """列出知识库下的文档"""
    try:
        kb = store.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return store.list_documents(kb_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[知识库] 文档列表查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文档列表查询失败: {str(e)}")


@router.post("/{kb_id}/upload")
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
):
    """
    上传文档到知识库。

    支持格式：PDF、Word(.docx)、Excel(.xlsx)、PPT(.pptx)、TXT
    上传后自动解析 → 分块 → 向量化
    """
    try:
        kb = store.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")

        # 校验文件类型
        filename = file.filename or "unknown.txt"
        ext = os.path.splitext(filename)[1].lower()
        supported = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md"}
        if ext not in supported:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式: {ext}，支持: {', '.join(sorted(supported))}",
            )

        # 读取文件内容
        content = await file.read()
        file_size = len(content)

        # 1. 解析文档
        logger.info(f"[知识库] 开始解析: {filename} ({file_size} bytes)")
        text = extract_text(content, filename)

        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="文档内容为空或无法解析")

        # 2. 分块
        chunks = split_into_chunks(text)
        if not chunks:
            raise HTTPException(status_code=400, detail="文档分块失败")

        # 3. 创建文档记录（状态 processing）
        doc = store.add_document(kb_id, filename, file_size, len(chunks), status="processing")

        # 4. 向量化 + 存储
        stored_count = embed_and_store(kb_id, doc["id"], chunks)

        # 5. 更新文档状态
        store.update_document_status(kb_id, doc["id"], "ready", stored_count)

        logger.info(f"[知识库] 上传完成: {filename} → {stored_count} chunks")
        return {
            "status": "ready",
            "doc_id": doc["id"],
            "filename": filename,
            "file_size": file_size,
            "chunk_count": stored_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[知识库] 上传失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    """删除文档"""
    try:
        if not store.delete_document(kb_id, doc_id):
            raise HTTPException(status_code=404, detail="文档不存在")
        return {"status": "deleted", "kb_id": kb_id, "doc_id": doc_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[知识库] 文档删除失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文档删除失败: {str(e)}")


# ==================== 检索 ====================

@router.post("/{kb_id}/search")
async def search_knowledge(kb_id: str, query: str = Form(...), top_k: int = Form(3)):
    """检索知识库中与 query 最相关的内容"""
    try:
        kb = store.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        results = retrieve_context(query, kb_id, top_k=min(top_k, 10))
        return {"kb_id": kb_id, "query": query, "results": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[知识库] 检索失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"知识库检索失败: {str(e)}")
