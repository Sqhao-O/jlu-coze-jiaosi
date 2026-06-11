"""
「教思」AI教学孪生系统 - 工具基础设施
TeachingThought Utility Tools

提供:
1. 知识库检索工具 (RAG)
2. 变量读写工具 (会话变量 + 用户变量管理)
3. 提示词加载工具
4. 格式化输出工具
"""

import os
import json
from typing import Optional, Dict, Any, List
from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_utils.log.write_log import request_context

from config.llm_config import get_llm_params, Thresholds
from utils.json_parser import extract_text_from_response


# ============================================================
# 提示词管理
# ============================================================

# 提示词缓存
_PROMPT_CACHE: Dict[str, str] = {}


def _get_prompts_dir() -> str:
    """获取提示词目录路径"""
    workspace = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    return os.path.join(workspace, "config", "prompts")


def load_prompt(prompt_name: str, use_cache: bool = True) -> str:
    """
    加载提示词模板文件

    Args:
        prompt_name: 提示词文件名(不含.txt扩展名)
        use_cache: 是否使用缓存

    Returns:
        提示词文本内容
    """
    if use_cache and prompt_name in _PROMPT_CACHE:
        return _PROMPT_CACHE[prompt_name]

    prompts_dir = _get_prompts_dir()
    prompt_path = os.path.join(prompts_dir, f"{prompt_name}.txt")

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
        if use_cache:
            _PROMPT_CACHE[prompt_name] = content
        return content
    except FileNotFoundError:
        # 如果模板文件不存在，返回内置精简版提示词
        return _get_fallback_prompt(prompt_name)


def _get_fallback_prompt(prompt_name: str) -> str:
    """获取内置回退提示词"""
    fallbacks = {
        "teaching_mirror": "你是教学镜像体，负责生成完整的备课教案...",
        "learning_insight": "你是学情透视体，负责分析班级学习数据...",
        "strategy_sandbox": "你是策略沙盘体，负责虚拟课堂推演...",
        "classroom_co": "你是课堂共生体，负责实时课堂辅助...",
        "growth_tracker": "你是成长轨迹体，负责教师专业发展分析...",
        "student_simulator": "你是学生模拟器，以指定学生视角进行课堂反应...",
    }
    return fallbacks.get(prompt_name, "")


def format_prompt(prompt_name: str, **kwargs) -> str:
    """
    加载并格式化提示词模板

    Args:
        prompt_name: 提示词名称
        **kwargs: 模板变量，用于填充 {variable} 占位符

    Returns:
        格式化后的提示词
    """
    template = load_prompt(prompt_name)
    try:
        return template.format(**kwargs)
    except KeyError as e:
        # 缺失的变量保留原占位符，不报错
        return template


def clear_prompt_cache():
    """清除提示词缓存"""
    _PROMPT_CACHE.clear()


# ============================================================
# 知识库检索 (RAG)
# ============================================================

# 知识库检索优先级和参数配置
KB_CONFIG = {
    "standards": {
        "name": "KB1_课程标准",
        "priority": 1,
        "chunk_size": 600,
        "chunk_overlap": 120,
        "top_k": 6,
        "description": "各学科最新课程标准原文"
    },
    "textbooks": {
        "name": "KB2_教材教参",
        "priority": 2,
        "chunk_size": 500,
        "chunk_overlap": 100,
        "top_k": 8,
        "description": "主流教材目录、单元目标、教师用书"
    },
    "pedagogy": {
        "name": "KB3_教学法",
        "priority": 3,
        "chunk_size": 800,
        "chunk_overlap": 150,
        "top_k": 5,
        "description": "教育学理论、教学模式、案例分析"
    },
    "personal": {
        "name": "KB4_个人知识库",
        "priority": 4,
        "chunk_size": 600,
        "chunk_overlap": 120,
        "top_k": 10,
        "description": "教师历史教案、反思、学生数据"
    }
}


def kb_search(query: str, kb_type: str, top_k: Optional[int] = None) -> str:
    """
    调用知识库RAG检索

    通过coze_coding_dev_sdk的知识库接口进行语义检索。
    按优先级: 课标(KB1) → 教材(KB2) → 教法(KB3) → 个人KB(KB4)

    Args:
        query: 检索查询
        kb_type: 知识库类型: "standards"/"textbooks"/"pedagogy"/"personal"
        top_k: 返回结果数量，默认使用KB配置中的值

    Returns:
        格式化的检索结果文本
    """
    ctx = request_context.get() or new_context(method="kb_search")

    kb_cfg = KB_CONFIG.get(kb_type, KB_CONFIG["standards"])
    k = top_k or kb_cfg["top_k"]

    try:
        from coze_coding_dev_sdk import KBClient
        client = KBClient(ctx=ctx)

        results = client.search(
            knowledge_base=kb_cfg["name"],
            query=query,
            top_k=k,
        )

        if not results:
            return f"[{kb_cfg['name']}] 未检索到相关内容。"

        # 格式化检索结果
        formatted = []
        for i, doc in enumerate(results):
            content = doc.get("content", "") if isinstance(doc, dict) else str(doc)
            score = doc.get("score", 0) if isinstance(doc, dict) else 0
            formatted.append(f"---\n📄 来源 {i+1} (相关度: {score:.2f})\n{content}")

        header = f"## {kb_cfg['name']} 检索结果 (Top-{k})\n"
        return header + "\n".join(formatted)

    except Exception as e:
        # KB检索失败时返回提示信息，不阻塞主流程
        return f"[{kb_cfg['name']}] 知识库暂时不可用: {str(e)[:100]}"


def kb_multi_search(query: str, kb_types: Optional[List[str]] = None) -> Dict[str, str]:
    """
    多知识库并发检索

    Args:
        query: 检索查询
        kb_types: 要检索的知识库类型列表，默认按优先级检索全部

    Returns:
        {kb_type: result_text} 字典
    """
    if kb_types is None:
        # 按优先级排序
        kb_types = sorted(KB_CONFIG.keys(), key=lambda k: KB_CONFIG[k]["priority"])

    results = {}
    for kb_type in kb_types:
        results[kb_type] = kb_search(query, kb_type)

    return results


def merge_kb_results(results: Dict[str, str], max_length: int = 3000) -> str:
    """
    合并多知识库检索结果为单一上下文

    Args:
        results: kb_multi_search的返回结果
        max_length: 最大合并长度 (超过则截断)

    Returns:
        合并后的知识库上下文文本
    """
    merged_parts = []
    total_len = 0

    # 按优先级顺序合并
    for kb_type in sorted(results.keys(), key=lambda k: KB_CONFIG[k]["priority"]):
        content = results[kb_type]
        if total_len + len(content) > max_length:
            remaining = max_length - total_len
            if remaining > 200:
                merged_parts.append(content[:remaining] + "\n...(截断)")
            break
        merged_parts.append(content)
        total_len += len(content)

    return "\n\n".join(merged_parts)


# ============================================================
# 会话变量管理
# ============================================================

def compress_lesson_plan(plan_text: str, max_length: int = None) -> str:
    """
    压缩教案文本为摘要 (用于State存储)

    教案 > 2000字时自动压缩为500字摘要存入State，
    完整教案保留在工作流内部变量中。

    Args:
        plan_text: 教案全文
        max_length: 摘要最大长度（默认使用 Thresholds.LESSON_PLAN_COMPRESS_TARGET）

    Returns:
        压缩后的摘要或原文
    """
    if max_length is None:
        max_length = Thresholds.LESSON_PLAN_COMPRESS_TARGET

    if len(plan_text) <= Thresholds.LESSON_PLAN_COMPRESS_THRESHOLD:
        return plan_text

    ctx = request_context.get() or new_context(method="compress")

    try:
        from coze_coding_dev_sdk import LLMClient
        from langchain_core.messages import SystemMessage, HumanMessage

        client = LLMClient(ctx=ctx)

        # 使用集中化 LLM 配置
        llm_params = get_llm_params("compress_lesson_plan",
                                     max_tokens=max_length * 3)
        response = client.invoke(
            messages=[
                SystemMessage(content="请将以下教案压缩为简洁摘要，保留课题、教学目标、重难点、核心教学环节的关键信息。控制在500字以内。"),
                HumanMessage(content=plan_text[:8000])  # 只取前8000字用于摘要
            ],
            **llm_params
        )

        text = extract_text_from_response(response)
        return text[:max_length] if text else plan_text[:max_length]

    except Exception:
        # 压缩失败时直接截断
        return plan_text[:max_length] + "\n...(原文已截断)"


def format_student_name(index: int, tier: str) -> str:
    """
    生成化名学生姓名

    Args:
        index: 学生序号
        tier: 认知层次

    Returns:
        化名 (如: "张同学(基础层)")
    """
    surnames = ["张", "李", "王", "刘", "陈", "杨", "赵", "黄", "周", "吴"]
    surname = surnames[index % len(surnames)]
    return f"{surname}同学({tier})"


# ============================================================
# 格式化输出
# ============================================================

def format_lesson_plan_sections(sections: Dict[str, str]) -> str:
    """
    将教案各部分组装为完整Markdown文档

    Args:
        sections: {section_name: content} 字典

    Returns:
        完整的Markdown格式教案
    """
    order = [
        "课题信息", "课标链接", "教学目标", "教学重难点",
        "教学过程", "板书设计", "分层练习设计", "作业设计", "教学反思提示"
    ]

    formatted = []
    for section_name in order:
        content = sections.get(section_name, "")
        if content:
            formatted.append(f"## {section_name}\n\n{content}\n")

    return "\n".join(formatted)


def format_risk_badge(risk_level: str) -> str:
    """格式化风险等级徽章"""
    badges = {
        "red": "🔴 高风险",
        "yellow": "🟡 中风险",
        "green": "🟢 低风险",
    }
    return badges.get(risk_level, "⚪ 未知")


def format_error_tier(tier: str) -> str:
    """格式化错因层级标签"""
    labels = {
        "L1": "L1 知识性错误",
        "L2": "L2 方法性错误",
        "L3": "L3 习惯性错误",
    }
    return labels.get(tier, tier)


def format_radar_chart_text(dimensions: Dict[str, float]) -> str:
    """
    用文字描述五维雷达图

    Args:
        dimensions: {维度名: 0-10分数} 字典

    Returns:
        ASCII艺术风格的雷达图文字描述
    """
    max_score = 10
    lines = []
    lines.append("```")
    lines.append("五维能力雷达图 (0-10)")
    lines.append("-" * 40)

    for dim, score in dimensions.items():
        bar_length = int((score / max_score) * 20)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        lines.append(f"{dim:12s} │{bar}│ {score:.1f}")

    lines.append("-" * 40)
    lines.append("```")
    return "\n".join(lines)
