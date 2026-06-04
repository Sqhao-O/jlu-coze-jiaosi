"""
「教思」AI教学孪生系统 — 工作流3: 成长分析 (Growth Analysis)
12节点StateGraph

流程: 数据采集 → 数据清洗 → 5维能力评估(设计/课堂/诊断/反馈/反思) →
      五维聚合 → 趋势分析 → 归因分析 → 关键事件识别 → 成就发现 →
      个性化建议 → 激励机制(寄语) → 格式化输出

参考: 方案.md 第八章 8.3 成长分析流程
"""

import json
import logging
from typing import Literal, Optional
from datetime import datetime, timedelta

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_utils.log.write_log import request_context

from graphs.state import (
    TeachingState, GrowthAnalysisState, WorkflowMode,
)

logger = logging.getLogger(__name__)


# ============================================================
# 辅助函数
# ============================================================

def _extract_text(response) -> str:
    """从LLM响应中提取文本"""
    if isinstance(response.content, str):
        return response.content
    elif isinstance(response.content, list):
        return " ".join(item.get("text", "") for item in response.content if isinstance(item, dict))
    return str(response.content)


def _parse_json(content: str, default: dict = None) -> dict:
    """安全解析JSON"""
    content = str(content).strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"):
        content = content[:-3]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning(f"[成长] JSON解析失败: {content[:200]}")
        return default or {}


# ============================================================
# 节点函数
# ============================================================

def node_data_collection(state: GrowthAnalysisState) -> dict:
    """
    节点1: 数据采集
    聚合教师的多维教学数据
    """
    ctx = request_context.get() or new_context(method="growth.collect")
    logger.info(f"[成长-节点1] 数据采集开始")

    period = state.get("analysis_period", "最近一个月")
    analysis_type = state.get("analysis_type", "综合成长报告")
    subject = state.get("lesson_subject", state.get("subject", "未指定"))

    # 模拟数据采集 (实际环境中从DB/S3读取)
    collected = {
        "period": period,
        "analysis_type": analysis_type,
        "subject": subject,
        "data_sources": {
            "lesson_plans": "备课记录(模拟): 本周期教案生成次数",
            "simulations": "推演记录(模拟): 教案推演次数及优化采纳率",
            "classroom_events": "课堂事件(模拟): 课堂共生体使用记录",
            "reflection_logs": "反思日志(模拟): 教师撰写的教学反思",
            "growth_snapshots": "历史快照(模拟): 上周期五维评分",
        },
        "data_quality": "模拟数据 - 仅供演示。实际使用中数据越丰富，分析越精准。",
        "collected_at": datetime.utcnow().isoformat(),
    }

    # 基于周期估算数据量
    period_days_map = {
        "最近一周": 7,
        "最近一个月": 30,
        "本学期": 120,
        "本学年": 270,
    }
    days = period_days_map.get(period, 30)
    estimated_records = max(1, days // 7)  # 每周至少1次

    collected["estimated_records"] = estimated_records
    collected["data_sufficiency"] = "充分" if estimated_records >= 3 else "有限(不足3次记录)"

    return {
        "collected_data": collected,
        "last_action": f"数据采集完成 - 周期: {period}, 估计{estimated_records}条记录",
        "workflow_mode": WorkflowMode.GROWTH_ANALYSIS,
    }


def node_data_cleaning(state: GrowthAnalysisState) -> dict:
    """
    节点2: 数据清洗
    标准化和去噪
    """
    ctx = request_context.get() or new_context(method="growth.clean")
    logger.info(f"[成长-节点2] 数据清洗开始")

    collected = state.get("collected_data", {})

    cleaned = {
        **collected,
        "cleaned_at": datetime.utcnow().isoformat(),
        "cleaning_notes": [
            "去除重复记录",
            "标准化时间戳格式",
            "标记缺失值",
        ],
    }

    return {
        "cleaned_data": cleaned,
        "last_action": "数据清洗完成",
    }


def _analyze_dimension(ctx, dimension_name: str, dimension_desc: str, collected_data: dict) -> dict:
    """通用维度分析函数"""
    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    system_prompt = f"""你是教学能力评估专家。请对教师的「{dimension_name}」维度进行评分和分析。

## 维度说明
{dimension_desc}

## 评分标准 (0-10分)
- 0-3分: 薄弱 - 该维度能力需要系统提升
- 4-6分: 发展中 - 具备基本能力，仍有提升空间
- 7-8分: 熟练 - 能力较为成熟，运用自如
- 9-10分: 卓越 - 该维度达到优秀水平，可作为示范

## 输出格式 (JSON)
{{
  "score": 6.5,
  "level": "发展中",
  "strengths": ["优势1", "优势2"],
  "weaknesses": ["待改进1"],
  "evidence": "评分依据(1句话)",
  "growth_from_last": 0.3,
  "recommendation": "提升建议(1句话)"
}}
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"教学数据: {json.dumps(collected_data, ensure_ascii=False)[:2000]}")
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.5,
        max_completion_tokens=1000,
        thinking="disabled"
    )

    return _parse_json(_extract_text(response), {
        "score": 6.0,
        "level": "发展中",
        "strengths": ["持续使用教学工具"],
        "weaknesses": ["数据不足难以精确评估"],
        "evidence": "基于可用数据评估",
        "growth_from_last": 0.0,
        "recommendation": "继续积累教学数据以获得更精准分析",
    })


def node_dimension_design(state: GrowthAnalysisState) -> dict:
    """节点3: 维度1 - 教学设计力"""
    ctx = request_context.get() or new_context(method="growth.dim1")
    logger.info(f"[成长-节点3] 教学设计力评估")

    result = _analyze_dimension(
        ctx, "教学设计力",
        "评估教师设计教案的结构化程度、目标清晰度、活动丰富度、差异化设计能力。"
        "关注: 三层目标设计质量、教学过程完整性、课标对齐度、创新性。",
        state.get("cleaned_data", {})
    )
    return {"dimension_design": result, "last_action": "教学设计力评估完成"}


def node_dimension_classroom(state: GrowthAnalysisState) -> dict:
    """节点4: 维度2 - 课堂驾驭力"""
    ctx = request_context.get() or new_context(method="growth.dim2")
    logger.info(f"[成长-节点4] 课堂驾驭力评估")

    result = _analyze_dimension(
        ctx, "课堂驾驭力",
        "评估教师的课堂追问质量、环节过渡流畅度、意外应对能力、注意力调度能力。"
        "关注: 追问深度、过渡自然度、应急反应速度、课堂氛围营造。",
        state.get("cleaned_data", {})
    )
    return {"dimension_classroom": result, "last_action": "课堂驾驭力评估完成"}


def node_dimension_diagnosis(state: GrowthAnalysisState) -> dict:
    """节点5: 维度3 - 学情诊断力"""
    ctx = request_context.get() or new_context(method="growth.dim3")
    logger.info(f"[成长-节点5] 学情诊断力评估")

    result = _analyze_dimension(
        ctx, "学情诊断力",
        "评估教师对学生认知状态的判断准确度、分层教学的适配度、错因分析的深度。"
        "关注: 学情数据使用频率、分层策略恰当性、个性化指导质量。",
        state.get("cleaned_data", {})
    )
    return {"dimension_diagnosis": result, "last_action": "学情诊断力评估完成"}


def node_dimension_feedback(state: GrowthAnalysisState) -> dict:
    """节点6: 维度4 - 评价反馈力"""
    ctx = request_context.get() or new_context(method="growth.dim4")
    logger.info(f"[成长-节点6] 评价反馈力评估")

    result = _analyze_dimension(
        ctx, "评价反馈力",
        "评估教师的作业设计层次性、评价语言精准度、反馈及时性、激励有效性。"
        "关注: 分层作业设计质量、评价语的针对性和建设性、学生进步追踪。",
        state.get("cleaned_data", {})
    )
    return {"dimension_feedback": result, "last_action": "评价反馈力评估完成"}


def node_dimension_reflection(state: GrowthAnalysisState) -> dict:
    """节点7: 维度5 - 反思成长力"""
    ctx = request_context.get() or new_context(method="growth.dim5")
    logger.info(f"[成长-节点7] 反思成长力评估")

    result = _analyze_dimension(
        ctx, "反思成长力",
        "评估教师的反思日志深度、改进措施的落实情况、自我驱动成长的意愿。"
        "关注: 反思的具体性和深度、改进计划的可执行性、持续跟踪的习惯。",
        state.get("cleaned_data", {})
    )
    return {"dimension_reflection": result, "last_action": "反思成长力评估完成"}


def node_radar_aggregation(state: GrowthAnalysisState) -> dict:
    """
    节点8: 五维聚合
    将5个维度的评分聚合为雷达图数据
    """
    ctx = request_context.get() or new_context(method="growth.aggregate")
    logger.info(f"[成长-节点8] 五维聚合开始")

    dims = {
        "教学设计力": state.get("dimension_design", {}),
        "课堂驾驭力": state.get("dimension_classroom", {}),
        "学情诊断力": state.get("dimension_diagnosis", {}),
        "评价反馈力": state.get("dimension_feedback", {}),
        "反思成长力": state.get("dimension_reflection", {}),
    }

    radar = {}
    total = 0
    for name, dim in dims.items():
        if isinstance(dim, dict):
            score = dim.get("score", 5.0)
            radar[name] = {
                "score": score,
                "level": dim.get("level", "发展中"),
                "growth": dim.get("growth_from_last", 0),
                "strength": dim.get("strengths", [None])[0] if dim.get("strengths") else "",
            }
            total += score

    avg_score = round(total / len(dims), 1) if dims else 5.0

    # 确定总体水平
    if avg_score >= 8.5:
        overall_level = "卓越"
    elif avg_score >= 7.0:
        overall_level = "熟练"
    elif avg_score >= 5.0:
        overall_level = "发展中"
    else:
        overall_level = "起步"

    # 找出最强和最弱维度
    if radar:
        strongest = max(radar.items(), key=lambda x: x[1]["score"])
        weakest = min(radar.items(), key=lambda x: x[1]["score"])
    else:
        strongest = ("", {"score": 0})
        weakest = ("", {"score": 0})

    radar_data = {
        "dimensions": radar,
        "average_score": avg_score,
        "overall_level": overall_level,
        "strongest_dimension": strongest[0],
        "weakest_dimension": weakest[0],
        "score_range": f"{min(d['score'] for d in radar.values()):.1f} - {max(d['score'] for d in radar.values()):.1f}",
    }

    logger.info(f"[成长-节点8] 五维聚合完成 - 平均{avg_score}分, 水平{overall_level}")

    return {
        "radar_data": radar_data,
        "last_action": f"五维聚合完成 - 综合评分{avg_score}/10 ({overall_level})",
    }


def node_trend_analysis(state: GrowthAnalysisState) -> dict:
    """
    节点9: 趋势分析
    与上周期对比变化方向
    """
    ctx = request_context.get() or new_context(method="growth.trend")
    logger.info(f"[成长-节点9] 趋势分析开始")

    radar = state.get("radar_data", {})
    dims = radar.get("dimensions", {})

    # 趋势判断 (基于growth_from_last字段)
    trends = {}
    improving = []
    stable = []
    declining = []

    for name, data in dims.items():
        if isinstance(data, dict):
            growth = data.get("growth", 0)
            if growth >= 0.5:
                trends[name] = "↑ 上升"
                improving.append(name)
            elif growth <= -0.5:
                trends[name] = "↓ 下降"
                declining.append(name)
            else:
                trends[name] = "→ 持平"
                stable.append(name)

    trend_analysis = {
        "dimension_trends": trends,
        "improving_dimensions": improving,
        "stable_dimensions": stable,
        "declining_dimensions": declining,
        "overall_trend": "上升" if len(improving) > len(declining) else ("下降" if len(declining) > len(improving) else "持平"),
        "note": "趋势基于本周期与上一周期评分的差值(≥0.5分视为显著变化)" if dims else "数据不足, 无法计算趋势",
    }

    return {
        "trend_analysis": trend_analysis,
        "last_action": f"趋势分析完成 - 整体趋势{trend_analysis['overall_trend']}",
    }


def node_attribution_analysis(state: GrowthAnalysisState) -> dict:
    """
    节点10: 归因分析
    对显著变化(≥1.5分)做归因解释
    """
    ctx = request_context.get() or new_context(method="growth.attribution")
    logger.info(f"[成长-节点10] 归因分析开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    dims = {
        "教学设计力": state.get("dimension_design", {}),
        "课堂驾驭力": state.get("dimension_classroom", {}),
        "学情诊断力": state.get("dimension_diagnosis", {}),
        "评价反馈力": state.get("dimension_feedback", {}),
        "反思成长力": state.get("dimension_reflection", {}),
    }

    # 找出显著变化的维度
    significant_changes = {}
    for name, dim in dims.items():
        if isinstance(dim, dict):
            growth = abs(dim.get("growth_from_last", 0))
            if growth >= 0.5:  # 阈值放宽至0.5以获取更多分析
                significant_changes[name] = {
                    "direction": "上升" if dim.get("growth_from_last", 0) > 0 else "下降",
                    "magnitude": round(growth, 1),
                }

    if not significant_changes:
        return {
            "attribution": {"summary": "本周期各项能力保持稳定，无显著变化(≥0.5分)。这是正常的教学波动。", "details": []},
            "last_action": "归因分析完成 - 无显著变化",
        }

    system_prompt = """你是教师成长归因分析专家。对教学能力的变化进行可能的归因解释。

## 输出格式 (JSON)
{
  "summary": "整体归因概述(1-2句话)",
  "details": [
    {
      "dimension": "维度名称",
      "change": "上升/下降 + 幅度",
      "possible_reasons": ["可能原因1", "可能原因2"],
      "confidence": "中/低 (基于数据量)",
      "suggestion": "建议(1句话)"
    }
  ],
  "overall_note": "所有归因分析基于数据推测，实际情况以教师自身感受为准"
}"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"显著变化维度:\n{json.dumps(significant_changes, ensure_ascii=False, indent=2)}")
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.5,
        max_completion_tokens=2000,
        thinking="disabled"
    )

    attribution = _parse_json(_extract_text(response), {
        "summary": "基于数据的归因分析",
        "details": [],
        "overall_note": "数据仅供参考",
    })

    return {
        "attribution": attribution,
        "last_action": "归因分析完成",
    }


def node_achievement_discovery(state: GrowthAnalysisState) -> dict:
    """
    节点11: 成就发现
    挖掘教师可能没意识到的进步亮点
    """
    ctx = request_context.get() or new_context(method="growth.achievement")
    logger.info(f"[成长-节点11] 成就发现开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    radar = state.get("radar_data", {})
    trend = state.get("trend_analysis", {})
    dims_data = {
        "教学设计力": state.get("dimension_design", {}),
        "课堂驾驭力": state.get("dimension_classroom", {}),
        "学情诊断力": state.get("dimension_diagnosis", {}),
        "评价反馈力": state.get("dimension_feedback", {}),
        "反思成长力": state.get("dimension_reflection", {}),
    }

    system_prompt = """你是教师成长激励专家。你的任务是发现教师可能没有意识到的"意外进步"。

## 成就发现原则
1. 不只关注分数最高的维度 (教师自己也知道)
2. 重点发现"进步最快"的维度 (即使绝对值还不高)
3. 关注"稳定性"——持续进步比偶尔高分更有价值
4. 关注"关联进步"——一个维度的提升可能带动了其他维度

## 输出格式 (JSON)
{
  "discoveries": [
    {
      "title": "成就标题(温暖有力)",
      "description": "具体发现了什么(50字)",
      "why_matters": "为什么这很重要(1句话)",
      "evidence": "支持这个发现的数据"
    }
  ],
  "celebration_message": "庆祝语(温暖, 1-2句话)"
}

至少发现2个成就, 最多4个。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"""五维数据:
{json.dumps(dims_data, ensure_ascii=False, indent=2)[:2000]}

趋势: {json.dumps(trend, ensure_ascii=False)[:500]}

雷达数据: {json.dumps(radar, ensure_ascii=False)[:500]}

请发现教师的意外进步。""")
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.8,  # 稍高温度让输出更有人情味
        max_completion_tokens=2000,
        thinking="disabled"
    )

    achievements = _parse_json(_extract_text(response), {
        "discoveries": [
            {"title": "持续使用教学工具", "description": "您坚持使用教思系统进行备课和反思，这种持续学习的习惯本身就是最大的进步。", "why_matters": "教学成长不是一蹴而就，而是日积月累", "evidence": "本周期多次使用备课和推演功能"}
        ],
        "celebration_message": "您的每一次备课、每一次反思、每一次推演，都在让自己成为更好的老师。这份坚持本身，就是最宝贵的成长。"
    })

    return {
        "achievements": achievements,
        "last_action": "成就发现完成",
    }


def node_suggestions_generation(state: GrowthAnalysisState) -> dict:
    """
    节点12: 个性化建议
    给出下阶段的2-3条具体发展建议
    """
    ctx = request_context.get() or new_context(method="growth.suggestions")
    logger.info(f"[成长-节点12] 建议生成开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    radar = state.get("radar_data", {})
    dims = radar.get("dimensions", {})
    weakest = radar.get("weakest_dimension", "")

    system_prompt = """你是教师专业发展顾问。基于五维能力评估，给出下一阶段的个性化发展建议。

## 建议要求
每条建议必须包含:
1. **为什么**: 为什么这个方向值得关注
2. **怎么提升**: 1-2条具体可执行的行动
3. **教思怎么帮你**: 教思系统中的哪个功能可以帮助

## 输出格式 (JSON)
{
  "suggestions": [
    {
      "focus": "关注维度",
      "priority": 1,
      "why": "为什么重要",
      "how": "具体怎么提升",
      "jiao_si_support": "教思怎么帮你"
    }
  ],
  "next_step": "建议的下一步行动(1句话)"
}"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"""五维评分:
{json.dumps(dims, ensure_ascii=False, indent=2)}

最需提升维度: {weakest}

请生成2-3条个性化发展建议。""")
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.6,
        max_completion_tokens=2000,
        thinking="disabled"
    )

    suggestions = _parse_json(_extract_text(response), {
        "suggestions": [
            {"focus": weakest or "教学能力", "priority": 1, "why": "持续提升教学核心能力", "how": "每周进行一次完整的备课→推演→反思循环", "jiao_si_support": "使用教学镜像体备课+策略沙盘体推演"}
        ],
        "next_step": "从现在开始，为下一堂课进行一次完整的教思循环。"
    })

    return {
        "suggestions": suggestions,
        "last_action": "发展建议生成完成",
    }


def node_personalized_narrative(state: GrowthAnalysisState) -> dict:
    """
    节点13: 个性化叙事寄语
    200字温暖成长寄语
    """
    ctx = request_context.get() or new_context(method="growth.narrative")
    logger.info(f"[成长-节点13] 寄语生成开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    radar = state.get("radar_data", {})
    achievements = state.get("achievements", {})
    trend = state.get("trend_analysis", {})
    period = state.get("analysis_period", "最近一个月")

    system_prompt = f"""你是一位温暖而专业的教育前辈。请为一位教师撰写一段200字左右的成长寄语。

## 要求
- 使用第二人称"您"
- 肯定教师的努力和进步
- 具体提到1-2个发现(基于数据)
- 温暖但不煽情
- 鼓励但不虚伪
- 结尾给人力量感

## 参考数据
- 分析周期: {period}
- 综合评分: {radar.get('average_score', 'N/A')}/10 ({radar.get('overall_level', '')})
- 整体趋势: {trend.get('overall_trend', '')}
- 成就: {json.dumps(achievements.get('discoveries', []), ensure_ascii=False)[:500]}

请写一篇200字左右的温暖寄语。直接输出寄语文字，不需要JSON格式。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="请为这位教师写一段温暖的成长寄语。")
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.9,  # 更高温度让寄语更自然温暖
        max_completion_tokens=800,
        thinking="disabled"
    )

    narrative = _extract_text(response)

    return {
        "personalized_narrative": narrative,
        "last_action": "个性化寄语生成完成",
    }


def node_format_growth_output(state: GrowthAnalysisState) -> dict:
    """
    节点14: 格式化输出
    组装完整的成长报告 (9部分)
    """
    ctx = request_context.get() or new_context(method="growth.format")
    logger.info(f"[成长-节点14] 格式化输出开始")

    collected = state.get("collected_data", {})
    radar = state.get("radar_data", {})
    trend = state.get("trend_analysis", {})
    attribution = state.get("attribution", {})
    achievements = state.get("achievements", {})
    suggestions = state.get("suggestions", {})
    narrative = state.get("personalized_narrative", "")
    period = state.get("analysis_period", "最近一个月")

    dims_data = {
        "教学设计力": state.get("dimension_design", {}),
        "课堂驾驭力": state.get("dimension_classroom", {}),
        "学情诊断力": state.get("dimension_diagnosis", {}),
        "评价反馈力": state.get("dimension_feedback", {}),
        "反思成长力": state.get("dimension_reflection", {}),
    }

    sufficiency = collected.get("data_sufficiency", "未知")
    records = collected.get("estimated_records", 0)

    # Part 1: 报告概览
    report_parts = []
    report_parts.append(f"""# 📈 教师成长报告

## 1. 报告概览

| 项目 | 内容 |
|------|------|
| 分析周期 | {period} |
| 数据记录数 | 约{records}条 |
| 数据充足性 | {sufficiency} |
| 综合评分 | **{radar.get('average_score', 'N/A')}/10** |
| 总体水平 | **{radar.get('overall_level', 'N/A')}** |
| 整体趋势 | {trend.get('overall_trend', 'N/A')} |

> {'⚠️ 本报告基于有限数据生成，随着使用记录增加，分析将更加精准。' if records < 3 else '✅ 数据较为充分，分析具有参考价值。'}

---

""")

    # Part 2: 五维能力雷达
    report_parts.append("## 2. 五维能力雷达\n")
    dims = radar.get("dimensions", {})
    if dims:
        # 生成可视化文本
        report_parts.append("```")
        report_parts.append("        教学设计力")
        report_parts.append("           ▲")
        report_parts.append("          / \\")
        report_parts.append("         /   \\")
        report_parts.append("  反思  /     \\  课堂")
        report_parts.append("  成长力├──────┤驾驭力")
        report_parts.append("        \\     /")
        report_parts.append("         \\   /")
        report_parts.append("  评价    \\ /    学情")
        report_parts.append("  反馈力   ▼   诊断力")
        report_parts.append("```\n")

        for name, data in dims.items():
            if isinstance(data, dict):
                score = data.get("score", 5)
                bar = "█" * int(score) + "░" * (10 - int(score))
                growth = data.get("growth", 0)
                arrow = "↑" if growth >= 0.5 else ("↓" if growth <= -0.5 else "→")
                report_parts.append(f"**{name}**: {bar} {score}/10 {arrow}")
        report_parts.append(f"\n最强维度: **{radar.get('strongest_dimension', '')}**  |  最需提升: **{radar.get('weakest_dimension', '')}**\n")
    else:
        report_parts.append("数据不足以生成雷达图。\n")

    report_parts.append("---\n")

    # Part 3: 各维度详细分析
    report_parts.append("## 3. 各维度详细分析\n")
    for name, dim in dims_data.items():
        if isinstance(dim, dict) and dim:
            report_parts.append(f"""### {name} — {dim.get('score', 'N/A')}/10 ({dim.get('level', '')})

**优势**: {', '.join(dim.get('strengths', ['-']))}
**待改进**: {', '.join(dim.get('weaknesses', ['-']))}
**评估依据**: {dim.get('evidence', '-')}
**提升建议**: {dim.get('recommendation', '-')}
""")

    report_parts.append("---\n")

    # Part 4: 趋势分析
    report_parts.append("## 4. 趋势分析\n")
    dim_trends = trend.get("dimension_trends", {})
    if dim_trends:
        for name, t in dim_trends.items():
            report_parts.append(f"- {name}: {t}")
        report_parts.append(f"\n**整体趋势**: {trend.get('overall_trend', 'N/A')}")
    else:
        report_parts.append("数据不足以进行趋势分析。")
    report_parts.append("\n---\n")

    # Part 5: 归因分析
    report_parts.append("## 5. 成长归因\n")
    attr_summary = attribution.get("summary", "")
    attr_details = attribution.get("details", [])
    report_parts.append(f"{attr_summary}\n")
    for d in attr_details:
        if isinstance(d, dict):
            report_parts.append(f"- **{d.get('dimension', '')}** {d.get('change', '')}: {', '.join(d.get('possible_reasons', ['-']))}")
    report_parts.append("\n---\n")

    # Part 6: 成就发现
    report_parts.append("## 6. ⭐ 成就发现\n")
    discoveries = achievements.get("discoveries", [])
    for d in discoveries:
        if isinstance(d, dict):
            report_parts.append(f"""### ✨ {d.get('title', '')}
{d.get('description', '')}

> {d.get('why_matters', '')}
""")
    report_parts.append("\n---\n")

    # Part 7: 发展建议
    report_parts.append("## 7. 🧭 发展建议\n")
    suggs = suggestions.get("suggestions", [])
    for i, s in enumerate(suggs, 1):
        if isinstance(s, dict):
            report_parts.append(f"""### 建议{i}: {s.get('focus', '')}
- **为什么**: {s.get('why', '')}
- **怎么提升**: {s.get('how', '')}
- **教思帮你**: {s.get('jiao_si_support', '')}
""")
    report_parts.append(f"**下一步**: {suggestions.get('next_step', '')}")
    report_parts.append("\n---\n")

    # Part 8: 个性化寄语
    report_parts.append("## 8. 💌 成长寄语\n")
    report_parts.append(narrative if narrative else "您在成为更好的老师的路上，每一步都算数。教思会一直陪伴着您。")
    report_parts.append("\n---\n")

    # Part 9: 反思提示
    report_parts.append("""## 9. 🤔 反思提示

请您思考以下三个问题:

1. **本周期中，哪一堂课让您最有成就感？为什么？**
2. **如果要在下个周期重点提升一个维度，您会选择哪一个？**
3. **教思系统还可以在哪些方面更好地支持您的教学？**

---
📋 **本报告由「教思」成长轨迹体生成**
💡 下一步建议: **[设定新目标]** / **[导出报告]** / **[开始新一轮备课]**
""")

    final_report = "\n".join(report_parts)

    return {
        "final_growth_report": final_report,
        "last_action": "成长报告生成完成",
        "workflow_mode": WorkflowMode.NONE,
    }


# ============================================================
# 构建 StateGraph
# ============================================================

def build_growth_analysis_graph() -> StateGraph:
    """构建成长分析14节点StateGraph"""

    builder = StateGraph(GrowthAnalysisState)

    # 添加节点
    builder.add_node("data_collection", node_data_collection)
    builder.add_node("data_cleaning", node_data_cleaning)
    builder.add_node("dimension_design", node_dimension_design)
    builder.add_node("dimension_classroom", node_dimension_classroom)
    builder.add_node("dimension_diagnosis", node_dimension_diagnosis)
    builder.add_node("dimension_feedback", node_dimension_feedback)
    builder.add_node("dimension_reflection", node_dimension_reflection)
    builder.add_node("radar_aggregation", node_radar_aggregation)
    builder.add_node("trend_analysis", node_trend_analysis)
    builder.add_node("attribution_analysis", node_attribution_analysis)
    builder.add_node("achievement_discovery", node_achievement_discovery)
    builder.add_node("suggestions_generation", node_suggestions_generation)
    builder.add_node("personalized_narrative", node_personalized_narrative)
    builder.add_node("format_output", node_format_growth_output)

    # 设置入口
    builder.set_entry_point("data_collection")

    # 连线
    builder.add_edge("data_collection", "data_cleaning")

    # 5个维度并行评估 (这里用串行简化, 实际上可以并行)
    builder.add_edge("data_cleaning", "dimension_design")
    builder.add_edge("dimension_design", "dimension_classroom")
    builder.add_edge("dimension_classroom", "dimension_diagnosis")
    builder.add_edge("dimension_diagnosis", "dimension_feedback")
    builder.add_edge("dimension_feedback", "dimension_reflection")

    # 聚合与分析
    builder.add_edge("dimension_reflection", "radar_aggregation")
    builder.add_edge("radar_aggregation", "trend_analysis")
    builder.add_edge("trend_analysis", "attribution_analysis")
    builder.add_edge("attribution_analysis", "achievement_discovery")
    builder.add_edge("achievement_discovery", "suggestions_generation")
    builder.add_edge("suggestions_generation", "personalized_narrative")
    builder.add_edge("personalized_narrative", "format_output")
    builder.add_edge("format_output", END)

    return builder
