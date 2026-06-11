"""
教思 AI 教学孪生系统 — 智能备课工作流 (3 节点)

重构 v3.0: 11节点 → 3节点
流程: intent_router → generate_lesson_plan → format_output

- intent_router: 关键词匹配，区分闲聊/备课
- generate_lesson_plan: 1 次 LLM 调用生成完整教案 JSON
- format_output: 纯 Python，将 JSON 转为 Markdown
"""

import json
import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_utils.log.write_log import request_context

from graphs.state import LessonPrepState
from config.llm_config import get_llm_params
from utils.json_parser import parse_json

logger = logging.getLogger(__name__)


# ============================================================
# 节点1: 意图路由
# ============================================================

# 备课关键词
LESSON_PREP_KEYWORDS = [
    "备课", "教案", "教学设计", "课程设计", "教学方案",
    "教学目标", "重难点", "教学过程", "板书设计",
    "教学反思", "分层练习", "作业设计", "课堂活动",
]

CHAT_KEYWORDS = [
    "你好", "嗨", "在吗", "谢谢", "再见", "拜拜",
    "你是谁", "什么是", "怎么用", "帮助", "介绍",
]


def node_intent_router(state: LessonPrepState) -> dict:
    """意图路由：区分闲聊 vs 备课"""
    user_input = ""
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            user_input = last_msg.content
        elif isinstance(last_msg, dict):
            user_input = last_msg.get("content", "")

    # 如果前端已经传入了学科/课题，直接判定为备课
    if state.get("lesson_subject") or state.get("lesson_topic"):
        return {"intent": "lesson_prep"}

    text = str(user_input).lower()
    prep_score = sum(1 for kw in LESSON_PREP_KEYWORDS if kw in text)
    chat_score = sum(1 for kw in CHAT_KEYWORDS if kw in text)

    if prep_score > chat_score:
        intent = "lesson_prep"
    elif chat_score > 0 and prep_score == 0:
        intent = "chat"
    else:
        # 默认走备课（用户输入的教学相关内容通常更可能是备课请求）
        intent = "lesson_prep" if prep_score > 0 else "chat"

    logger.info(f"[意图路由] input={user_input[:50]} intent={intent}")
    return {"intent": intent}


def route_intent(state: LessonPrepState) -> Literal["chat_reply", "generate_lesson_plan"]:
    """条件边：根据意图分流"""
    return "chat_reply" if state.get("intent") == "chat" else "generate_lesson_plan"


# ============================================================
# 节点2: 闲聊回复
# ============================================================

def node_chat_reply(state: LessonPrepState) -> dict:
    """闲聊回复"""
    ctx = request_context.get() or new_context(method="lesson_prep.chat")
    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    user_input = ""
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            user_input = last_msg.content
        elif isinstance(last_msg, dict):
            user_input = last_msg.get("content", "")

    system_prompt = """你是「教思」AI 教学助手，一个温暖专业的教师伙伴。
- 用简洁友好的语气回答
- 如果教师想备课，引导他们使用备课功能
- 回答控制在 3 句话以内"""

    msgs = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=str(user_input)),
    ]

    response = client.invoke(messages=msgs, **get_llm_params("chat"))
    reply = response if isinstance(response, str) else str(response)

    return {
        "messages": [AIMessage(content=reply)],
        "final_lesson_plan": reply,
    }


# ============================================================
# 节点3: 教案生成（1 次 LLM 调用）
# ============================================================

LESSON_PLAN_SYSTEM_PROMPT = """你是资深教学设计专家，根据教师提供的信息一次性生成完整教案。

## 输出要求
严格按以下 JSON 结构输出，不要遗漏任何字段，不要输出 markdown 代码块：

{
  "title": "课题标题",
  "subject": "学科",
  "grade": "年级",
  "hours": 1,
  "type": "课型",
  "standards": {
    "core_competencies": ["核心素养1", "核心素养2"],
    "curriculum_requirement": "课标要求描述"
  },
  "objectives": {
    "basic": "基础目标：全体学生应达到的标准",
    "advanced": "进阶目标：多数学生应达到的标准",
    "challenge": "挑战目标：学有余力学生可尝试"
  },
  "key_difficulties": {
    "key_point": "教学重点",
    "key_strategy": "突破策略",
    "difficult_point": "教学难点",
    "difficult_strategy": "化解策略"
  },
  "teaching_process": [
    {
      "stage": "环节名称",
      "duration": "时间（如'5分钟'）",
      "teacher_activity": "教师活动详细描述",
      "student_activity": "学生活动详细描述",
      "transition": "过渡语",
      "purpose": "设计意图"
    }
  ],
  "board_design": "板书设计描述（文字形式）",
  "exercises": {
    "basic": ["基础练习1", "基础练习2"],
    "advanced": ["提升练习1", "提升练习2"],
    "challenge": ["拓展练习1"]
  },
  "homework": {
    "required": "必做作业",
    "optional": "选做作业",
    "challenge": "挑战作业"
  },
  "reflection_prompts": ["反思要点1", "反思要点2", "反思要点3"]
}

## 规则
1. teaching_process 至少包含 4 个环节（导入、新授、练习、总结）
2. 每个环节的描述要具体可操作，不要空洞
3. 分层练习和作业要体现梯度差异
4. 整体风格要与教师指定的教学风格一致
"""


def node_generate_lesson_plan(state: LessonPrepState) -> dict:
    """教案生成：1 次 LLM 调用，生成完整教案 JSON"""
    ctx = request_context.get() or new_context(method="lesson_prep.generate")
    logger.info("[备课] 开始生成教案")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    # 从 state 中提取参数
    subject = state.get("lesson_subject", "未指定")
    topic = state.get("lesson_topic", "")
    grade = state.get("lesson_grade", "未指定")
    hours = state.get("lesson_hours", 1)
    lesson_type = state.get("lesson_type", "新授课")
    style = state.get("style_preference", "混合型")
    teacher = state.get("teacher_name", "")
    experience = state.get("years_of_experience", 5)
    concerns = state.get("key_concerns", "")

    # 如果课题为空，从用户消息中提取
    if not topic:
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            user_input = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
            topic = user_input[:50]  # 取前50字作为课题

    # 构建用户消息
    user_parts = [
        f"学科：{subject}",
        f"课题：{topic}",
        f"年级：{grade}",
        f"课时：{hours}",
        f"课型：{lesson_type}",
        f"教学风格：{style}",
    ]
    if teacher:
        user_parts.append(f"教师：{teacher}（教龄{experience}年）")
    if concerns:
        user_parts.append(f"特别关注：{concerns}")

    user_content = "请为以下需求生成完整教案：\n" + "\n".join(user_parts)

    messages = [
        SystemMessage(content=LESSON_PLAN_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    response = client.invoke(messages=messages, **get_llm_params("creative"))

    # 解析 JSON
    lesson_plan_json = parse_json(response, default=None, log_context="[备课-生成]")

    if lesson_plan_json is None:
        # JSON 解析失败，用原始文本作为教案
        logger.warning("[备课] JSON 解析失败，使用原始文本")
        lesson_plan_json = {"title": topic, "raw_text": response}

    logger.info(f"[备课] 教案生成完成")
    return {"_lesson_plan_json": json.dumps(lesson_plan_json, ensure_ascii=False)}


# ============================================================
# 节点4: 格式化输出
# ============================================================

# 中文字段映射
FIELD_NAMES = {
    "title": "课题", "subject": "学科", "grade": "年级", "hours": "课时", "type": "课型",
    "standards": "课标链接", "core_competencies": "核心素养", "curriculum_requirement": "课标要求",
    "objectives": "教学目标", "basic": "基础目标", "advanced": "进阶目标", "challenge": "挑战目标",
    "key_difficulties": "重难点", "key_point": "教学重点", "key_strategy": "突破策略",
    "difficult_point": "教学难点", "difficult_strategy": "化解策略",
    "teaching_process": "教学过程", "stage": "环节", "duration": "时长",
    "teacher_activity": "教师活动", "student_activity": "学生活动", "transition": "过渡语",
    "purpose": "设计意图", "board_design": "板书设计",
    "exercises": "分层练习", "homework": "作业设计",
    "required": "必做", "optional": "选做", "challenge": "挑战",
    "reflection_prompts": "教学反思要点",
}


def _zh(key: str) -> str:
    return FIELD_NAMES.get(key, key)


def _format_value(val, depth: int = 0) -> str:
    """递归将 JSON 值格式化为 Markdown"""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        lines = []
        for i, item in enumerate(val, 1):
            if isinstance(item, dict):
                lines.append(f"\n{'#' * (depth + 3)} 第{i}项\n")
                lines.append(_format_value(item, depth + 1))
            elif isinstance(item, str):
                lines.append(f"{i}. {item}")
            else:
                lines.append(f"{i}. {item}")
        return "\n".join(lines)
    if isinstance(val, dict):
        lines = []
        for k, v in val.items():
            zh_key = _zh(k)
            if isinstance(v, (dict, list)):
                lines.append(f"\n{'#' * (depth + 2)} {zh_key}\n")
                lines.append(_format_value(v, depth + 1))
            else:
                lines.append(f"**{zh_key}**：{v}")
        return "\n".join(lines)
    return str(val)


def node_format_output(state: LessonPrepState) -> dict:
    """格式化输出：JSON → Markdown"""
    # 闲聊场景：直接透传 chat_reply 的消息
    if state.get("intent") != "lesson_prep":
        messages = state.get("messages", [])
        last_ai = ""
        for msg in reversed(messages):
            if hasattr(msg, "content") and getattr(msg, "type", "") == "ai":
                last_ai = msg.content
                break
        if last_ai and not state.get("final_lesson_plan"):
            return {"final_lesson_plan": last_ai}
        return {}

    # 备课场景：将 JSON 转为 Markdown
    raw_json = state.get("_lesson_plan_json", "")
    if not raw_json:
        return {"final_lesson_plan": "教案生成失败，请重试。"}

    try:
        plan = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return {"final_lesson_plan": str(raw_json)}

    # 如果有 raw_text 说明是解析失败的降级
    if "raw_text" in plan:
        return {"final_lesson_plan": plan["raw_text"]}

    # 构建 Markdown 教案
    md_parts = []

    # 标题行
    title = plan.get("title", "教学设计方案")
    md_parts.append(f"# {title}\n")

    # 基本信息
    info_items = []
    for k in ["subject", "grade", "hours", "type"]:
        if k in plan:
            info_items.append(f"**{_zh(k)}**：{plan[k]}")
    if info_items:
        md_parts.append(" | ".join(info_items) + "\n")

    md_parts.append("---\n")

    # 课标链接
    if "standards" in plan:
        std = plan["standards"]
        md_parts.append(f"## {_zh('standards')}\n")
        if "core_competencies" in std:
            md_parts.append(f"**{_zh('core_competencies')}**：" + "、".join(std["core_competencies"]))
        if "curriculum_requirement" in std:
            md_parts.append(f"\n**{_zh('curriculum_requirement')}**：{std['curriculum_requirement']}")
        md_parts.append("\n")

    # 教学目标
    if "objectives" in plan:
        md_parts.append(f"## {_zh('objectives')}\n")
        for tier, label in [("basic", "基础目标"), ("advanced", "进阶目标"), ("challenge", "挑战目标")]:
            if tier in plan["objectives"]:
                md_parts.append(f"- **{label}**：{plan['objectives'][tier]}")
        md_parts.append("")

    # 重难点
    if "key_difficulties" in plan:
        kd = plan["key_difficulties"]
        md_parts.append(f"## {_zh('key_difficulties')}\n")
        for k in ["key_point", "key_strategy", "difficult_point", "difficult_strategy"]:
            if k in kd:
                md_parts.append(f"**{_zh(k)}**：{kd[k]}\n")

    # 教学过程
    if "teaching_process" in plan:
        md_parts.append(f"## {_zh('teaching_process')}\n")
        for i, stage in enumerate(plan["teaching_process"], 1):
            stage_name = stage.get("stage", f"环节{i}")
            md_parts.append(f"### {i}. {stage_name}")
            if "duration" in stage:
                md_parts.append(f"⏱ {stage['duration']}")
            md_parts.append("")
            if "teacher_activity" in stage:
                md_parts.append(f"**教师活动**：{stage['teacher_activity']}")
            if "student_activity" in stage:
                md_parts.append(f"**学生活动**：{stage['student_activity']}")
            if "transition" in stage:
                md_parts.append(f"*过渡语*：「{stage['transition']}」")
            if "purpose" in stage:
                md_parts.append(f"**设计意图**：{stage['purpose']}")
            md_parts.append("")

    # 板书设计
    if "board_design" in plan:
        md_parts.append(f"## {_zh('board_design')}\n")
        md_parts.append(plan["board_design"])
        md_parts.append("")

    # 分层练习
    if "exercises" in plan:
        md_parts.append(f"## {_zh('exercises')}\n")
        for tier in ["basic", "advanced", "challenge"]:
            if tier in plan["exercises"]:
                md_parts.append(f"### {_zh(tier)}")
                for ex in plan["exercises"][tier]:
                    md_parts.append(f"- {ex}")
                md_parts.append("")

    # 作业设计
    if "homework" in plan:
        md_parts.append(f"## {_zh('homework')}\n")
        for tier in ["required", "optional", "challenge"]:
            if tier in plan["homework"]:
                md_parts.append(f"- **{_zh(tier)}**：{plan['homework'][tier]}")
        md_parts.append("")

    # 教学反思要点
    if "reflection_prompts" in plan:
        md_parts.append(f"## {_zh('reflection_prompts')}\n")
        for rp in plan["reflection_prompts"]:
            md_parts.append(f"- {rp}")

    markdown = "\n".join(md_parts)
    return {"final_lesson_plan": markdown}


# ============================================================
# 图构建
# ============================================================

def build_lesson_prep_graph() -> StateGraph:
    """构建 3 节点备课工作流图"""
    builder = StateGraph(LessonPrepState)

    # 添加节点
    builder.add_node("intent_router", node_intent_router)
    builder.add_node("chat_reply", node_chat_reply)
    builder.add_node("generate_lesson_plan", node_generate_lesson_plan)
    builder.add_node("format_output", node_format_output)

    # 设置入口
    builder.set_entry_point("intent_router")

    # 条件路由
    builder.add_conditional_edges(
        "intent_router",
        route_intent,
        {"chat_reply": "chat_reply", "generate_lesson_plan": "generate_lesson_plan"},
    )

    # 两条路径都汇聚到 format_output
    builder.add_edge("chat_reply", "format_output")
    builder.add_edge("generate_lesson_plan", "format_output")
    builder.add_edge("format_output", END)

    return builder
