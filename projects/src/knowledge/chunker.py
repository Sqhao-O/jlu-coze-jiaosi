"""
文本分块模块

支持段落感知 + 滑动窗口分块策略。
教辅资料结构性强，优先按段落边界切分。
"""

import logging
import re
import uuid
from typing import List

logger = logging.getLogger(__name__)

# 默认分块参数
DEFAULT_CHUNK_SIZE = 500     # 每块最大字符数
DEFAULT_CHUNK_OVERLAP = 50   # 相邻块重叠字符数
DEFAULT_MAX_CHUNKS = 200     # 单文档最大分块数


def split_into_chunks(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> List[dict]:
    """
    将文本分割为 chunks。

    策略：
    1. 按段落（双换行）预切分
    2. 段落内如果超过 chunk_size，按句子再切
    3. 相邻块之间有 chunk_overlap 重叠
    4. 每个 chunk 生成唯一 id

    Args:
        text: 原始文本
        chunk_size: 每块最大字符数
        chunk_overlap: 重叠字符数
        max_chunks: 单文档最大分块数

    Returns:
        [{"id": str, "content": str, "index": int}, ...]
    """
    if not text or not text.strip():
        return []

    # 按段落预切分
    paragraphs = _split_paragraphs(text)

    # 合并段落为 chunks
    chunks = []
    current_chunk = ""
    chunk_index = 0

    for para in paragraphs:
        if not para.strip():
            continue

        # 如果当前块 + 新段落不超过限制，合并
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
        else:
            # 保存当前块
            if current_chunk:
                chunks.append(_make_chunk(current_chunk, chunk_index))
                chunk_index += 1

                # 重叠：取当前块末尾 overlap 字符
                if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                    current_chunk = current_chunk[-chunk_overlap:] + "\n\n" + para
                else:
                    current_chunk = para
            else:
                # 单个段落超过 chunk_size，按句子切分
                sub_chunks = _split_long_paragraph(para, chunk_size, chunk_overlap)
                for sc in sub_chunks:
                    chunks.append(_make_chunk(sc, chunk_index))
                    chunk_index += 1
                current_chunk = ""

    # 最后一块
    if current_chunk:
        chunks.append(_make_chunk(current_chunk, chunk_index))

    # 限制最大数量
    if len(chunks) > max_chunks:
        logger.warning(
            f"[分块] 文档分块数 {len(chunks)} 超过上限 {max_chunks}，截断"
        )
        chunks = chunks[:max_chunks]

    logger.info(f"[分块] 生成 {len(chunks)} 个 chunks")
    return chunks


def _split_paragraphs(text: str) -> List[str]:
    """按段落分割（双换行或章节标题）"""
    # 按双换行分割
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _split_long_paragraph(
    text: str, chunk_size: int, chunk_overlap: int
) -> List[str]:
    """对超长段落按句子切分"""
    # 中文句子分隔：句号、问号、感叹号、分号
    sentences = re.split(r"(?<=[。！？；\n])", text)
    sentences = [s for s in sentences if s.strip()]

    if not sentences:
        # 极端情况：无标点，硬切
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    chunks = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) <= chunk_size:
            current += sent
        else:
            if current:
                chunks.append(current)
            # 重叠
            if chunk_overlap > 0 and len(current) > chunk_overlap:
                current = current[-chunk_overlap:] + sent
            else:
                current = sent
    if current:
        chunks.append(current)

    return chunks


def _make_chunk(content: str, index: int) -> dict:
    return {
        "id": f"chunk-{uuid.uuid4().hex[:12]}",
        "content": content.strip(),
        "index": index,
    }
