"""
教思系统 — Graph Builder

v3.0: 3 节点流水线
"""

from graphs.state import LessonPrepState


class Graph:
    """Graph包装器 - 为 main.py 提供 .builder 属性"""

    def __init__(self, workflow: str = "lesson_prep"):
        self._workflow = workflow
        self._builder = None

    @property
    def builder(self):
        if self._builder is None:
            self._builder = self._build()
        return self._builder

    def _build(self):
        from graphs.lesson_prep import build_lesson_prep_graph
        return build_lesson_prep_graph()


# 模块级实例
graph = Graph()

__all__ = ["graph", "Graph", "LessonPrepState"]
