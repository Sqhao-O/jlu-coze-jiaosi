"""
教思系统 — 图入口模块

为 coze_coding_utils 框架提供图实例。
导出已编译的 StateGraph 供框架发现和使用。
"""

from langgraph.graph.state import CompiledStateGraph
from graphs import Graph as _GraphWrapper

# 创建默认图实例（lesson_prep 工作流）
_wrapper = _GraphWrapper(workflow="lesson_prep")

# 编译图供框架发现
graph: CompiledStateGraph = _wrapper.builder.compile()

# 同时保留 builder 引用供 main.py 使用
builder = _wrapper.builder
