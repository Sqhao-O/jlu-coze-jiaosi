"""
教思系统 — 图入口模块

为 coze_coding_utils 框架提供图实例。
导出已编译的 StateGraph 供框架发现和使用。

重构 v2.0: 支持流式断点配置
- interrupt_after: 关键节点后暂停，支持渐进式输出
- 可通过环境变量 COZE_INTERACTIVE_MODE=true 启用
"""

import os
from langgraph.graph.state import CompiledStateGraph
from graphs import Graph as _GraphWrapper

# 创建默认图实例（lesson_prep 工作流）
_wrapper = _GraphWrapper(workflow="lesson_prep")

# ============================================================
# 断点配置
# ============================================================

# 是否启用交互模式（节点间可暂停）
INTERACTIVE_MODE = os.getenv("COZE_INTERACTIVE_MODE", "false").lower() in ("true", "1", "yes")

# 各工作流的断点节点列表 — 在这些节点执行后暂停
INTERRUPT_AFTER_NODES = {
    "lesson_prep": [
        "kb_retrieval",         # KB检索后可让用户确认检索结果
        "objectives_generation", # 目标生成后可确认方向
        "process_design",        # 教学过程后可预览核心设计
        "quality_check",         # 质量校验后可决定是否重试
    ],
    "simulation": [
        "build_virtual_classroom",  # 虚拟课堂构建后可预览学生画像
        "aggregate_results",        # 聚合后可预览模拟结果
        "bottleneck_detection",     # 瓶颈识别后可确认风险点
        "optimization_suggestions", # 优化建议后可决定是否采纳
    ],
    "growth": [
        "radar_aggregation",        # 五维聚合后可预览雷达图
        "attribution_analysis",     # 归因后可确认分析方向
    ],
}


def get_interrupt_config(workflow: str = "lesson_prep"):
    """
    获取指定工作流的断点配置。

    Args:
        workflow: 工作流名称

    Returns:
        dict: 包含 interrupt_after 的配置字典（交互模式关闭时返回空配置）
    """
    if not INTERACTIVE_MODE:
        return {}
    nodes = INTERRUPT_AFTER_NODES.get(workflow, [])
    return {"interrupt_after": nodes} if nodes else {}


def compile_graph(builder, checkpointer=None, workflow: str = "lesson_prep"):
    """
    编译 StateGraph 并应用断点配置。

    Args:
        builder: StateGraph builder 实例
        checkpointer: 可选的 checkpointer
        workflow: 工作流名称（用于获取断点配置）

    Returns:
        编译后的 CompiledStateGraph
    """
    interrupt_config = get_interrupt_config(workflow)

    if checkpointer is not None:
        return builder.compile(
            checkpointer=checkpointer,
            **interrupt_config,
        )
    return builder.compile(**interrupt_config)


# 编译图供框架发现（默认不使用 checkpointer 和断点）
graph: CompiledStateGraph = compile_graph(_wrapper.builder)

# 同时保留 builder 引用供 main.py 使用
builder = _wrapper.builder
