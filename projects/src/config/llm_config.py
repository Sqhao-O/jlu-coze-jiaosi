"""
「教思」AI教学孪生系统 — 集中化 LLM 配置
Centralized LLM Configuration

解决问题3：参数冗余 — 所有 LLM 参数、模型名称、阈值集中管理。
修改一处即可全局生效。
"""

from typing import Dict, Any, Optional


# ============================================================
# 模型名称常量
# ============================================================

class ModelName:
    """模型名称常量 — 修改一处即可全局切换模型"""
    PRO = "doubao-seed-2-0-pro-260215"       # 高精度模型：复杂推理、创意生成
    LITE = "doubao-seed-2-0-lite-260215"      # 快速模型：简单任务、高并发场景


# ============================================================
# 任务类型 → 推荐模型映射
# ============================================================

# 需要使用 PRO 模型的任务类型
PRO_TASKS = {
    "kb_retrieval",
    "objectives_generation",
    "key_difficulty_design",
    "process_design",
    "tiered_exercises",
    "homework_design",
    "build_virtual_classroom",
    "bottleneck_detection",
    "risk_assessment",
    "contingency_plans",
    "optimization_suggestions",
    "comparison_report",
    "attribution_analysis",
    "achievement_discovery",
    "suggestions_generation",
    "personalized_narrative",
    "generate_lesson_plan",
    "analyze_learning_situation",
    "simulate_teaching",
    "generate_growth_report",
}

# 可以使用 LITE 模型的任务类型
LITE_TASKS = {
    "parse_requirements",
    "style_modeling",
    "parse_lesson_plan",
    "student_simulator",
    "board_design",
    "classroom_assistant",
    "data_collection",
    "data_cleaning",
    "compress_lesson_plan",
    "format_output",
}


def get_model_for_task(task_type: str) -> str:
    """根据任务类型返回推荐模型"""
    if task_type in PRO_TASKS:
        return ModelName.PRO
    if task_type in LITE_TASKS:
        return ModelName.LITE
    return ModelName.PRO  # 默认使用 PRO


# ============================================================
# Temperature 集中配置（按任务类型）
# ============================================================

class TaskTemperature:
    """各任务类型的推荐 temperature"""
    # 备课工作流
    PARSE_REQUIREMENTS = 0.3        # 需求解析：需要精确提取
    KB_RETRIEVAL = 0.5              # 知识库检索：平衡创造性与准确性
    STYLE_MODELING = 0.4            # 风格建模：适度发散
    OBJECTIVES_GENERATION = 0.6     # 教学目标：需要教学创意
    KEY_DIFFICULTY_DESIGN = 0.5     # 重难点设计：需要专业判断
    PROCESS_DESIGN = 0.7            # 教学过程：需要丰富创意
    BOARD_DESIGN = 0.5              # 板书设计：结构化输出
    TIERED_EXERCISES = 0.7          # 分层练习：需要多样性
    HOMEWORK_DESIGN = 0.6           # 作业设计：需要创意
    QUALITY_CHECK = 0.3             # 质量校验：纯逻辑判断

    # 推演工作流
    PARSE_LESSON_PLAN = 0.3         # 教案解析：结构化提取
    BUILD_VIRTUAL_CLASSROOM = 0.7   # 虚拟课堂：需要多样性
    STUDENT_SIMULATOR = 0.8         # 学生模拟：需要真实多样性
    BOTTLENECK_DETECTION = 0.5      # 瓶颈识别：专业分析
    RISK_ASSESSMENT = 0.5           # 风险评级：逻辑判断
    CONTINGENCY_PLANS = 0.6         # 应急预案：创造性方案
    OPTIMIZATION_SUGGESTIONS = 0.5  # 优化建议：专业判断
    COMPARISON_REPORT = 0.5         # 对比报告：客观分析

    # 成长分析工作流
    DIMENSION_ANALYSIS = 0.5        # 维度分析：专业评估
    ATTRIBUTION = 0.5               # 归因分析：逻辑推理
    ACHIEVEMENT_DISCOVERY = 0.8     # 成就发现：需要温暖人情味
    SUGGESTIONS_GENERATION = 0.6    # 建议生成：需要创意
    PERSONALIZED_NARRATIVE = 0.9    # 个性化寄语：高温度更自然

    # Agent 工具
    AGENT_LESSON_PLAN = 0.7         # Agent 备课
    AGENT_LEARNING_SITUATION = 0.6  # Agent 学情分析
    AGENT_SIMULATE = 0.7            # Agent 推演
    AGENT_CLASSROOM = 0.8           # Agent 课堂辅助
    AGENT_GROWTH = 0.7              # Agent 成长报告

    # 工具
    COMPRESS = 0.3                  # 教案压缩
    FORMAT_OUTPUT = 0.3             # 格式化输出

    # 默认
    DEFAULT = 0.5


# ============================================================
# max_completion_tokens 集中配置（按任务类型）
# ============================================================

class TaskMaxTokens:
    """各任务类型的推荐 max_completion_tokens"""
    PARSE_REQUIREMENTS = 1000
    KB_RETRIEVAL = 3000
    STYLE_MODELING = 1000
    OBJECTIVES_GENERATION = 3000
    KEY_DIFFICULTY_DESIGN = 2000
    PROCESS_DESIGN = 4000
    BOARD_DESIGN = 1500
    TIERED_EXERCISES = 2000
    HOMEWORK_DESIGN = 2000

    PARSE_LESSON_PLAN = 3000
    BUILD_VIRTUAL_CLASSROOM = 3000
    STUDENT_SIMULATOR = 800
    BOTTLENECK_DETECTION = 3000
    RISK_ASSESSMENT = 2000
    CONTINGENCY_PLANS = 3000
    OPTIMIZATION_SUGGESTIONS = 4000
    COMPARISON_REPORT = 3000

    DIMENSION_ANALYSIS = 1000
    ATTRIBUTION = 2000
    ACHIEVEMENT_DISCOVERY = 2000
    SUGGESTIONS_GENERATION = 2000
    PERSONALIZED_NARRATIVE = 800

    AGENT_LESSON_PLAN = 8000
    AGENT_LEARNING_SITUATION = 6000
    AGENT_SIMULATE = 10000
    AGENT_CLASSROOM = 2000
    AGENT_GROWTH = 6000

    COMPRESS = 1500
    FORMAT_OUTPUT = 8000

    DEFAULT = 2000


# ============================================================
# Thinking 模式配置
# ============================================================

DEFAULT_THINKING = "disabled"  # 所有任务默认禁用 thinking 以节省成本


# ============================================================
# 阈值常量集中管理
# ============================================================

class Thresholds:
    """所有硬编码阈值的集中管理 — 修改一处即可全局生效"""

    # --- 质量校验 ---
    LESSON_TOTAL_TIME_MIN = 30          # 教学总时间下限（分钟）
    LESSON_TOTAL_TIME_MAX = 60          # 教学总时间上限（分钟）
    MIN_TEACHING_STAGES = 4             # 最少教学环节数
    MAX_RETRIES = 3                     # 最大重试次数

    # --- 成长分析 ---
    LEVEL_EXCELLENT = 8.5               # 卓越水平阈值
    LEVEL_PROFICIENT = 7.0              # 熟练水平阈值
    LEVEL_DEVELOPING = 5.0              # 发展中水平阈值
    TREND_SIGNIFICANT_UP = 0.5          # 趋势显著上升阈值
    TREND_SIGNIFICANT_DOWN = -0.5       # 趋势显著下降阈值
    ATTRIBUTION_MIN_CHANGE = 0.5        # 归因分析最低变化阈值

    # --- 教学推演 ---
    MIN_LESSON_PLAN_LENGTH = 200        # 最小教案长度（字符）
    MAX_SIMULATION_STAGES = 5           # 推演最多聚焦环节数
    UNDERSTANDING_BOTTLENECK = 4        # 理解程度瓶颈阈值（低于此值为瓶颈）
    ENGAGEMENT_BOTTLENECK = 3           # 参与度瓶颈阈值

    # --- 风险评级 ---
    HIGH_RISK_AFFECTED_TIERS = 2        # 高风险：影响 ≥2 个层级
    MEDIUM_RISK_AFFECTED_TIERS = 1      # 中风险：影响 ≥1 个层级

    # --- 教案压缩 ---
    LESSON_PLAN_COMPRESS_THRESHOLD = 2000  # 超过此长度的教案需压缩
    LESSON_PLAN_COMPRESS_TARGET = 500      # 压缩目标长度

    # --- 系统 ---
    TIMEOUT_SECONDS = 900               # 任务超时时间（秒）
    AGENT_MAX_MESSAGES = 40             # Agent 滑动窗口大小

    # --- JSON 格式化 ---
    JSON_MIN_LENGTH_FOR_FORMAT = 50     # JSON 字符串低于此长度不格式化


# ============================================================
# 便捷函数：获取 LLM 调用参数
# ============================================================

def get_llm_params(
    task_type: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    thinking: str = DEFAULT_THINKING,
) -> Dict[str, Any]:
    """
    根据任务类型获取标准化的 LLM 调用参数。

    Args:
        task_type: 任务类型标识（如 "objectives_generation"）
        temperature: 覆盖默认 temperature（None 则使用 TaskTemperature 中的值）
        max_tokens: 覆盖默认 max_completion_tokens
        model: 覆盖默认模型
        thinking: thinking 模式（默认 "disabled"）

    Returns:
        包含 model, temperature, max_completion_tokens, thinking 的字典

    Usage:
        params = get_llm_params("objectives_generation")
        response = client.invoke(messages=messages, **params)
    """
    # 映射 task_type 到 TaskTemperature 和 TaskMaxTokens
    temp_map = {
        "parse_requirements": TaskTemperature.PARSE_REQUIREMENTS,
        "kb_retrieval": TaskTemperature.KB_RETRIEVAL,
        "style_modeling": TaskTemperature.STYLE_MODELING,
        "objectives_generation": TaskTemperature.OBJECTIVES_GENERATION,
        "key_difficulty_design": TaskTemperature.KEY_DIFFICULTY_DESIGN,
        "process_design": TaskTemperature.PROCESS_DESIGN,
        "board_design": TaskTemperature.BOARD_DESIGN,
        "tiered_exercises": TaskTemperature.TIERED_EXERCISES,
        "homework_design": TaskTemperature.HOMEWORK_DESIGN,
        "quality_check": TaskTemperature.QUALITY_CHECK,
        "parse_lesson_plan": TaskTemperature.PARSE_LESSON_PLAN,
        "build_virtual_classroom": TaskTemperature.BUILD_VIRTUAL_CLASSROOM,
        "student_simulator": TaskTemperature.STUDENT_SIMULATOR,
        "bottleneck_detection": TaskTemperature.BOTTLENECK_DETECTION,
        "risk_assessment": TaskTemperature.RISK_ASSESSMENT,
        "contingency_plans": TaskTemperature.CONTINGENCY_PLANS,
        "optimization_suggestions": TaskTemperature.OPTIMIZATION_SUGGESTIONS,
        "comparison_report": TaskTemperature.COMPARISON_REPORT,
        "dimension_analysis": TaskTemperature.DIMENSION_ANALYSIS,
        "attribution_analysis": TaskTemperature.ATTRIBUTION,
        "achievement_discovery": TaskTemperature.ACHIEVEMENT_DISCOVERY,
        "suggestions_generation": TaskTemperature.SUGGESTIONS_GENERATION,
        "personalized_narrative": TaskTemperature.PERSONALIZED_NARRATIVE,
        "generate_lesson_plan": TaskTemperature.AGENT_LESSON_PLAN,
        "analyze_learning_situation": TaskTemperature.AGENT_LEARNING_SITUATION,
        "simulate_teaching": TaskTemperature.AGENT_SIMULATE,
        "classroom_assistant": TaskTemperature.AGENT_CLASSROOM,
        "generate_growth_report": TaskTemperature.AGENT_GROWTH,
        "compress_lesson_plan": TaskTemperature.COMPRESS,
        "format_output": TaskTemperature.FORMAT_OUTPUT,
    }

    tokens_map = {
        "parse_requirements": TaskMaxTokens.PARSE_REQUIREMENTS,
        "kb_retrieval": TaskMaxTokens.KB_RETRIEVAL,
        "style_modeling": TaskMaxTokens.STYLE_MODELING,
        "objectives_generation": TaskMaxTokens.OBJECTIVES_GENERATION,
        "key_difficulty_design": TaskMaxTokens.KEY_DIFFICULTY_DESIGN,
        "process_design": TaskMaxTokens.PROCESS_DESIGN,
        "board_design": TaskMaxTokens.BOARD_DESIGN,
        "tiered_exercises": TaskMaxTokens.TIERED_EXERCISES,
        "homework_design": TaskMaxTokens.HOMEWORK_DESIGN,
        "parse_lesson_plan": TaskMaxTokens.PARSE_LESSON_PLAN,
        "build_virtual_classroom": TaskMaxTokens.BUILD_VIRTUAL_CLASSROOM,
        "student_simulator": TaskMaxTokens.STUDENT_SIMULATOR,
        "bottleneck_detection": TaskMaxTokens.BOTTLENECK_DETECTION,
        "risk_assessment": TaskMaxTokens.RISK_ASSESSMENT,
        "contingency_plans": TaskMaxTokens.CONTINGENCY_PLANS,
        "optimization_suggestions": TaskMaxTokens.OPTIMIZATION_SUGGESTIONS,
        "comparison_report": TaskMaxTokens.COMPARISON_REPORT,
        "dimension_analysis": TaskMaxTokens.DIMENSION_ANALYSIS,
        "attribution_analysis": TaskMaxTokens.ATTRIBUTION,
        "achievement_discovery": TaskMaxTokens.ACHIEVEMENT_DISCOVERY,
        "suggestions_generation": TaskMaxTokens.SUGGESTIONS_GENERATION,
        "personalized_narrative": TaskMaxTokens.PERSONALIZED_NARRATIVE,
        "generate_lesson_plan": TaskMaxTokens.AGENT_LESSON_PLAN,
        "analyze_learning_situation": TaskMaxTokens.AGENT_LEARNING_SITUATION,
        "simulate_teaching": TaskMaxTokens.AGENT_SIMULATE,
        "classroom_assistant": TaskMaxTokens.AGENT_CLASSROOM,
        "generate_growth_report": TaskMaxTokens.AGENT_GROWTH,
        "compress_lesson_plan": TaskMaxTokens.COMPRESS,
        "format_output": TaskMaxTokens.FORMAT_OUTPUT,
    }

    return {
        "model": model or get_model_for_task(task_type),
        "temperature": temperature if temperature is not None else temp_map.get(task_type, TaskTemperature.DEFAULT),
        "max_completion_tokens": max_tokens if max_tokens is not None else tokens_map.get(task_type, TaskMaxTokens.DEFAULT),
        "thinking": thinking,
    }
