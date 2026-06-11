"""
教思 AI 教学孪生系统 — 简化状态定义

重构 v3.0: 3 节点流水线
- 去掉 intermediate_data 和所有中间节点字段
- 只保留意图路由、核心生成、格式化输出所需的最小字段集
"""

from typing import Annotated, TypedDict, Optional, Dict, Any, List
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


class LessonPrepState(TypedDict, total=False):
    """
    智能备课工作流 State — 3 节点 (intent_router → generate_lesson_plan → format_output)
    """
    # --- 对话消息 ---
    messages: Annotated[list[AnyMessage], add_messages]

    # --- 意图路由 ---
    intent: str  # "chat" / "lesson_prep"

    # --- 教师输入参数（前端表单直接传入） ---
    lesson_subject: str       # 学科: "语文"/"数学"/"英语"/...
    lesson_topic: str         # 课题名称
    lesson_grade: str         # 年级: "初一"/"初二"/...
    lesson_hours: int         # 课时数（默认1）
    lesson_type: str          # 课型: "新授课"/"复习课"/"习题课"/"实验课"/"综合课"
    style_preference: str     # 教学风格: "启发式互动型"/"系统讲授型"/"情感体验型"/"任务驱动型"/"混合型"
    teacher_name: str         # 教师姓名（可选）
    years_of_experience: int  # 教龄（可选，默认5）
    key_concerns: str         # 教师特别关注点（可选）

    # --- 输出 ---
    _lesson_plan_json: str      # 中间：generate_lesson_plan 的 JSON 输出（内部使用）
    final_lesson_plan: str      # 最终格式化教案（Markdown）


class WorkflowMode:
    """工作流模式枚举"""
    LESSON_PREP = "lesson_prep"
    NONE = "none"
