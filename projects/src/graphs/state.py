"""
教思 AI 教学孪生系统 — 简化状态定义

重构 v3.1: 7 个核心参数
- 学科、年级、教学目标、重点、难点、课时时长、教学风格
- 每个参数都支持预设选择 + 自定义输入
"""

from typing import Annotated, TypedDict, Optional
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

    # --- 教师输入参数（前端表单传入） ---
    lesson_subject: str       # 学科
    lesson_topic: str         # 课题名称
    lesson_grade: str         # 年级
    lesson_objectives: str    # 教学目标
    key_points: str           # 重点
    difficult_points: str     # 难点
    lesson_duration: int      # 课时时长（分钟）
    style_preference: str     # 教学风格

    # --- 输出 ---
    _lesson_plan_json: str      # 中间：generate_lesson_plan 的 JSON 输出（内部使用）
    final_lesson_plan: str      # 最终格式化教案（Markdown）


class WorkflowMode:
    """工作流模式枚举"""
    LESSON_PREP = "lesson_prep"
    NONE = "none"
