"""
「教思」AI教学孪生系统 — Graph Builder
TeachingThought Graph Module

为Coze平台提供工作流模式的图入口。
当 graph_helper.is_agent_proj() 为 False 时，main.py 使用本模块。

架构:
- Agent模式 (is_agent_proj=True): 使用 agents/agent.py → Agent 0 主控路由
- Graph模式 (is_agent_proj=False): 使用本模块的 StateGraph
"""

from graphs.state import TeachingState


class Graph:
    """
    Graph包装器 - 为 main.py 提供 .builder 属性

    可通过设置不同的 workflow 来切换活跃工作流:
    - workflow="lesson_prep" → 智能备课工作流
    - workflow="simulation"  → 教学推演工作流
    - workflow="growth"      → 成长分析工作流

    默认为智能备课工作流（最常用入口）。
    """

    def __init__(self, workflow: str = "lesson_prep"):
        self._workflow = workflow
        self._builder = None

    @property
    def builder(self):
        """延迟加载: 首次访问时才构建 StateGraph"""
        if self._builder is None:
            self._builder = self._build()
        return self._builder

    def _build(self):
        """根据workflow构建对应的StateGraph"""
        if self._workflow == "simulation":
            from graphs.teaching_simulation import build_teaching_simulation_graph
            return build_teaching_simulation_graph()
        elif self._workflow == "growth":
            from graphs.growth_analysis import build_growth_analysis_graph
            return build_growth_analysis_graph()
        else:
            # 默认: 智能备课
            from graphs.lesson_prep import build_lesson_prep_graph
            return build_lesson_prep_graph()


# 模块级实例 — main.py 通过 graph_helper.get_graph_instance("graphs.graph") 访问
graph = Graph()


# 便捷导出
__all__ = [
    "graph",
    "Graph",
    # 从 state.py 重导出常用类型
    "TeachingState",
    "LessonPrepState",
    "SimulationState",
    "GrowthAnalysisState",
    "WorkflowMode",
    "RiskLevel",
    "ErrorTier",
    "StudentTier",
]

# 重导出 state 中的类型方便外部使用
from graphs.state import (  # noqa: E402
    TeachingState,
    LessonPrepState,
    SimulationState,
    GrowthAnalysisState,
    WorkflowMode,
    RiskLevel,
    ErrorTier,
    StudentTier,
)
