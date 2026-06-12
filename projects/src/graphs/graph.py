"""
教思系统 — 图入口模块

v3.0: 简化，统一编译逻辑
"""

from langgraph.graph.state import CompiledStateGraph
from graphs import Graph as _GraphWrapper

_wrapper = _GraphWrapper(workflow="lesson_prep")


def compile_graph(builder, checkpointer=None, workflow: str = "lesson_prep"):
    """编译 StateGraph"""
    # builder 是未编译的 StateGraph
    kwargs = {}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    return builder.compile(**kwargs)


graph = compile_graph(_wrapper.builder)
builder = _wrapper.builder
