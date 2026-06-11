"""
「教思」AI教学孪生系统 — 统一 JSON 解析工具
Unified JSON Parser

解决问题1：将分散在 10+ 个节点中的重复 JSON 解析逻辑统一封装。
解决问题3：消除代码重复，提供统一的容错机制。
"""

import json
import logging
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


def extract_text_from_response(response: Any) -> str:
    """
    从 LLM 响应中提取文本内容。

    兼容多种响应格式：
    - response.content 为 str
    - response.content 为 list[dict]（如 OpenAI 格式）
    - response 直接为 str
    """
    if hasattr(response, "content"):
        content = response.content
    else:
        content = response

    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        return " ".join(
            item.get("text", "") for item in content
            if isinstance(item, dict)
        )
    return str(content)


def clean_markdown_code_block(content: str) -> str:
    """
    清理 LLM 输出中常见的 markdown 代码块包装。

    处理情况：
    - ```json\\n{...}\\n```
    - ```\\n{...}\\n```
    - 只有开头 ``` 没有结尾
    - 只有结尾 ``` 没有开头
    """
    content = content.strip()
    # 移除 markdown 代码块标记
    if content.startswith("```"):
        # 跳过可能的语言标识（如 ```json）
        first_newline = content.find("\n")
        if first_newline != -1:
            content = content[first_newline + 1:]
        else:
            content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def parse_json(
    content: Union[str, Any],
    default: Optional[Dict[str, Any]] = None,
    log_context: str = "",
) -> Dict[str, Any]:
    """
    安全解析 JSON 字符串 — 统一的容错入口。

    处理流程：
    1. 从 LLM 响应中提取文本
    2. 清理 markdown 代码块标记
    3. 尝试 json.loads
    4. 失败则返回默认值并记录警告

    Args:
        content: 待解析的内容（可以是 LLM 响应对象、字符串或已解析的 dict）
        default: 解析失败时的默认返回值
        log_context: 日志上下文标识（如 "[备课-节点1]"）

    Returns:
        解析后的 dict，解析失败时返回 default

    Usage:
        # 替代原来分散的 try/except + 手动清理逻辑
        result = parse_json(response, default={"key": "val"}, log_context="[备课-节点1]")
    """
    if default is None:
        default = {}

    # 如果已经是 dict/list，直接返回
    if isinstance(content, (dict, list)):
        return content if isinstance(content, dict) else {"items": content}

    # 从 LLM 响应中提取文本
    text = extract_text_from_response(content)

    # 清理 markdown 代码块
    text = clean_markdown_code_block(text)

    # 尝试解析
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        elif isinstance(result, list):
            return {"items": result}
        else:
            return {"value": result}
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        preview = text[:200] if text else "(empty)"
        logger.warning(f"{log_context} JSON解析失败: {preview} | 错误: {e}")
        return default


def parse_json_strict(
    content: Union[str, Any],
    log_context: str = "",
) -> Optional[Dict[str, Any]]:
    """
    严格 JSON 解析 — 失败返回 None（而非默认值）。

    用于需要区分"解析失败"和"空结果"的场景。
    """
    text = extract_text_from_response(content)
    text = clean_markdown_code_block(text)
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        return {"value": result}
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        preview = text[:200] if text else "(empty)"
        logger.warning(f"{log_context} 严格JSON解析失败: {preview} | 错误: {e}")
        return None


def json_to_content_string(data: Any) -> str:
    """
    将 Python 对象转为用于 LLM prompt 的 JSON 字符串。

    自动截断过长内容。
    """
    return json.dumps(data, ensure_ascii=False, indent=2)


def is_valid_json_string(text: str) -> bool:
    """检查字符串是否为有效的 JSON"""
    if not isinstance(text, str):
        return False
    trimmed = text.strip()
    if not ((trimmed.startswith("{") and trimmed.endswith("}")) or
            (trimmed.startswith("[") and trimmed.endswith("]"))):
        return False
    try:
        json.loads(trimmed)
        return True
    except (json.JSONDecodeError, ValueError):
        return False
