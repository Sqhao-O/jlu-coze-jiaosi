"""
教思 AI 教学孪生系统 — 简化 LLM 配置

重构 v3.0: 3 种参数模板替代 21 种
- precise: 低温度，适合结构化提取
- creative: 中温度，适合教案生成
- chat: 中温度，短输出，适合闲聊
"""

from typing import Dict, Any, Optional


class ModelName:
    """模型名称常量"""
    PRO = "doubao-seed-2-0-pro-260215"
    LITE = "doubao-seed-2-0-lite-260215"


# 3 种预设模板
LLM_PRESETS = {
    "precise":  {"model": ModelName.LITE, "temperature": 0.3, "max_completion_tokens": 2000},
    "creative": {"model": ModelName.PRO,  "temperature": 0.7, "max_completion_tokens": 8000},
    "chat":     {"model": ModelName.LITE, "temperature": 0.7, "max_completion_tokens": 500},
}


class Thresholds:
    """硬编码阈值集中管理"""
    TIMEOUT_SECONDS = 900


def get_llm_params(
    preset: str = "creative",
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    根据预设模板获取 LLM 调用参数，支持覆盖。

    Args:
        preset: 预设名称 "precise" / "creative" / "chat"
        temperature: 覆盖温度
        max_tokens: 覆盖最大 token 数
        model: 覆盖模型

    Returns:
        LLM 参数字典
    """
    base = LLM_PRESETS.get(preset, LLM_PRESETS["creative"]).copy()
    if temperature is not None:
        base["temperature"] = temperature
    if max_tokens is not None:
        base["max_completion_tokens"] = max_tokens
    if model is not None:
        base["model"] = model
    return base
