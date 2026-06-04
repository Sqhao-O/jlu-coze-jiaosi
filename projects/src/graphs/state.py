"""
「教思」AI教学孪生系统 - 全局状态定义
TeachingThought Global State Definitions

定义所有工作流和Agent共享的状态结构:
- 10个会话变量 (Conversation Variables) → LangGraph State字段
- 8个用户变量 (User Variables) → PostgreSQL持久化字段
"""

from typing import Annotated, TypedDict, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


# ============================================================
# 会话变量 - LangGraph State (10个字段)
# 这些变量在单次会话中流转，会话结束后可选择性持久化
# ============================================================

class TeachingStyle(TypedDict, total=False):
    """7维教学风格向量"""
    compactness: float      # 紧凑度 (0-1): 内容密度和节奏
    interactivity: float    # 互动度 (0-1): 师生互动的偏好程度
    depth: float            # 深度 (0-1): 对概念深入挖掘的偏好
    interest: float         # 趣味性 (0-1): 使用趣味元素的倾向
    rigor: float            # 严谨度 (0-1): 学术规范和准确性要求
    innovation: float      # 创新度 (0-1): 尝试新方法的意愿
    warmth: float           # 温度 (0-1): 情感关怀和鼓励的偏好


class KnowledgeBaseResults(TypedDict, total=False):
    """知识库检索结果缓存"""
    standards: str       # KB1: 课程标准检索结果
    textbooks: str       # KB2: 教材教参检索结果
    pedagogy: str        # KB3: 教学法检索结果
    personal: str        # KB4: 个人知识库检索结果


class SimulationResult(TypedDict, total=False):
    """教学推演结果摘要"""
    risk_level: str              # 总体风险等级: "red"/"yellow"/"green"
    bottleneck_count: int        # 瓶颈数量
    bottleneck_summary: str      # 瓶颈摘要
    student_a_feedback: str      # 基础生关键反馈
    student_b_feedback: str      # 中等生关键反馈
    student_c_feedback: str      # 优等生关键反馈
    optimized_plan_snippet: str  # 优化片段


class TeachingState(TypedDict, total=False):
    """
    教思系统全局状态 — 会话级变量

    这些变量在整个会话生命周期中流转，通过LangGraph的State机制
    在各节点之间自动传递和合并。
    """
    # --- 基础信息 ---
    subject: str                     # 当前科目: "语文"/"数学"/"英语"/.../"未指定"
    grade: str                       # 学段: "小学"/"初中"/"高中"
    grade_level: str                 # 具体年级: "一年级"~"高三"

    # --- 教学风格 ---
    teaching_style: TeachingStyle    # 7维风格向量
    style_description: str           # 风格的自然语言描述

    # --- 当前任务上下文 ---
    current_lesson_topic: str        # 当前课题名称
    lesson_plan_draft: str           # 教案全文 (>2000字自动压缩为500字摘要)
    simulation_result: SimulationResult  # 最近一次推演结果摘要
    last_action: str                 # 最近操作描述 (用于上下文连贯)

    # --- 工作流控制 ---
    workflow_mode: str               # 当前激活的工作流: "lesson_prep"/"simulation"/"growth"/"classroom"/None
    error_count: int                 # 当前工作流重试计数
    max_retries: int                 # 最大重试次数 (默认3)

    # --- 知识库缓存 ---
    kb_results: KnowledgeBaseResults # RAG检索结果缓存

    # --- 质量校验 ---
    validation_errors: list[str]     # 质量校验发现的错误列表
    validation_passed: bool          # 是否通过质量校验


# ============================================================
# 用户变量 - PostgreSQL持久化 (8个字段)
# 这些变量跨会话持久化，存储在数据库中
# ============================================================

class UserProfile(TypedDict, total=False):
    """
    用户档案 — 持久化到PostgreSQL user_profile表

    这些数据跨会话保持，用于个性化教师体验。
    """
    teacher_name: str                # 教师姓名
    subjects_taught: list[str]       # 任教科目列表
    grade_taught: str                # 任教年级
    years_of_experience: int         # 教龄
    preferred_model: str             # 偏好模型: "pro"(精准)/"lite"(快速)

    # 以下字段通过S3+DB索引存储:
    # historical_lesson_plans: list[str]  # 历史教案S3 key列表
    # teaching_journal: list[dict]        # 教学反思日志
    # growth_history: list[dict]          # 五维成长历史快照


# ============================================================
# 工作流专用State (继承自TeachingState)
# ============================================================

class LessonPrepState(TeachingState, total=False):
    """
    智能备课工作流 State

    11节点工作流专用字段，继承所有TeachingState字段。
    """
    # 输入
    lesson_subject: str              # 备课学科
    lesson_topic: str                # 备课课题
    lesson_grade: str                # 备课年级
    lesson_hours: int                # 课时数
    lesson_type: str                 # 课型: "新授课"/"复习课"/"习题课"/"实验课"/"综合课"
    style_preference: str            # 风格偏好标签

    # 中间产物
    kb_context: str                  # 融合后的知识库上下文
    style_profile: dict              # 提取的风格特征
    teaching_objectives: dict        # 三层教学目标
    key_difficult_points: dict       # 重难点分析
    teaching_process: list[dict]     # 教学过程 (5个环节)
    board_design: dict               # 板书设计
    tiered_exercises: dict           # 分层练习
    homework_design: dict            # 作业设计

    # 输出
    final_lesson_plan: str           # 最终格式化教案


class SimulationState(TeachingState, total=False):
    """
    教学推演工作流 State

    12节点工作流专用字段，支持3路并行学生模拟。
    """
    # 输入
    source_lesson_plan: str          # 待推演的完整教案文本
    class_profile: dict              # 班级画像
    focus_stage: str                 # 聚焦环节

    # 3路并行模拟结果 (由Send扇出节点产生)
    student_a_simulation: dict       # 基础生模拟结果
    student_b_simulation: dict       # 中等生模拟结果
    student_c_simulation: dict       # 优等生模拟结果

    # 聚合分析
    aggregated_results: dict         # 三路聚合结果
    bottleneck_list: list[dict]      # 瓶颈列表
    risk_assessment: dict            # 风险评级结果
    contingency_plans: list[dict]    # 应急预案列表
    optimization_suggestions: dict   # 优化建议
    comparison_report: str           # 原版vs优化版对比

    # 输出
    final_simulation_report: str     # 最终推演报告


class GrowthAnalysisState(TeachingState, total=False):
    """
    成长分析工作流 State

    12节点工作流专用字段。
    """
    # 输入
    analysis_period: str             # 分析周期
    analysis_type: str               # 报告类型

    # 数据采集
    collected_data: dict             # 采集到的原始数据
    cleaned_data: dict               # 清洗后的数据

    # 五维分析
    dimension_design: dict           # 维度1: 教学设计力
    dimension_classroom: dict        # 维度2: 课堂驾驭力
    dimension_diagnosis: dict        # 维度3: 学情诊断力
    dimension_feedback: dict         # 维度4: 评价反馈力
    dimension_reflection: dict       # 维度5: 反思成长力

    # 聚合
    radar_data: dict                 # 五维雷达图数据
    trend_analysis: dict             # 趋势分析
    attribution: dict                # 归因分析
    suggestions: list[dict]          # 发展建议

    # 输出
    final_growth_report: str         # 最终成长报告


# ============================================================
# 工作流枚举常量
# ============================================================

class WorkflowMode:
    """工作流模式枚举"""
    LESSON_PREP = "lesson_prep"           # 智能备课
    TEACHING_SIMULATION = "simulation"     # 教学推演
    GROWTH_ANALYSIS = "growth"             # 成长分析
    CLASSROOM = "classroom"                # 课堂辅助
    NONE = "none"                          # 无活跃工作流


class RiskLevel:
    """风险等级"""
    RED = "red"        # 高风险: ≥2个学生有明显困惑
    YELLOW = "yellow"  # 中风险: 仅基础层学生有困惑
    GREEN = "green"    # 低风险: 仅个别学生有轻微困惑


class ErrorTier:
    """错因层级"""
    L1_KNOWLEDGE = "L1"    # L1 知识性错误: 不知道知识点
    L2_METHOD = "L2"       # L2 方法性错误: 知道但用错方法
    L3_HABIT = "L3"        # L3 习惯性错误: 粗心/审题等习惯问题


class StudentTier:
    """学生认知层次"""
    BASIC = "基础层"       # 后30%: 需要具体例子和直观演示
    INTERMEDIATE = "进阶层" # 中间50%: 能跟上但缺乏深度思考
    ADVANCED = "挑战层"     # 前20%: 理解力强,需要额外挑战
