"""
「教思」AI教学孪生系统 — 集中化配置模块
Centralized Configuration Module

统一管理所有 LLM 参数、阈值常量和提示词。
"""

from config.llm_config import (
    LLMConfig,
    ModelName,
    TaskTemperature,
    TaskMaxTokens,
    Thresholds,
    get_llm_params,
    get_model_for_task,
)

__all__ = [
    "LLMConfig",
    "ModelName",
    "TaskTemperature",
    "TaskMaxTokens",
    "Thresholds",
    "get_llm_params",
    "get_model_for_task",
]
