"""
教思 AI 教学孪生系统 — 多功能工作流

v4.0: 5 种功能模式 + 闲聊
流程: intent_router → [mode 分流] → 各功能节点 → format_output

设计原则:
- 每个功能模式对应一个独立的生成节点，各自有 prompt 模板
- format_output 统一做输出格式化，根据 intent 选择不同模板
- mode 由前端显式传入，不再依赖关键词猜测
- modes 列表预留 subagent 并行模式
"""

import json
import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_utils.log.write_log import request_context

from graphs.state import LessonPrepState, WorkflowMode
from config.llm_config import get_llm_params
from utils.json_parser import parse_json

logger = logging.getLogger(__name__)


# ============================================================
# 辅助：从 state 提取教师参数
# ============================================================

def _extract_teacher_params(state: LessonPrepState) -> dict:
    """从 state 中提取教师输入参数"""
    return {
        "subject": state.get("lesson_subject", ""),
        "topic": state.get("lesson_topic", ""),
        "grade": state.get("lesson_grade", ""),
        "objectives": state.get("lesson_objectives", ""),
        "key_points": state.get("key_points", ""),
        "difficult_points": state.get("difficult_points", ""),
        "duration": state.get("lesson_duration", 45),
        "style": state.get("style_preference", ""),
    }


def _build_user_content(params: dict, action_verb: str = "生成完整教案") -> str:
    """构建用户消息（教师参数 + 动作词）"""
    parts = []
    if params["subject"]:
        parts.append(f"学科：{params['subject']}")
    parts.append(f"课题：{params['topic'] or '未指定'}")
    if params["grade"]:
        parts.append(f"年级：{params['grade']}")
    if params["objectives"]:
        parts.append(f"教学目标：{params['objectives']}")
    if params["key_points"]:
        parts.append(f"教学重点：{params['key_points']}")
    if params["difficult_points"]:
        parts.append(f"教学难点：{params['difficult_points']}")
    parts.append(f"课时时长：{params['duration']}分钟")
    if params["style"]:
        parts.append(f"教学风格：{params['style']}")

    return f"请为以下需求{action_verb}：\n" + "\n".join(parts)


def _resolve_topic(state: LessonPrepState) -> str:
    """如果课题为空，从用户消息中提取"""
    topic = state.get("lesson_topic", "")
    if not topic:
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            topic = (last_msg.content if hasattr(last_msg, "content") else str(last_msg))[:50]
    return topic


# ============================================================
# 节点1: 意图路由（基于 mode 字段）
# ============================================================

def node_intent_router(state: LessonPrepState) -> dict:
    """意图路由：基于前端传入的 mode 字段分流"""
    mode = state.get("mode", "")

    # 如果前端没有传 mode，走关键词降级逻辑
    if not mode:
        if state.get("lesson_subject") or state.get("lesson_topic"):
            mode = WorkflowMode.LESSON_PREP
        else:
            user_input = ""
            messages = state.get("messages", [])
            if messages:
                last_msg = messages[-1]
                user_input = (last_msg.content if hasattr(last_msg, "content")
                              else str(last_msg)).lower()

            prep_keywords = ["备课", "教案", "教学设计", "课程设计"]
            if any(kw in user_input for kw in prep_keywords):
                mode = WorkflowMode.LESSON_PREP
            else:
                mode = WorkflowMode.CHAT

    # intent 等于 mode（chat 保持 chat，功能模式保持原名）
    intent = mode if mode != WorkflowMode.CHAT else "chat"

    logger.info(f"[意图路由] mode={mode} intent={intent}")
    return {"intent": intent, "mode": mode}


# 路由映射：mode → 节点名
MODE_NODE_MAP = {
    WorkflowMode.CHAT:              "chat_reply",
    WorkflowMode.LESSON_PREP:       "generate_lesson_plan",
    WorkflowMode.CLASSROOM_SIM:     "simulate_classroom",
    WorkflowMode.BLIND_SPOT:        "detect_blindspots",
    WorkflowMode.STUDENT_SIM:       "simulate_students",
    WorkflowMode.INTERACTION_DESIGN: "design_interactions",
    WorkflowMode.EXAM_GEN:          "generate_exam",
    WorkflowMode.PPT_GEN:           "generate_ppt",
}


def route_intent(state: LessonPrepState) -> str:
    """条件边：根据 intent/mode 分流到对应节点"""
    intent = state.get("intent", "chat")
    return MODE_NODE_MAP.get(intent, "chat_reply")


# ============================================================
# 节点2: 闲聊回复
# ============================================================

def node_chat_reply(state: LessonPrepState) -> dict:
    """闲聊回复"""
    ctx = request_context.get() or new_context(method="chat.reply")
    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    # 构建完整对话历史（上下文联动）
    messages = state.get("messages", [])
    chat_history = []
    for msg in messages:
        if hasattr(msg, "content") and hasattr(msg, "type"):
            if msg.type == "human":
                chat_history.append(HumanMessage(content=msg.content))
            elif msg.type == "ai":
                chat_history.append(AIMessage(content=msg.content))
        elif isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                chat_history.append(HumanMessage(content=content))
            elif role == "assistant":
                chat_history.append(AIMessage(content=content))

    system_prompt = """你是「教思」AI 教学助手，一个温暖专业的教师伙伴。
- 用简洁友好的语气回答
- 如果教师想备课，引导他们使用备课功能
- 回答控制在 3 句话以内
- 注意理解上下文，记住用户之前说过的信息"""

    # RAG 上下文注入
    knowledge_context = state.get("_knowledge_context", "")
    if knowledge_context:
        system_prompt += KNOWLEDGE_CONTEXT_TEMPLATE.format(context=knowledge_context)

    msgs = [SystemMessage(content=system_prompt)] + chat_history

    response = client.invoke(messages=msgs, **get_llm_params("chat"))
    # response 是 AIMessage 对象，必须用 .content 提取纯文本
    reply = response.content if hasattr(response, "content") else str(response)

    return {
        "messages": [AIMessage(content=reply)],
        # 不设置 final_output，避免流式输出重复
        # format_output 节点会处理 final_output
    }


# ============================================================
# 节点3: 教案生成
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
    logger.info("[教案生成] 开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    params = _extract_teacher_params(state)
    params["topic"] = _resolve_topic(state)
    user_content = _build_user_content(params, "生成完整教案")

    system_prompt = LESSON_PLAN_SYSTEM_PROMPT
    # RAG 上下文注入
    knowledge_context = state.get("_knowledge_context", "")
    if knowledge_context:
        system_prompt += KNOWLEDGE_CONTEXT_TEMPLATE.format(context=knowledge_context)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    response = client.invoke(messages=messages, **get_llm_params("creative"))
    lesson_plan_json = parse_json(response, default=None, log_context="[教案生成]")

    if lesson_plan_json is None:
        logger.warning("[教案生成] JSON 解析失败，使用原始文本")
        lesson_plan_json = {"title": params["topic"], "raw_text": response}

    logger.info("[教案生成] 完成")
    return {"_lesson_plan_json": json.dumps(lesson_plan_json, ensure_ascii=False)}


# ============================================================
# 节点4: 课堂预演
# ============================================================

CLASSROOM_SIM_SYSTEM_PROMPT = """你是资深课堂观察专家，擅长预判课堂动态。你的任务是模拟这节课可能发生的典型意外情境。

## 输出要求
严格按以下 JSON 结构输出，不要遗漏任何字段，不要输出 markdown 代码块：

{
  "lesson_context": {
    "subject": "学科",
    "topic": "课题",
    "grade": "年级"
  },
  "scenarios": [
    {
      "name": "情境名称（简洁4-8字）",
      "trigger_point": "触发点：在教学的哪个环节最可能发生",
      "likelihood": "发生概率（高/中/低）",
      "student_behavior": "学生可能的表现和行为",
      "teacher_risk": "教师可能犯的错误（如忽视、急躁、跳过）",
      "response_strategy": "教师应对策略（具体可操作的话术和动作）",
      "prevention": "预防措施（课前可以做什么来降低发生概率）"
    }
  ],
  "time_risk": {
    "most_likely_overrun_stage": "最可能超时的环节",
    "reason": "超时原因分析",
    "compression_strategy": "时间压缩策略",
    "fallback_plan": "备选方案（如果时间不够怎么办）"
  },
  "overall_risk_level": "整体风险等级（高/中/低）",
  "key_reminder": "给教师的最重要的1条提醒"
}

## 规则
1. 至少模拟 4 种不同的课堂情境（学生困惑、时间失控、意外提问、课堂走偏、分层断裂等）
2. 每个情境的应对策略必须具体到可以直接使用的话术
3. 预防措施要具有可操作性
4. 基于教师提供的学科、年级、课题进行针对性分析
"""


def node_simulate_classroom(state: LessonPrepState) -> dict:
    """课堂预演：模拟课堂可能发生的意外情境"""
    ctx = request_context.get() or new_context(method="classroom_sim.generate")
    logger.info("[课堂预演] 开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    params = _extract_teacher_params(state)
    params["topic"] = _resolve_topic(state)
    user_content = _build_user_content(params, "模拟这节课可能发生的典型意外情境")

    system_prompt = CLASSROOM_SIM_SYSTEM_PROMPT
    knowledge_context = state.get("_knowledge_context", "")
    if knowledge_context:
        system_prompt += KNOWLEDGE_CONTEXT_TEMPLATE.format(context=knowledge_context)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    response = client.invoke(messages=messages, **get_llm_params("creative"))
    result = parse_json(response, default=None, log_context="[课堂预演]")

    if result is None:
        logger.warning("[课堂预演] JSON 解析失败，使用原始文本")
        result = {"lesson_context": {"topic": params["topic"]}, "raw_text": response}

    logger.info("[课堂预演] 完成")
    return {"_classroom_sim_json": json.dumps(result, ensure_ascii=False)}


# ============================================================
# 节点5: 盲区检测
# ============================================================

BLIND_SPOT_SYSTEM_PROMPT = """你是资深教学诊断专家，擅长发现教案中的逻辑漏洞和认知偏差。你的任务是审查教师的教学设计，找出潜在盲区。

## 输出要求
严格按以下 JSON 结构输出，不要遗漏任何字段，不要输出 markdown 代码块：

{
  "lesson_context": {
    "subject": "学科",
    "topic": "课题",
    "grade": "年级"
  },
  "blindspots": [
    {
      "type": "盲区类型（认知跳步/预设偏差/逻辑漏洞/评估缺失/风格脱节）",
      "location": "问题位置（具体到哪个教学环节）",
      "description": "问题描述：为什么这是一个盲区",
      "risk_level": "风险等级（高/中/低）",
      "impact": "可能造成的后果",
      "suggestion": "修改建议（具体的、可直接操作的改进方案）"
    }
  ],
  "overall_assessment": "整体评估（2-3句话总结这节课的盲区情况）",
  "priority_fix": "最需要优先修复的1个问题及建议"
}

## 规则
1. 至少找出 4 个潜在盲区，覆盖不同类型
2. 每个盲区必须具体到某个教学环节，不要泛泛而谈
3. 修改建议要具体可操作，不要"建议加强..."这类空洞建议
4. 认知跳步：从A到B的推导缺少中间步骤
5. 预设偏差：教师预设学生已掌握某个前置知识，但实际未必
6. 逻辑漏洞：教学活动与目标不匹配
7. 评估缺失：教学中缺少即时检验学生理解的环节
8. 基于教师提供的学科、年级、重点难点进行针对性分析
"""


def node_detect_blindspots(state: LessonPrepState) -> dict:
    """盲区检测：找出教案中的逻辑漏洞和认知偏差"""
    ctx = request_context.get() or new_context(method="blind_spot.generate")
    logger.info("[盲区检测] 开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    params = _extract_teacher_params(state)
    params["topic"] = _resolve_topic(state)
    user_content = _build_user_content(params, "诊断这节课可能存在的教学盲区")

    system_prompt = BLIND_SPOT_SYSTEM_PROMPT
    knowledge_context = state.get("_knowledge_context", "")
    if knowledge_context:
        system_prompt += KNOWLEDGE_CONTEXT_TEMPLATE.format(context=knowledge_context)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    response = client.invoke(messages=messages, **get_llm_params("precise"))
    result = parse_json(response, default=None, log_context="[盲区检测]")

    if result is None:
        logger.warning("[盲区检测] JSON 解析失败，使用原始文本")
        result = {"lesson_context": {"topic": params["topic"]}, "raw_text": response}

    logger.info("[盲区检测] 完成")
    return {"_blind_spot_json": json.dumps(result, ensure_ascii=False)}


# ============================================================
# 节点6: 学情推演
# ============================================================

STUDENT_SIM_SYSTEM_PROMPT = """你是资深学情分析专家，擅长从不同层次学生的视角审视教学设计。你的任务是模拟三类学生的思维路径和卡点。

## 输出要求
严格按以下 JSON 结构输出，不要遗漏任何字段，不要输出 markdown 代码块：

{
  "lesson_context": {
    "subject": "学科",
    "topic": "课题",
    "grade": "年级"
  },
  "student_profiles": [
    {
      "type": "优等生",
      "thinking_path": "这类学生在这节课的思维路径（他们会怎么想、怎么理解）",
      "boredom_point": "可能觉得无聊或缺乏挑战的环节",
      "challenge_design": "为他们设计的挑战性任务或拓展问题",
      "engagement_strategy": "保持他们投入的策略"
    },
    {
      "type": "中等生",
      "thinking_path": "这类学生在这节课的思维路径",
      "watershed": "分水岭环节（从这个环节开始可能吃力）",
      "struggle_point": "最可能卡住的概念或步骤",
      "support_strategy": "帮助他们跨越分水岭的策略"
    },
    {
      "type": "学困生",
      "thinking_path": "这类学生在这节课的思维路径",
      "block_point": "彻底卡住的环节和原因",
      "scaffold": "需要的脚手架（具体的辅助工具、分解步骤、提示语）",
      "alternative_path": "为他们设计的替代学习路径"
    }
  ],
  "classroom_dynamics": {
    "divergence_point": "三类学生理解差距最大的环节",
    "convergence_strategy": "缩小差距的教学策略",
    "differentiation_tips": "分层教学的具体操作建议"
  },
  "key_insight": "关于这节课学情的最重要的1条洞察"
}

## 规则
1. 三类学生的分析必须具体到这节课的知识点，不要泛泛而谈
2. 思维路径要模拟学生真实的内心活动（"我大概能理解...但到这里我就懵了"）
3. 脚手架和替代路径必须具体可操作
4. 基于教师提供的学科、年级、重点难点进行针对性分析
"""


def node_simulate_students(state: LessonPrepState) -> dict:
    """学情推演：模拟不同层次学生的思维路径和卡点"""
    ctx = request_context.get() or new_context(method="student_sim.generate")
    logger.info("[学情推演] 开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    params = _extract_teacher_params(state)
    params["topic"] = _resolve_topic(state)
    user_content = _build_user_content(params, "推演不同层次学生在这节课的思维路径和卡点")

    system_prompt = STUDENT_SIM_SYSTEM_PROMPT
    knowledge_context = state.get("_knowledge_context", "")
    if knowledge_context:
        system_prompt += KNOWLEDGE_CONTEXT_TEMPLATE.format(context=knowledge_context)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    response = client.invoke(messages=messages, **get_llm_params("creative"))
    result = parse_json(response, default=None, log_context="[学情推演]")

    if result is None:
        logger.warning("[学情推演] JSON 解析失败，使用原始文本")
        result = {"lesson_context": {"topic": params["topic"]}, "raw_text": response}

    logger.info("[学情推演] 完成")
    return {"_student_sim_json": json.dumps(result, ensure_ascii=False)}


# ============================================================
# 节点7: 互动设计
# ============================================================

INTERACTION_DESIGN_SYSTEM_PROMPT = """你是资深课堂互动设计专家，擅长设计生动有效的师生互动方案。你的任务是为这节课的每个教学环节设计具体的互动方案和话术。

## 输出要求
严格按以下 JSON 结构输出，不要遗漏任何字段，不要输出 markdown 代码块：

{
  "lesson_context": {
    "subject": "学科",
    "topic": "课题",
    "grade": "年级"
  },
  "interactions": [
    {
      "stage": "教学环节名称",
      "stage_purpose": "本环节的教学目的",
      "teacher_questions": [
        {
          "question": "教师提问的具体话术",
          "purpose": "这个提问的目的",
          "expected_answers": ["学生可能的回答1", "学生可能的回答2"],
          "follow_up": "根据学生回答的追问策略"
        }
      ],
      "group_activity": {
        "format": "活动形式（讨论/实验/角色扮演/竞赛/合作任务）",
        "instruction": "活动指令（对学生说的话）",
        "duration": "建议时长",
        "output": "学生需要产出的内容"
      },
      "quick_check": {
        "method": "即时评估方法（举手/投票/白板展示/小测）",
        "question": "评估问题",
        "pass_criteria": "通过标准（如何判断学生掌握了）"
      },
      "transition_script": "过渡到下一环节的衔接话术"
    }
  ],
  "icebreaker": {
    "suggestion": "课前破冰/导入的互动建议",
    "script": "具体话术"
  },
  "overall_tips": "关于这节课互动设计的1条最重要的建议"
}

## 规则
1. 至少为 4 个教学环节设计互动方案
2. 每个提问的话术必须自然、口语化，像真正的老师在说话
3. 追问策略要覆盖学生回答正确和错误两种情况
4. 小组活动要考虑课堂实际操作可行性
5. 即时评估要简单快速，不占用太多时间
6. 基于教师提供的学科、年级、教学风格进行针对性设计
"""


def node_design_interactions(state: LessonPrepState) -> dict:
    """互动设计：为每个教学环节设计师生互动方案"""
    ctx = request_context.get() or new_context(method="interaction_design.generate")
    logger.info("[互动设计] 开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    params = _extract_teacher_params(state)
    params["topic"] = _resolve_topic(state)
    user_content = _build_user_content(params, "设计每个教学环节的师生互动方案和话术")

    system_prompt = INTERACTION_DESIGN_SYSTEM_PROMPT
    knowledge_context = state.get("_knowledge_context", "")
    if knowledge_context:
        system_prompt += KNOWLEDGE_CONTEXT_TEMPLATE.format(context=knowledge_context)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    response = client.invoke(messages=messages, **get_llm_params("creative"))
    result = parse_json(response, default=None, log_context="[互动设计]")

    if result is None:
        logger.warning("[互动设计] JSON 解析失败，使用原始文本")
        result = {"lesson_context": {"topic": params["topic"]}, "raw_text": response}

    logger.info("[互动设计] 完成")
    return {"_interaction_json": json.dumps(result, ensure_ascii=False)}


# ============================================================
# 节点7: 智能命题
# ============================================================

EXAM_GEN_SYSTEM_PROMPT = """你是资深命题专家，擅长根据教学目标和重难点设计高质量试题。你的任务是为这节课生成一套完整的结构化试题。

## 输出要求
严格按以下 JSON 结构输出，不要遗漏任何字段，不要输出 markdown 代码块：

{
  "lesson_context": {
    "subject": "学科",
    "topic": "课题",
    "grade": "年级"
  },
  "exam_meta": {
    "total_score": 100,
    "suggested_duration": 45,
    "difficulty_ratio": {
      "basic": "60%",
      "advanced": "30%",
      "challenge": "10%"
    }
  },
  "questions": [
    {
      "type": "choice",
      "difficulty": "basic",
      "score": 4,
      "stem": "题干文本",
      "options": ["选项A", "选项B", "选项C", "选项D"],
      "answer": "A",
      "explanation": "解析"
    },
    {
      "type": "fill_blank",
      "difficulty": "basic",
      "score": 4,
      "stem": "题干文本，空格用____标注",
      "answer": "标准答案",
      "explanation": "解析"
    },
    {
      "type": "true_false",
      "difficulty": "basic",
      "score": 3,
      "stem": "判断题题干",
      "answer": "正确",
      "explanation": "解析"
    },
    {
      "type": "short_answer",
      "difficulty": "advanced",
      "score": 8,
      "stem": "简答题题干",
      "answer": "参考答案",
      "scoring_points": ["要点1（x分）", "要点2（x分）", "要点3（x分）"],
      "explanation": "解析"
    },
    {
      "type": "applied",
      "difficulty": "challenge",
      "score": 12,
      "stem": "应用题/计算题题干",
      "answer": "参考答案及解题过程",
      "scoring_points": ["步骤1（x分）", "步骤2（x分）", "步骤3（x分）"],
      "explanation": "解析"
    }
  ],
  "difficulty_summary": {
    "basic_score": 60,
    "basic_pct": "60%",
    "advanced_score": 30,
    "advanced_pct": "30%",
    "challenge_score": 10,
    "challenge_pct": "10%"
  },
  "exam_tips": "命题建议与使用提示"
}

## 规则
1. 选择题至少 4 道，填空题至少 3 道，判断题至少 3 道，简答题至少 2 道，应用题至少 1 道
2. 题目必须紧扣教师提供的学科、年级、重点、难点和教学目标
3. 难度分布约为基础60%、提高30%、挑战10%
4. 选择题的 4 个选项须有一定迷惑性，不能有明显错误选项
5. 题目之间不得重复考查同一知识点
6. 简答题和应用题的评分要点必须具体到分值分配
7. 各题分值之和必须等于 total_score
8. 基于教师提供的学科、年级、教学风格进行针对性命题
9. 判断题的 answer 只能是"正确"或"错误"
"""


def node_generate_exam(state: LessonPrepState) -> dict:
    """智能命题：生成结构化试题"""
    ctx = request_context.get() or new_context(method="exam_gen.generate")
    logger.info("[智能命题] 开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    params = _extract_teacher_params(state)
    params["topic"] = _resolve_topic(state)
    user_content = _build_user_content(params, "生成一套完整的结构化试题")

    system_prompt = EXAM_GEN_SYSTEM_PROMPT
    knowledge_context = state.get("_knowledge_context", "")
    if knowledge_context:
        system_prompt += KNOWLEDGE_CONTEXT_TEMPLATE.format(context=knowledge_context)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    response = client.invoke(messages=messages, **get_llm_params("creative"))
    result = parse_json(response, default=None, log_context="[智能命题]")

    if result is None:
        logger.warning("[智能命题] JSON 解析失败，使用原始文本")
        result = {"lesson_context": {"topic": params["topic"]}, "raw_text": response}

    logger.info("[智能命题] 完成")
    return {"_exam_json": json.dumps(result, ensure_ascii=False)}


# ============================================================
# 节点7.5: RAG 上下文增强（通用，所有功能模式共享）
# ============================================================

KNOWLEDGE_CONTEXT_TEMPLATE = """

【参考资料（来自知识库）】
{context}

请参考以上资料，确保生成内容与知识库中的信息一致。如果知识库内容与你的专业知识有冲突，以知识库为准并标注。"""


def node_rag_enrich(state: LessonPrepState) -> dict:
    """RAG 上下文增强：检索知识库，将相关内容写入 _knowledge_context。
    无知识库时直接跳过（不检索、不注入任何内容）。"""
    kb_id = state.get("knowledge_base_id", "")
    if not kb_id:
        logger.info("[RAG增强] 未选择知识库，跳过检索")
        return {"_knowledge_context": ""}

    # 组合查询：用户最新消息 + 课题
    query_parts = []
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        query_parts.append(last_msg.content if hasattr(last_msg, "content") else str(last_msg))
    topic = state.get("lesson_topic", "")
    if topic:
        query_parts.append(topic)
    query = " ".join(query_parts)

    if not query:
        return {"_knowledge_context": ""}

    # 检索知识库
    try:
        from knowledge.embedder import retrieve_context
        results = retrieve_context(query, kb_id, top_k=3)
    except Exception as e:
        logger.error(f"[RAG增强] 检索失败: {e}")
        return {"_knowledge_context": ""}

    if not results:
        logger.info("[RAG增强] 未检索到相关内容")
        return {"_knowledge_context": ""}

    # 拼接检索上下文
    context_parts = []
    for i, r in enumerate(results, 1):
        context_parts.append(f"【片段 {i}】\n{r.get('content', '')}")
    context = "\n\n".join(context_parts)

    logger.info(f"[RAG增强] 检索到 {len(results)} 条相关内容")
    return {"_knowledge_context": context}


# ============================================================
# 节点8: PPT 生成（调用 Coze Doc Maker 工作流）
# ============================================================

import asyncio
from utils.ppt_client import call_ppt_workflow


def node_generate_ppt(state: LessonPrepState) -> dict:
    """PPT 生成：调用 Coze Doc Maker 工作流生成 .pptx 课件"""
    logger.info("[PPT生成] 开始")

    topic = _resolve_topic(state)
    if not topic:
        topic = "教学课件"

    params = _extract_teacher_params(state)

    # 调用 Coze 工作流
    loop = asyncio.new_event_loop()
    try:
        ppt_url = loop.run_until_complete(
            call_ppt_workflow(
                topic=topic,
                subject=params.get("subject", ""),
                grade=params.get("grade", ""),
                duration=state.get("lesson_duration", 45),
                objectives=state.get("lesson_objectives", ""),
                key_points=state.get("key_points", ""),
                difficult_points=state.get("difficult_points", ""),
                style=state.get("style_preference", ""),
            )
        )
    except Exception as e:
        logger.error(f"[PPT生成] 工作流调用失败: {e}")
        ppt_url = ""
    finally:
        loop.close()

    if not ppt_url:
        return {"ppt_download_url": "", "final_output": "PPT 生成失败，请稍后重试。"}

    # 生成大纲预览（让用户在下载前知道 PPT 包含什么内容）
    preview = f"""## 📊 PPT 课件已生成

**课题**: {topic}
**学科**: {params.get('subject', '未指定')} | **年级**: {params.get('grade', '未指定')} | **课时**: {state.get('lesson_duration', 45)}分钟

### PPT 包含以下页面

1. 封面页：课题名称 + 学科 + 年级
2. 教学目标页：三维目标
3. 重难点页：重点 + 难点
4. 教学过程概览页
5. 各教学环节页：导入、新授、练习、小结
6. 板书设计页
7. 分层练习页
8. 作业布置页
9. 教学反思页

### 下载

📥 [点击下载 PPT 课件]({ppt_url})

> PPT 由 Coze Doc Maker 生成，可直接用 PowerPoint / WPS 打开编辑。
"""

    logger.info(f"[PPT生成] 完成, url={ppt_url[:80]}...")
    return {"ppt_download_url": ppt_url, "final_output": preview}


# ============================================================
# 节点8: 格式化输出（多模式）
# ============================================================

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
    # 课堂预演
    "scenarios": "课堂情境", "name": "情境", "trigger_point": "触发点",
    "likelihood": "发生概率", "student_behavior": "学生可能表现",
    "teacher_risk": "教师风险", "response_strategy": "应对策略",
    "prevention": "预防措施", "time_risk": "时间风险",
    "most_likely_overrun_stage": "最可能超时环节", "reason": "原因",
    "compression_strategy": "压缩策略", "fallback_plan": "备选方案",
    "overall_risk_level": "整体风险", "key_reminder": "关键提醒",
    # 盲区检测
    "blindspots": "盲区列表", "type": "类型", "location": "位置",
    "description": "问题描述", "risk_level": "风险等级", "impact": "可能后果",
    "suggestion": "修改建议", "overall_assessment": "整体评估", "priority_fix": "优先修复",
    # 学情推演
    "student_profiles": "学生画像", "thinking_path": "思维路径",
    "boredom_point": "无聊点", "challenge_design": "挑战设计",
    "engagement_strategy": "投入策略", "watershed": "分水岭",
    "struggle_point": "卡点", "support_strategy": "支持策略",
    "block_point": "完全卡住点", "scaffold": "脚手架",
    "alternative_path": "替代路径", "classroom_dynamics": "课堂动态",
    "divergence_point": "分化点", "convergence_strategy": "收敛策略",
    "differentiation_tips": "分层建议", "key_insight": "关键洞察",
    # 互动设计
    "interactions": "互动方案", "stage_purpose": "环节目的",
    "teacher_questions": "教师提问", "question": "问题",
    "expected_answers": "预期回答", "follow_up": "追问策略",
    "group_activity": "小组活动", "format": "形式", "instruction": "指令",
    "output": "产出", "quick_check": "即时评估", "method": "方法",
    "pass_criteria": "通过标准", "transition_script": "过渡话术",
    "icebreaker": "破冰", "overall_tips": "总体建议",
    # 智能命题
    "exam_meta": "试卷信息", "total_score": "总分",
    "suggested_duration": "建议时长", "difficulty_ratio": "难度比例",
    "questions": "试题列表", "stem": "题干", "options": "选项",
    "answer": "答案", "explanation": "解析", "scoring_points": "评分要点",
    "difficulty_summary": "难度分布", "basic_score": "基础题分值",
    "basic_pct": "基础题占比", "advanced_score": "提高题分值",
    "advanced_pct": "提高题占比", "challenge_score": "挑战题分值",
    "challenge_pct": "挑战题占比", "exam_tips": "命题建议",
    "choice": "选择题", "fill_blank": "填空题", "true_false": "判断题",
    "short_answer": "简答题", "applied": "应用题",
    "basic": "基础", "advanced": "提高", "challenge": "挑战",
    # 通用
    "lesson_context": "课程信息",
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


def _format_lesson_plan(plan: dict) -> str:
    """格式化教案输出"""
    md = []
    title = plan.get("title", "教学设计方案")
    md.append(f"# 📋 {title}\n")

    info_items = []
    for k in ["subject", "grade", "hours", "type"]:
        if k in plan:
            info_items.append(f"**{_zh(k)}**：{plan[k]}")
    if info_items:
        md.append(" | ".join(info_items) + "\n")
    md.append("---\n")

    if "standards" in plan:
        std = plan["standards"]
        md.append(f"## {_zh('standards')}\n")
        if "core_competencies" in std:
            md.append(f"**{_zh('core_competencies')}**：" + "、".join(std["core_competencies"]))
        if "curriculum_requirement" in std:
            md.append(f"\n**{_zh('curriculum_requirement')}**：{std['curriculum_requirement']}")
        md.append("\n")

    if "objectives" in plan:
        md.append(f"## {_zh('objectives')}\n")
        for tier, label in [("basic", "基础目标"), ("advanced", "进阶目标"), ("challenge", "挑战目标")]:
            if tier in plan["objectives"]:
                md.append(f"- **{label}**：{plan['objectives'][tier]}")
        md.append("")

    if "key_difficulties" in plan:
        kd = plan["key_difficulties"]
        md.append(f"## {_zh('key_difficulties')}\n")
        for k in ["key_point", "key_strategy", "difficult_point", "difficult_strategy"]:
            if k in kd:
                md.append(f"**{_zh(k)}**：{kd[k]}\n")

    if "teaching_process" in plan:
        md.append(f"## {_zh('teaching_process')}\n")
        for i, stage in enumerate(plan["teaching_process"], 1):
            stage_name = stage.get("stage", f"环节{i}")
            md.append(f"### {i}. {stage_name}")
            if "duration" in stage:
                md.append(f"⏱ {stage['duration']}")
            md.append("")
            for fk, label in [("teacher_activity", "**教师活动**"), ("student_activity", "**学生活动**")]:
                if fk in stage:
                    md.append(f"{label}：{stage[fk]}")
            if "transition" in stage:
                md.append(f"*过渡语*：「{stage['transition']}」")
            if "purpose" in stage:
                md.append(f"**设计意图**：{stage['purpose']}")
            md.append("")

    if "board_design" in plan:
        md.append(f"## {_zh('board_design')}\n{plan['board_design']}\n")

    if "exercises" in plan:
        md.append(f"## {_zh('exercises')}\n")
        for tier in ["basic", "advanced", "challenge"]:
            if tier in plan["exercises"]:
                md.append(f"### {_zh(tier)}")
                for ex in plan["exercises"][tier]:
                    md.append(f"- {ex}")
                md.append("")

    if "homework" in plan:
        md.append(f"## {_zh('homework')}\n")
        for tier in ["required", "optional", "challenge"]:
            if tier in plan["homework"]:
                md.append(f"- **{_zh(tier)}**：{plan['homework'][tier]}")
        md.append("")

    if "reflection_prompts" in plan:
        md.append(f"## {_zh('reflection_prompts')}\n")
        for rp in plan["reflection_prompts"]:
            md.append(f"- {rp}")

    return "\n".join(md)


def _format_classroom_sim(data: dict) -> str:
    """格式化课堂预演输出"""
    md = []
    ctx = data.get("lesson_context", {})
    title = ctx.get("topic", "课堂预演")
    md.append(f"# 🎭 课堂预演：{title}\n")

    # 情境列表
    scenarios = data.get("scenarios", [])
    for i, sc in enumerate(scenarios, 1):
        name = sc.get("name", f"情境{i}")
        likelihood = sc.get("likelihood", "")
        risk_badge = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(likelihood, "⚪")
        md.append(f"## {risk_badge} {i}. {name}")
        md.append(f"**发生概率**：{likelihood}")
        md.append(f"**触发点**：{sc.get('trigger_point', '')}")
        md.append("")
        md.append(f"### 学生可能表现\n{sc.get('student_behavior', '')}\n")
        md.append(f"### 教师风险\n{sc.get('teacher_risk', '')}\n")
        md.append(f"### 应对策略\n{sc.get('response_strategy', '')}\n")
        md.append(f"### 预防措施\n{sc.get('prevention', '')}\n")

    # 时间风险
    tr = data.get("time_risk", {})
    if tr:
        md.append("## ⏱ 时间风险分析\n")
        md.append(f"**最可能超时环节**：{tr.get('most_likely_overrun_stage', '')}")
        md.append(f"**原因**：{tr.get('reason', '')}")
        md.append(f"**压缩策略**：{tr.get('compression_strategy', '')}")
        md.append(f"**备选方案**：{tr.get('fallback_plan', '')}\n")

    overall = data.get("overall_risk_level", "")
    reminder = data.get("key_reminder", "")
    if overall or reminder:
        md.append("---\n")
        if overall:
            md.append(f"**整体风险**：{overall}")
        if reminder:
            md.append(f"\n> 💡 **关键提醒**：{reminder}")

    return "\n".join(md)


def _format_blind_spot(data: dict) -> str:
    """格式化盲区检测输出"""
    md = []
    ctx = data.get("lesson_context", {})
    title = ctx.get("topic", "盲区检测")
    md.append(f"# 🔍 盲区检测：{title}\n")

    blindspots = data.get("blindspots", [])
    for i, bs in enumerate(blindspots, 1):
        bs_type = bs.get("type", "未知")
        risk = bs.get("risk_level", "")
        risk_badge = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(risk, "⚪")
        md.append(f"## {risk_badge} {i}. [{bs_type}] {bs.get('location', '')}")
        md.append(f"**风险等级**：{risk}")
        md.append(f"**问题描述**：{bs.get('description', '')}")
        md.append(f"**可能后果**：{bs.get('impact', '')}")
        md.append(f"**修改建议**：{bs.get('suggestion', '')}\n")

    assessment = data.get("overall_assessment", "")
    fix = data.get("priority_fix", "")
    if assessment or fix:
        md.append("---\n")
        if assessment:
            md.append(f"**整体评估**：{assessment}")
        if fix:
            md.append(f"\n> 🔧 **优先修复**：{fix}")

    return "\n".join(md)


def _format_student_sim(data: dict) -> str:
    """格式化学情推演输出"""
    md = []
    ctx = data.get("lesson_context", {})
    title = ctx.get("topic", "学情推演")
    md.append(f"# 👥 学情推演：{title}\n")

    profiles = data.get("student_profiles", [])
    type_icon = {"优等生": "🌟", "中等生": "📘", "学困生": "🤔"}
    for p in profiles:
        p_type = p.get("type", "")
        icon = type_icon.get(p_type, "👤")
        md.append(f"## {icon} {p_type}\n")
        md.append(f"### 思维路径\n{p.get('thinking_path', '')}\n")

        if "boredom_point" in p:
            md.append(f"### 无聊点\n{p['boredom_point']}\n")
            md.append(f"### 挑战设计\n{p.get('challenge_design', '')}\n")
            md.append(f"### 投入策略\n{p.get('engagement_strategy', '')}\n")

        if "watershed" in p:
            md.append(f"### 分水岭\n{p['watershed']}\n")
            md.append(f"### 卡点\n{p.get('struggle_point', '')}\n")
            md.append(f"### 支持策略\n{p.get('support_strategy', '')}\n")

        if "block_point" in p:
            md.append(f"### 完全卡住点\n{p['block_point']}\n")
            md.append(f"### 脚手架\n{p.get('scaffold', '')}\n")
            md.append(f"### 替代路径\n{p.get('alternative_path', '')}\n")

    dynamics = data.get("classroom_dynamics", {})
    if dynamics:
        md.append("## 🔄 课堂动态\n")
        md.append(f"**分化点**：{dynamics.get('divergence_point', '')}")
        md.append(f"**收敛策略**：{dynamics.get('convergence_strategy', '')}")
        md.append(f"**分层建议**：{dynamics.get('differentiation_tips', '')}\n")

    insight = data.get("key_insight", "")
    if insight:
        md.append(f"> 💡 **关键洞察**：{insight}")

    return "\n".join(md)


def _format_interaction_design(data: dict) -> str:
    """格式化互动设计输出"""
    md = []
    ctx = data.get("lesson_context", {})
    title = ctx.get("topic", "互动设计")
    md.append(f"# 💬 互动设计：{title}\n")

    # 破冰
    ice = data.get("icebreaker", {})
    if ice:
        md.append("## 🧊 课前破冰\n")
        md.append(f"**建议**：{ice.get('suggestion', '')}")
        md.append(f"**话术**：「{ice.get('script', '')}」\n")

    # 各环节互动
    interactions = data.get("interactions", [])
    for i, inter in enumerate(interactions, 1):
        stage = inter.get("stage", f"环节{i}")
        md.append(f"## {i}. {stage}")
        md.append(f"**目的**：{inter.get('stage_purpose', '')}\n")

        # 教师提问
        questions = inter.get("teacher_questions", [])
        if questions:
            md.append("### 提问设计\n")
            for j, q in enumerate(questions, 1):
                md.append(f"**Q{j}**：{q.get('question', '')}")
                md.append(f"  - 目的：{q.get('purpose', '')}")
                expected = q.get("expected_answers", [])
                if expected:
                    md.append(f"  - 预期回答：{' / '.join(expected)}")
                md.append(f"  - 追问策略：{q.get('follow_up', '')}")
            md.append("")

        # 小组活动
        ga = inter.get("group_activity", {})
        if ga:
            md.append("### 小组活动\n")
            md.append(f"**形式**：{ga.get('format', '')}")
            md.append(f"**指令**：「{ga.get('instruction', '')}」")
            md.append(f"**时长**：{ga.get('duration', '')}")
            md.append(f"**产出**：{ga.get('output', '')}\n")

        # 即时评估
        qc = inter.get("quick_check", {})
        if qc:
            md.append("### 即时评估\n")
            md.append(f"**方法**：{qc.get('method', '')}")
            md.append(f"**问题**：{qc.get('question', '')}")
            md.append(f"**通过标准**：{qc.get('pass_criteria', '')}\n")

        # 过渡
        ts = inter.get("transition_script", "")
        if ts:
            md.append(f"*过渡话术*：「{ts}」\n")

    tips = data.get("overall_tips", "")
    if tips:
        md.append(f"> 💡 **总体建议**：{tips}")

    return "\n".join(md)


def _format_exam(data: dict) -> str:
    """格式化智能命题输出"""
    md = []
    ctx = data.get("lesson_context", {})
    title = ctx.get("topic", "智能命题")
    meta = data.get("exam_meta", {})
    total_score = meta.get("total_score", 100)
    suggested_duration = meta.get("suggested_duration", 45)

    md.append(f"# 📝 智能命题：{title}\n")

    info_parts = []
    if ctx.get("subject"):
        info_parts.append(f"**学科**：{ctx['subject']}")
    if ctx.get("grade"):
        info_parts.append(f"**年级**：{ctx['grade']}")
    info_parts.append(f"**建议时长**：{suggested_duration}分钟")
    info_parts.append(f"**总分**：{total_score}分")
    md.append(" | ".join(info_parts) + "\n")
    md.append("---\n")

    # 按题型分组
    TYPE_ORDER = ["choice", "fill_blank", "true_false", "short_answer", "applied"]
    TYPE_NAMES = {
        "choice": "选择题",
        "fill_blank": "填空题",
        "true_false": "判断题",
        "short_answer": "简答题",
        "applied": "应用题",
    }
    DIFFICULTY_ICON = {
        "basic": "🟢",
        "advanced": "🟡",
        "challenge": "🔴",
    }

    questions = data.get("questions", [])

    for q_type in TYPE_ORDER:
        type_questions = [q for q in questions if q.get("type") == q_type]
        if not type_questions:
            continue

        type_name = TYPE_NAMES.get(q_type, q_type)
        type_score = sum(q.get("score", 0) for q in type_questions)
        per_score = type_questions[0].get("score", 0) if type_questions else 0

        md.append(f"## {type_name}（每题{per_score}分，共{type_score}分）\n")

        for i, q in enumerate(type_questions, 1):
            difficulty = q.get("difficulty", "basic")
            diff_icon = DIFFICULTY_ICON.get(difficulty, "")
            md.append(f"**{i}.** {diff_icon} {q.get('stem', '')}")

            # 选择题选项
            if q_type == "choice":
                options = q.get("options", [])
                if options:
                    labels = ["A", "B", "C", "D", "E", "F"]
                    opt_lines = []
                    for j, opt in enumerate(options):
                        opt_lines.append(f"   {labels[j]}. {opt}")
                    md.append("\n".join(opt_lines))

            # 答案
            answer = q.get("answer", "")
            if answer:
                md.append(f"\n**答案**：{answer}")

            # 评分要点（简答题/应用题）
            scoring_points = q.get("scoring_points", [])
            if scoring_points:
                md.append("\n**评分要点**：")
                for sp in scoring_points:
                    md.append(f"- {sp}")

            # 解析
            explanation = q.get("explanation", "")
            if explanation:
                md.append(f"\n**解析**：{explanation}")

            md.append("")

    # 难度分布
    summary = data.get("difficulty_summary", {})
    if summary:
        md.append("---\n")
        md.append("### 难度分布\n")
        md.append(f"- **基础题**：{summary.get('basic_score', '?')}分（{summary.get('basic_pct', '?')}）")
        md.append(f"- **提高题**：{summary.get('advanced_score', '?')}分（{summary.get('advanced_pct', '?')}）")
        md.append(f"- **挑战题**：{summary.get('challenge_score', '?')}分（{summary.get('challenge_pct', '?')}）")
        md.append("")

    # 命题建议
    tips = data.get("exam_tips", "")
    if tips:
        md.append(f"> 💡 **命题建议**：{tips}")

    return "\n".join(md)


# 格式化器注册表
FORMATTERS = {
    WorkflowMode.LESSON_PREP:        _format_lesson_plan,
    WorkflowMode.CLASSROOM_SIM:      _format_classroom_sim,
    WorkflowMode.BLIND_SPOT:         _format_blind_spot,
    WorkflowMode.STUDENT_SIM:        _format_student_sim,
    WorkflowMode.INTERACTION_DESIGN: _format_interaction_design,
    WorkflowMode.EXAM_GEN:           _format_exam,
}

# 各模式读取的中间数据字段
MODE_DATA_FIELD = {
    WorkflowMode.LESSON_PREP:        "_lesson_plan_json",
    WorkflowMode.CLASSROOM_SIM:      "_classroom_sim_json",
    WorkflowMode.BLIND_SPOT:         "_blind_spot_json",
    WorkflowMode.STUDENT_SIM:        "_student_sim_json",
    WorkflowMode.INTERACTION_DESIGN: "_interaction_json",
    WorkflowMode.EXAM_GEN:           "_exam_json",
    WorkflowMode.PPT_GEN:            "_ppt_result_json",
}


def node_format_output(state: LessonPrepState) -> dict:
    """格式化输出：根据 intent 选择不同的格式化模板"""
    intent = state.get("intent", "chat")

    # 闲聊：chat_reply 已通过 messages 流式推送文本，format_output 不再输出
    if intent == "chat":
        return {}

    # PPT生成：特殊处理（大纲预览 + 下载链接）
    if intent == "ppt_gen":
        ppt_url = state.get("ppt_download_url", "")
        ppt_outline = state.get("_ppt_outline_markdown", "")
        if ppt_url:
            download_section = f"\n\n---\n\n📥 **[点击下载 PPT 课件]({ppt_url})**\n"
            return {"final_output": ppt_outline + download_section if ppt_outline else f"✅ PPT 课件已生成！\n\n📥 **[点击下载 PPT 课件]({ppt_url})**"}
        return {"final_output": "PPT 生成失败，请重试。"}

    # 功能模式：JSON → Markdown
    data_field = MODE_DATA_FIELD.get(intent, "")
    if not data_field:
        return {"final_output": "未知功能模式，请重试。"}

    raw_json = state.get(data_field, "")
    if not raw_json:
        return {"final_output": f"内容生成失败，请重试。"}

    try:
        data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return {"final_output": str(raw_json)}

    # 降级：JSON 解析失败时直接输出原始文本
    if isinstance(data, dict) and "raw_text" in data:
        return {"final_output": data["raw_text"]}

    # 根据模式选择格式化器
    formatter = FORMATTERS.get(intent, _format_value)
    if callable(formatter):
        markdown = formatter(data)
    else:
        markdown = _format_value(data)

    # RAG 上下文来源标注（有知识库检索时追加）
    knowledge_context = state.get("_knowledge_context", "")
    if knowledge_context:
        source_count = knowledge_context.count("【片段")
        markdown += f"\n\n> 📖 参考了知识库中 {source_count} 条相关内容"

    return {"final_output": markdown}


# ============================================================
# 图构建
# ============================================================

def build_lesson_prep_graph() -> StateGraph:
    """构建多功能工作流图
    拓扑: intent_router → rag_enrich → {各功能节点} → format_output
    无知识库时 rag_enrich 直接透传，不检索。
    """
    builder = StateGraph(LessonPrepState)

    # 添加节点
    builder.add_node("intent_router", node_intent_router)
    builder.add_node("rag_enrich", node_rag_enrich)
    builder.add_node("chat_reply", node_chat_reply)
    builder.add_node("generate_lesson_plan", node_generate_lesson_plan)
    builder.add_node("simulate_classroom", node_simulate_classroom)
    builder.add_node("detect_blindspots", node_detect_blindspots)
    builder.add_node("simulate_students", node_simulate_students)
    builder.add_node("design_interactions", node_design_interactions)
    builder.add_node("generate_exam", node_generate_exam)
    builder.add_node("generate_ppt", node_generate_ppt)
    builder.add_node("format_output", node_format_output)

    # 设置入口
    builder.set_entry_point("intent_router")

    # intent_router → rag_enrich（所有请求统一经过 RAG 增强层）
    builder.add_edge("intent_router", "rag_enrich")

    # rag_enrich → 各功能节点（条件路由）
    route_map = {name: name for name in MODE_NODE_MAP.values()}
    builder.add_conditional_edges("rag_enrich", route_intent, route_map)

    # 所有功能节点 → format_output → END
    for node_name in MODE_NODE_MAP.values():
        builder.add_edge(node_name, "format_output")
    builder.add_edge("format_output", END)

    return builder
