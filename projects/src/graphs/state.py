"""
教思 AI 教学孪生系统 — 状态定义

v4.0: 多功能模式
- mode 字段驱动路由，替代关键词猜测
- 5 种功能模式 + 闲聊
- modes 列表预留 subagent 并行模式
"""

from typing import Annotated, TypedDict, Optional, List
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


class LessonPrepState(TypedDict, total=False):
    """
    统一工作流 State — 多功能模式
    流程: intent_router → [mode 分流] → format_output
    """
    # --- 对话消息 ---
    messages: Annotated[list[AnyMessage], add_messages]

    # --- 意图路由 ---
    intent: str          # "chat" / 功能模式名
    mode: str            # 前端传入的功能模式（lesson_prep / classroom_sim / blind_spot / student_sim / interaction_design / chat）

    # --- 预留：subagent 并行模式 ---
    modes: List[str]     # 后续扩展：多个 mode 并行执行

    # --- 教师输入参数（前端表单传入） ---
    lesson_subject: str       # 学科
    lesson_topic: str         # 课题名称
    lesson_grade: str         # 年级
    lesson_objectives: str    # 教学目标
    key_points: str           # 重点
    difficult_points: str     # 难点
    lesson_duration: int      # 课时时长（分钟）
    style_preference: str     # 教学风格

    # --- 中间数据（各功能节点写入） ---
    _lesson_plan_json: str    # 教案 JSON（lesson_prep 生成）
    _classroom_sim_json: str  # 课堂预演 JSON（classroom_sim 生成）
    _blind_spot_json: str     # 盲区检测 JSON（blind_spot 生成）
    _student_sim_json: str    # 学情推演 JSON（student_sim 生成）
    _interaction_json: str    # 互动设计 JSON（interaction_design 生成）

    # --- 输出 ---
    final_output: str         # 最终格式化输出（Markdown）


class WorkflowMode:
    """工作流模式枚举"""
    LESSON_PREP = "lesson_prep"              # 教案生成
    CLASSROOM_SIM = "classroom_sim"          # 课堂预演
    BLIND_SPOT = "blind_spot"                # 盲区检测
    STUDENT_SIM = "student_sim"              # 学情推演
    INTERACTION_DESIGN = "interaction_design" # 互动设计
    CHAT = "chat"                            # 闲聊

    @classmethod
    def all_modes(cls):
        return [cls.LESSON_PREP, cls.CLASSROOM_SIM, cls.BLIND_SPOT,
                cls.STUDENT_SIM, cls.INTERACTION_DESIGN, cls.CHAT]

    @classmethod
    def is_functional(cls, mode: str) -> bool:
        """是否为功能性模式（非闲聊）"""
        return mode != cls.CHAT
