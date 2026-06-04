"""
「教思」AI教学孪生系统 — 工作流2: 教学推演 (Teaching Simulation)
12节点StateGraph + 3路并行Send

流程: 教案解析 → 虚拟课堂构建 → [3路并行学生模拟] → 结果聚合 →
      瓶颈识别 → 风险评级 → 预案生成 → 优化建议 → 对比报告 → 格式化输出

这是「教思」最具差异化竞争力的功能——教学"风洞实验室"。
参考: 方案.md 第八章 8.2 教学推演流程
"""

import json
import logging
from typing import Literal, Optional

from langgraph.graph import StateGraph, END
from langgraph.constants import Send
from langchain_core.messages import SystemMessage, HumanMessage
from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_utils.log.write_log import request_context

from graphs.state import (
    TeachingState, SimulationState, WorkflowMode,
    RiskLevel, StudentTier,
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
        logger.warning(f"[推演] JSON解析失败: {content[:200]}")
        return default or {}


# ============================================================
# 节点函数
# ============================================================

def node_parse_lesson_plan(state: SimulationState) -> dict:
    """
    节点1: 教案解析
    将教案文本拆解为教学环节序列
    """
    ctx = request_context.get() or new_context(method="simulation.parse")
    logger.info(f"[推演-节点1] 教案解析开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    lesson_plan = state.get("source_lesson_plan", "") or state.get("lesson_plan_draft", "")

    # 教案可用性检查
    if not lesson_plan or len(lesson_plan) < 200:
        logger.warning(f"[推演-节点1] 教案不可用 (长度={len(lesson_plan) if lesson_plan else 0})")
        return {
            "last_action": "教案不可用 - 需要先生成教案",
            "workflow_mode": WorkflowMode.NONE,
        }

    system_prompt = """你是教案结构解析器。将教案文本拆解为教学环节序列，识别每个环节的:
1. 环节名称 (导入/新授/练习/拓展/总结/其他)
2. 核心内容 (这个环节在教什么? 1句话)
3. 关键教学行为 (教师在做什么?)
4. 学生预期反应 (教师期望学生如何反应?)
5. 潜在分叉点 (这个环节可能在哪些地方出现意外?)

## 输出格式 (JSON)
{
  "lesson_overview": "教案整体描述(1句话)",
  "stages": [
    {
      "stage_id": 1,
      "stage_name": "导入",
      "core_content": "",
      "teacher_action": "",
      "expected_student_response": "",
      "potential_difficulty": "",
      "duration_min": 5
    }
  ],
  "total_stages": 5,
  "key_dependencies": ["如果A环节没达成, B环节会受影响"]
}

## 约束
- 准确识别环节边界
- 核心内容一句话概括
- 潜在分叉点是真实可能发生的"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"请解析以下教案:\n\n{lesson_plan[:5000]}")
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-lite-260215",
        temperature=0.3,
        max_completion_tokens=3000,
        thinking="disabled"
    )

    parsed = _parse_json(_extract_text(response), {"stages": [], "total_stages": 0})

    stages = parsed.get("stages", [])
    # 推演范围控制: 超过5个环节聚焦前5个(核心环节)
    if len(stages) > 5:
        logger.info(f"[推演-节点1] 环节数={len(stages)}, 聚焦前5个核心环节")
        stages = stages[:5]

    return {
        "lesson_overview": parsed.get("lesson_overview", ""),
        "stages": stages,
        "total_stages": len(stages),
        "last_action": f"教案解析完成 - 识别{len(stages)}个教学环节",
    }


def node_build_virtual_classroom(state: SimulationState) -> dict:
    """
    节点2: 虚拟课堂构建
    基于学情数据创建3个层次学生角色卡
    """
    ctx = request_context.get() or new_context(method="simulation.build_classroom")
    logger.info(f"[推演-节点2] 虚拟课堂构建开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    class_profile = state.get("class_profile", {})
    grade = state.get("grade_level", state.get("grade", ""))
    subject = state.get("subject", "")
    stages = state.get("stages", [])

    system_prompt = """你是虚拟课堂构建专家。基于学情数据，创建3个层次的虚拟学生角色卡。

## 三角色定义
### 虚拟学生A (基础层 - 后30%)
- 阅读/理解速度较慢
- 抽象概念理解困难, 需要具体例子
- 可能缺乏自信, 不敢主动发言
- 对基础内容能跟上, 但遇到复杂内容容易放弃

### 虚拟学生B (进阶层 - 中间50%)
- 能跟上教学节奏
- 知识掌握尚可但缺乏深度思考习惯
- 能回答直接问题但难以举一反三
- 课堂参与度中等, 随大流

### 虚拟学生C (挑战层 - 前20%)
- 理解力强, 学得快
- 容易感到无聊, 需要额外刺激
- 喜欢挑战性问题
- 可能不耐烦重复性内容

## 输出格式 (JSON)
{
  "student_a": {
    "name": "小明(化名)",
    "tier": "基础层",
    "cognitive_profile": "认知特征描述(50字)",
    "personality": "性格特征(30字)",
    "learning_style": "学习风格(30字)",
    "current_state": "当前这堂课开始时的心理状态(50字)",
    "typical_response_pattern": "典型反应模式(50字)"
  },
  "student_b": { ... },
  "student_c": { ... },
  "class_atmosphere": "班级整体氛围描述(50字)"
}"""

    user_content = f"""请构建虚拟课堂:
- 年级: {grade}
- 学科: {subject}
- 班级画像: {json.dumps(class_profile, ensure_ascii=False) if class_profile else '使用典型水平假设'}
- 教学环节预览: {[s.get('stage_name', '') for s in stages] if stages else '待解析'}

请创建三个层次的虚拟学生角色卡。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.7,
        max_completion_tokens=3000,
        thinking="disabled"
    )

    students = _parse_json(_extract_text(response), {"student_a": {}, "student_b": {}, "student_c": {}})

    return {
        "virtual_students": students,
        "class_atmosphere": students.get("class_atmosphere", ""),
        "last_action": "虚拟课堂构建完成 - 3个层次学生角色已就位",
    }


# ============================================================
# 3路并行学生模拟 (LangGraph Send)
# ============================================================

def continue_to_student_simulations(state: SimulationState) -> list[Send]:
    """
    Send分发节点: 为每个教学环节×每个学生层次生成模拟任务
    使用LangGraph Send机制实现3路并行

    每个Send目标: student_simulator节点
    """
    stages = state.get("stages", [])
    students = state.get("virtual_students", {})

    if not stages:
        logger.warning("[推演-Send] 无教学环节, 跳过模拟")
        return []

    # 为每个环节×每个学生层次创建Send
    sends = []
    student_keys = [
        ("student_a", StudentTier.BASIC),
        ("student_b", StudentTier.INTERMEDIATE),
        ("student_c", StudentTier.ADVANCED),
    ]

    for stage in stages:
        stage_id = stage.get("stage_id", 0)
        stage_name = stage.get("stage_name", "")
        for skey, tier in student_keys:
            if skey in students:
                sends.append(Send(
                    "student_simulator",
                    {
                        "stage_id": stage_id,
                        "stage_name": stage_name,
                        "stage_data": stage,
                        "student_key": skey,
                        "student_tier": tier,
                        "student_profile": students.get(skey, {}),
                    }
                ))

    logger.info(f"[推演-Send] 分发{len(sends)}个并行模拟任务 ({len(stages)}环节 × 3学生)")
    return sends


def node_student_simulator(state: dict) -> dict:
    """
    学生模拟器节点 (3路并行)
    以单个学生的视角模拟对某个教学环节的反应

    使用lite模型以降低延迟和成本
    """
    ctx = request_context.get() or new_context(method="simulation.student_sim")
    stage_name = state.get("stage_name", "")
    student_tier = state.get("student_tier", "")
    student_profile = state.get("student_profile", {})

    logger.info(f"[推演-模拟] {student_tier}学生 对 '{stage_name}' 环节的反应")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    system_prompt = f"""你是一个真实的学生模拟器。你现在扮演一位{student_tier}学生。

## 你的角色设定
{json.dumps(student_profile, ensure_ascii=False, indent=2)}

## 模拟要求
请以该学生的视角，对当前教学环节做出真实反应。你必须:

1. **注意力状态**: 此刻是否专注? 在想什么? (1句话)
2. **理解程度**: 对这个环节的内容理解了多少? 哪里卡住了? (1句话)
3. **内心独白**: 以学生身份说出此刻的想法、困惑或发现 (口语化, 1-2句)
4. **可能的外在表现**: 教师能从外表观察到的行为 (抬头发呆/做笔记/举手/和同桌说话等)
5. **如果被点名回答**: 你会怎么回答? (口语化, 1-2句)

## 约束
- 绝对真实: 不能"开上帝视角", 不能用教师视角评价教学
- 口语化表达: 使用学生真实的口语
- 可以犯错: 基础层学生可以有理解错误
- 不评价教学: 不使用"这个老师教得不好"之类表达
- 体现层次差异: {student_tier}学生的反应应符合其认知水平

## 输出格式 (JSON)
{{
  "attention": "注意力状态描述",
  "understanding_level": "理解程度(0-10)",
  "inner_monologue": "内心独白(口语化)",
  "external_behavior": "外在表现",
  "if_called_answer": "被点名时的回答(口语化)",
  "confusion_points": ["困惑点1", "困惑点2"],
  "engagement_score": 参与度(0-10)
}}"""

    stage_data = state.get("stage_data", {})
    user_content = f"""当前教学环节: {stage_name}
环节内容: {stage_data.get('core_content', '')}
教师在做什么: {stage_data.get('teacher_action', '')}
教师期望的反应: {stage_data.get('expected_student_response', '')}

请以{student_tier}学生的视角做出真实反应。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-lite-260215",  # lite模型 - 快速响应
        temperature=0.8,  # 稍高温度增加多样性
        max_completion_tokens=800,
        thinking="disabled"
    )

    result = _parse_json(_extract_text(response), {
        "attention": "正在听讲",
        "understanding_level": 5,
        "inner_monologue": "老师在讲什么呢...",
        "external_behavior": "看着黑板",
        "if_called_answer": "嗯...我不太确定",
        "confusion_points": [],
        "engagement_score": 5,
    })

    return {
        "student_simulations": [{
            "stage_name": stage_name,
            "student_tier": student_tier,
            "student_key": state.get("student_key", ""),
            "result": result,
        }]
    }


def node_aggregate_results(state: SimulationState) -> dict:
    """
    节点6: 结果聚合
    将3路并行模拟结果按环节聚合

    注意: LangGraph Send会将每个模拟结果写入state的student_simulations列表
    """
    ctx = request_context.get() or new_context(method="simulation.aggregate")
    logger.info(f"[推演-节点6] 结果聚合开始")

    simulations = state.get("student_simulations", [])
    stages = state.get("stages", [])

    if not simulations:
        logger.warning("[推演-节点6] 无模拟结果")
        return {"last_action": "无模拟结果可聚合"}

    # 按环节聚合
    aggregated = {}
    for sim in simulations:
        if not isinstance(sim, dict):
            continue
        stage_name = sim.get("stage_name", "未知环节")
        if stage_name not in aggregated:
            aggregated[stage_name] = {
                "stage_name": stage_name,
                StudentTier.BASIC: None,
                StudentTier.INTERMEDIATE: None,
                StudentTier.ADVANCED: None,
            }
        tier = sim.get("student_tier", "")
        result = sim.get("result", {})
        if tier in [StudentTier.BASIC, StudentTier.INTERMEDIATE, StudentTier.ADVANCED]:
            aggregated[stage_name][tier] = result

    logger.info(f"[推演-节点6] 聚合完成: {len(aggregated)}个环节")

    return {
        "aggregated_results": aggregated,
        "last_action": f"三路模拟结果聚合完成 - {len(aggregated)}个环节",
    }


def node_bottleneck_detection(state: SimulationState) -> dict:
    """
    节点7: 瓶颈识别
    综合分析三个层次学生的模拟反应，识别教学瓶颈点
    """
    ctx = request_context.get() or new_context(method="simulation.bottleneck")
    logger.info(f"[推演-节点7] 瓶颈识别开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    aggregated = state.get("aggregated_results", {})

    if not aggregated:
        return {"bottleneck_list": [], "last_action": "无数据, 跳过瓶颈识别"}

    system_prompt = """你是教学瓶颈识别专家。分析三个层次学生的模拟反应，识别教学瓶颈。

## 瓶颈定义
教学瓶颈 = 某个教学环节中, 至少一个层次的学生会出现明显理解困难或参与度显著下降。

## 识别标准
1. 基础层学生理解程度 < 4 → 瓶颈信号
2. 任何层次学生参与度 < 3 → 注意力瓶颈
3. 学生内心独白中出现"不懂""不会""卡住了""无聊"等 → 理解瓶颈
4. 学生的困惑点直接指向环节核心内容 → 设计瓶颈

## 输出格式 (JSON)
{
  "bottlenecks": [
    {
      "stage_name": "环节名称",
      "risk_signals": ["基础层理解困难", "中等生注意力分散"],
      "affected_tiers": ["基础层", "进阶层"],
      "root_cause": "根本原因分析(1句话)",
      "severity": "high/medium/low"
    }
  ],
  "overall_assessment": "整体评估(肯定优点+指出问题, 50字)"
}"""

    user_content = f"""三路学生模拟聚合结果:
{json.dumps(aggregated, ensure_ascii=False, indent=2)[:6000]}

请识别教学瓶颈。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.5,
        max_completion_tokens=3000,
        thinking="disabled"
    )

    result = _parse_json(_extract_text(response), {"bottlenecks": [], "overall_assessment": ""})

    bottlenecks = result.get("bottlenecks", [])
    logger.info(f"[推演-节点7] 识别到{len(bottlenecks)}个瓶颈")

    return {
        "bottleneck_list": bottlenecks,
        "overall_assessment": result.get("overall_assessment", ""),
        "last_action": f"瓶颈识别完成 - 发现{len(bottlenecks)}个潜在问题",
    }


def node_risk_assessment(state: SimulationState) -> dict:
    """
    节点8: 风险评级
    对每个瓶颈点进行红/黄/绿风险评级
    """
    ctx = request_context.get() or new_context(method="simulation.risk")
    logger.info(f"[推演-节点8] 风险评级开始")

    bottlenecks = state.get("bottleneck_list", [])

    if not bottlenecks:
        return {
            "risk_assessment": {"overall_risk": RiskLevel.GREEN, "items": []},
            "last_action": "无瓶颈, 风险评级为绿色",
        }

    risk_items = []
    high_count = 0
    medium_count = 0
    low_count = 0

    for bn in bottlenecks:
        severity = bn.get("severity", "medium")
        affected = bn.get("affected_tiers", [])
        stage_name = bn.get("stage_name", "")

        # 风险评级逻辑
        if severity == "high" or len(affected) >= 2:
            risk_level = RiskLevel.RED
            high_count += 1
        elif severity == "medium" or len(affected) >= 1:
            risk_level = RiskLevel.YELLOW
            medium_count += 1
        else:
            risk_level = RiskLevel.GREEN
            low_count += 1

        risk_items.append({
            "stage": stage_name,
            "risk_level": risk_level,
            "affected_tiers": affected,
            "root_cause": bn.get("root_cause", ""),
            "risk_signals": bn.get("risk_signals", []),
        })

    # 总体风险: 取最高等级
    if high_count > 0:
        overall = RiskLevel.RED
    elif medium_count > 0:
        overall = RiskLevel.YELLOW
    else:
        overall = RiskLevel.GREEN

    risk_assessment = {
        "overall_risk": overall,
        "summary": f"🔴{high_count}个高风险 🟡{medium_count}个中风险 🟢{low_count}个低风险",
        "items": risk_items,
    }

    logger.info(f"[推演-节点8] 风险评级: {risk_assessment['summary']}")

    return {
        "risk_assessment": risk_assessment,
        "last_action": f"风险评级完成 - {risk_assessment['summary']}",
    }


def node_contingency_plans(state: SimulationState) -> dict:
    """
    节点9: 预案生成
    为每个中高风险瓶颈生成至少2条课堂应急预案
    """
    ctx = request_context.get() or new_context(method="simulation.contingency")
    logger.info(f"[推演-节点9] 预案生成开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    risk_items = state.get("risk_assessment", {}).get("items", [])

    # 只对红色和黄色风险生成预案
    high_risk_items = [r for r in risk_items if r.get("risk_level") in (RiskLevel.RED, RiskLevel.YELLOW)]

    if not high_risk_items:
        return {
            "contingency_plans": [],
            "last_action": "无中高风险, 无需生成预案",
        }

    system_prompt = """你是课堂应急预案专家。为教学风险点生成教师可当场执行的应急方案。

## 预案要求
- 必须是教师能当场执行的"一句话动作"
- 不需要额外准备材料或设备
- 包含: 备选提问 / 简化讲法 / 替代活动 / 快速调整策略

## 输出格式 (JSON)
{
  "plans": [
    {
      "for_stage": "环节名称",
      "risk_level": "red/yellow",
      "scenario": "可能出现的情况",
      "plan_a": "方案A: 一句话可执行操作",
      "plan_b": "方案B: 备选一句话操作",
      "signal_to_trigger": "教师观察到什么现象时应启动预案"
    }
  ]
}"""

    user_content = f"""中高风险瓶颈:
{json.dumps(high_risk_items, ensure_ascii=False, indent=2)}

请为每个风险点生成2条应急预案。预案必须是教师能当场执行的一句话动作。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.6,
        max_completion_tokens=3000,
        thinking="disabled"
    )

    result = _parse_json(_extract_text(response), {"plans": []})
    plans = result.get("plans", [])

    logger.info(f"[推演-节点9] 生成了{len(plans)}条应急预案")

    return {
        "contingency_plans": plans,
        "last_action": f"应急预案生成完成 - {len(plans)}条方案",
    }


def node_optimization_suggestions(state: SimulationState) -> dict:
    """
    节点10: 优化建议
    基于瓶颈分析对原始教案进行针对性优化
    """
    ctx = request_context.get() or new_context(method="simulation.optimize")
    logger.info(f"[推演-节点10] 优化建议生成开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    bottlenecks = state.get("bottleneck_list", [])
    lesson_plan = state.get("source_lesson_plan", "")
    risk_assessment = state.get("risk_assessment", {})

    if not bottlenecks:
        return {
            "optimization_suggestions": {"changes": [], "summary": "教案设计良好, 无需优化"},
            "last_action": "无瓶颈, 教案无需优化",
        }

    system_prompt = """你是教学方案优化专家。基于推演发现的瓶颈，对原始教案进行**精准优化**。

## 优化原则
1. 只修改有瓶颈的环节
2. 每个修改必须回答三要素: 改了什么 / 为什么改 / 预期效果
3. 保留原始方案的优点
4. 不改变教案的整体结构和教学主线
5. 教师可以选择不接受优化

## 优化策略库
- 瓶颈: 学生理解困难 → 增加具体例子/可视化/类比
- 瓶颈: 学生注意力分散 → 增加互动环节/变换节奏
- 瓶颈: 高层次学生无聊 → 增加弹性挑战任务
- 瓶颈: 环节过渡生硬 → 增加过渡语/铺垫

## 输出格式 (JSON)
{
  "changes": [
    {
      "stage": "环节名称",
      "original": "原始设计的核心(1句话)",
      "optimized": "优化后的设计(1句话)",
      "reason": "为什么这样改",
      "expected_effect": "预期效果",
      "keep_original_option": true
    }
  ],
  "summary": "优化总结"
}"""

    user_content = f"""瓶颈列表:
{json.dumps(bottlenecks, ensure_ascii=False, indent=2)[:3000]}

风险评级: {risk_assessment.get('summary', '')}

原始教案(相关部分):
{lesson_plan[:3000]}

请生成优化建议。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.5,
        max_completion_tokens=4000,
        thinking="disabled"
    )

    suggestions = _parse_json(_extract_text(response), {"changes": [], "summary": ""})

    return {
        "optimization_suggestions": suggestions,
        "last_action": f"优化建议生成完成 - {len(suggestions.get('changes', []))}处改动",
    }


def node_comparison_report(state: SimulationState) -> dict:
    """
    节点11: 对比报告
    原始方案 vs 优化方案的差异对比
    """
    ctx = request_context.get() or new_context(method="simulation.compare")
    logger.info(f"[推演-节点11] 对比报告生成开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    suggestions = state.get("optimization_suggestions", {})
    changes = suggestions.get("changes", [])
    lesson_plan = state.get("source_lesson_plan", "")

    if not changes:
        return {
            "comparison_report": "✅ 教案设计优秀，推演未发现需要优化的瓶颈。原始方案可以直接使用。",
            "last_action": "无改动, 对比报告为空",
        }

    system_prompt = """你是教学方案对比分析专家。请生成原始方案与优化方案的清晰对比。

## 输出格式
### 改动概览
- 总改动数: X处
- 影响环节: [列出]

### 逐项对比
对每处改动:
- 📍 环节: [名称]
- ❌ 原始: [原始设计]
- ✅ 优化: [优化设计]
- 💡 理由: [为什么改]
- 🎯 预期: [预期效果]

### 整体评价
- 优化后的方案保留了原始方案的[优点]
- 主要改进在[方面]
- 建议教师在[环节]特别关注

用简洁的Markdown格式。不要输出JSON。"""

    user_content = f"""原始教案摘要: {lesson_plan[:1000]}

优化改动:
{json.dumps(changes, ensure_ascii=False, indent=2)}

请生成原始方案 vs 优化方案的对比报告。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.5,
        max_completion_tokens=3000,
        thinking="disabled"
    )

    report = _extract_text(response)

    return {
        "comparison_report": report,
        "last_action": "方案对比报告生成完成",
    }


def node_format_simulation_output(state: SimulationState) -> dict:
    """
    节点12: 格式化输出
    组装6部分完整推演报告
    """
    ctx = request_context.get() or new_context(method="simulation.format")
    logger.info(f"[推演-节点12] 格式化输出开始")

    # 收集所有结果
    overview = state.get("overall_assessment", "")
    aggregated = state.get("aggregated_results", {})
    bottlenecks = state.get("bottleneck_list", [])
    risk = state.get("risk_assessment", {})
    contingencies = state.get("contingency_plans", [])
    suggestions = state.get("optimization_suggestions", {})
    comparison = state.get("comparison_report", "")

    # Part 1: 推演概览
    report_parts = []
    report_parts.append(f"""# 🎯 教学推演报告

## 第一部分: 推演概览

{overview if overview else '本推演基于三层次学生模拟，对教案进行了全面预演分析。'}

**风险总评**: {risk.get('summary', '未评估')}

---
""")

    # Part 2: 环节模拟
    report_parts.append("## 第二部分: 环节模拟\n")
    for stage_name, stage_data in aggregated.items():
        if isinstance(stage_data, dict):
            report_parts.append(f"### 📍 {stage_name}\n")
            report_parts.append("| 学生层次 | 注意力 | 理解度 | 内心独白 | 外在表现 |")
            report_parts.append("|---------|--------|--------|---------|---------|")
            for tier in [StudentTier.BASIC, StudentTier.INTERMEDIATE, StudentTier.ADVANCED]:
                sim = stage_data.get(tier, {}) if isinstance(stage_data, dict) else {}
                if sim and isinstance(sim, dict):
                    attn = sim.get("attention", "-")[:15]
                    und = sim.get("understanding_level", "-")
                    inner = sim.get("inner_monologue", "-")[:20]
                    ext = sim.get("external_behavior", "-")[:15]
                    report_parts.append(f"| {tier} | {attn} | {und}/10 | {inner} | {ext} |")
            report_parts.append("")

    report_parts.append("---\n")

    # Part 3: 瓶颈分析
    report_parts.append("## 第三部分: 瓶颈分析\n")
    if bottlenecks:
        for i, bn in enumerate(bottlenecks, 1):
            severity = bn.get("severity", "medium")
            emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")
            report_parts.append(f"""### {emoji} 瓶颈{i}: {bn.get('stage_name', '')}
- **影响范围**: {', '.join(bn.get('affected_tiers', []))}
- **根本原因**: {bn.get('root_cause', '')}
- **风险信号**: {', '.join(bn.get('risk_signals', []))}
""")
    else:
        report_parts.append("✅ 未发现明显教学瓶颈。\n")

    report_parts.append("---\n")

    # Part 4: 方案对比
    report_parts.append("## 第四部分: 方案对比\n")
    report_parts.append(comparison if comparison else "无改动，原始方案与优化方案一致。\n")
    report_parts.append("\n---\n")

    # Part 5: 应急预案
    report_parts.append("## 第五部分: 应急预案\n")
    if contingencies:
        for i, plan in enumerate(contingencies, 1):
            if isinstance(plan, dict):
                report_parts.append(f"""### 预案{i}: {plan.get('for_stage', '')}
- **场景**: {plan.get('scenario', '')}
- **方案A**: {plan.get('plan_a', '')}
- **方案B**: {plan.get('plan_b', '')}
- **触发信号**: {plan.get('signal_to_trigger', '')}
""")
    else:
        report_parts.append("✅ 当前方案无中高风险点，无需应急预案。\n")

    report_parts.append("---\n")

    # Part 6: 教师决策
    report_parts.append("""## 第六部分: 教师决策卡

请选择下一步操作:

| 选项 | 说明 |
|------|------|
| ✅ **采用优化方案** | 将优化建议应用到教案中，重新生成优化版教案 |
| 🔄 **保留原始方案** | 我认为原始方案已经很好，不需要修改 |
| 🎛️ **选择性采纳** | 我想自己决定哪些优化要采用，哪些保留 |

---
📋 **本推演报告由「教思」策略沙盘体生成**
💡 推演完成后建议: 调整教案 → 课堂实践 → 课后用"成长轨迹体"反思
""")

    final_report = "\n".join(report_parts)

    # 生成优化后的教案片段(摘要)
    changes = suggestions.get("changes", [])
    optimized_snippet = ""
    if changes:
        optimized_snippet = f"共{len(changes)}处优化建议:\n"
        for c in changes[:3]:
            optimized_snippet += f"- [{c.get('stage', '')}] {c.get('optimized', '')}\n"

    return {
        "final_simulation_report": final_report,
        "simulation_result": {
            "risk_level": risk.get("overall_risk", RiskLevel.GREEN),
            "bottleneck_count": len(bottlenecks),
            "bottleneck_summary": ", ".join(b.get("stage_name", "") for b in bottlenecks[:3]),
            "student_a_feedback": "基础层模拟完成",
            "student_b_feedback": "进阶层模拟完成",
            "student_c_feedback": "挑战层模拟完成",
            "optimized_plan_snippet": optimized_snippet,
        },
        "last_action": "教学推演报告生成完成",
        "workflow_mode": WorkflowMode.NONE,
    }


# ============================================================
# 构建 StateGraph
# ============================================================

def build_teaching_simulation_graph() -> StateGraph:
    """构建教学推演12节点StateGraph (含3路并行Send)"""

    builder = StateGraph(SimulationState)

    # 添加节点
    builder.add_node("parse_lesson_plan", node_parse_lesson_plan)
    builder.add_node("build_virtual_classroom", node_build_virtual_classroom)
    builder.add_node("student_simulator", node_student_simulator)
    builder.add_node("aggregate_results", node_aggregate_results)
    builder.add_node("bottleneck_detection", node_bottleneck_detection)
    builder.add_node("risk_assessment", node_risk_assessment)
    builder.add_node("contingency_plans", node_contingency_plans)
    builder.add_node("optimization_suggestions", node_optimization_suggestions)
    builder.add_node("comparison_report", node_comparison_report)
    builder.add_node("format_output", node_format_simulation_output)

    # 设置入口
    builder.set_entry_point("parse_lesson_plan")

    # 连线
    builder.add_edge("parse_lesson_plan", "build_virtual_classroom")

    # 关键: 使用条件边分发3路并行模拟
    builder.add_conditional_edges(
        "build_virtual_classroom",
        continue_to_student_simulations,
        path_map=["student_simulator"]  # LangGraph会自动合并Send结果
    )

    # student_simulator → aggregate_results
    builder.add_edge("student_simulator", "aggregate_results")

    # 聚合后的串行流程
    builder.add_edge("aggregate_results", "bottleneck_detection")
    builder.add_edge("bottleneck_detection", "risk_assessment")
    builder.add_edge("risk_assessment", "contingency_plans")
    builder.add_edge("contingency_plans", "optimization_suggestions")
    builder.add_edge("optimization_suggestions", "comparison_report")
    builder.add_edge("comparison_report", "format_output")
    builder.add_edge("format_output", END)

    return builder
