"""
教思系统 — 日志追踪模块

为 coze_coding_utils 框架提供项目级日志追踪配置。
框架的 OpenAIChatHandler 等组件会动态导入本模块。
"""

from coze_coding_utils.log.loop_trace import init_run_config, init_agent_config

__all__ = ["init_run_config", "init_agent_config"]
