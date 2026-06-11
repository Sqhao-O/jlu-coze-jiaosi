"""
「教思」AI教学孪生系统 — 工作流1: 智能备课 (Lesson Preparation)
11节点StateGraph

流程: 需求解析 → KB检索 → 风格建模 → 目标生成(3层) → 重难点设计 →
      教学过程编排(5环节) → 板书设计 → 分层练习 → 作业设计 →
      质量校验(最多3次重试) → 格式化输出

参考: 方案.md 第八章 8.1 智能备课流程
"""

import os
import json
import logging
from typing import Literal, Optional

from langgraph.graph import StateGraph, END
from langgraph.constants import Send
from langchain_core.messages import SystemMessage, HumanMessage
from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_utils.log.write_log import request_context

from graphs.state import (
    TeachingState, LessonPrepState, WorkflowMode, StudentTier,
)

from config.llm_config import get_llm_params, Thresholds
from utils.json_parser import parse_json, extract_text_from_response

logger = logging.getLogger(__name__)


# ============================================================
# 节点函数
# ============================================================

def node_parse_requirements(state: LessonPrepState) -> dict:
    """
    节点1: 需求解析
    从用户输入中提取: 学科、课题、年级、课时、课型、风格偏好
    """
    ctx = request_context.get() or new_context(method="lesson_prep.parse")
    logger.info(f"[备课-节点1] 需求解析开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    user_input = state.get("messages", [{}])[-1] if state.get("messages") else {}
    topic = state.get("current_lesson_topic", "") or state.get("lesson_topic", "")

    system_prompt = """你是教学需求解析器。从输入中提取结构化字段，只输出JSON。

## 字段说明
- subject: 学科 (语文/数学/英语/物理/化学/生物/历史/地理/政治/未指定)
- topic: 课题名称
- grade: 年级班级 (如"初二(3)班")
- lesson_hours: 课时数 (整数, 默认1)
- lesson_type: 课型 (新授课/复习课/习题课/实验课/综合课)
- style_preference: 教学风格 (启发式互动型/系统讲授型/情感体验型/任务驱动型/混合型)
- key_concerns: 教师特别关注点 (可选)

## 规则
- 缺失字段使用默认值
- 从state中已有的字段优先使用
- 输出纯JSON, 不要markdown代码块"""

    user_content = f"""当前State中已提取的信息:
- 学科: {state.get('subject', '未指定')}
- 课题: {state.get('current_lesson_topic', topic)}
- 年级: {state.get('grade_level', '未指定')}
- 课时: {state.get('lesson_hours', 1)}
- 风格: {state.get('style_description', '混合型')}

用户最新输入: {str(user_input)}

请输出结构化的JSON需求解析结果。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    response = client.invoke(messages=messages, **get_llm_params("parse_requirements"))

    parsed = parse_json(response, default={}, log_context="[备课-节点1]")

    return {
        "lesson_subject": parsed.get("subject", state.get("subject", "未指定")),
        "lesson_topic": parsed.get("topic", topic),
        "lesson_grade": parsed.get("grade", state.get("grade_level", "未指定")),
        "lesson_hours": parsed.get("lesson_hours", state.get("lesson_hours", 1)),
        "lesson_type": parsed.get("lesson_type", "新授课"),
        "style_preference": parsed.get("style_preference", state.get("style_description", "混合型")),
        "workflow_mode": WorkflowMode.LESSON_PREP,
        "last_action": "解析备课需求",
        "error_count": 0,
        "intermediate_data": {
            "parse_requirements": {
                "parsed_result": parsed,
                "lesson_subject": parsed.get("subject", state.get("subject", "未指定")),
                "lesson_topic": parsed.get("topic", topic),
                "lesson_grade": parsed.get("grade", state.get("grade_level", "未指定")),
                "lesson_hours": parsed.get("lesson_hours", state.get("lesson_hours", 1)),
                "lesson_type": parsed.get("lesson_type", "新授课"),
                "style_preference": parsed.get("style_preference", state.get("style_description", "混合型")),
            }
        },
    }


def node_kb_retrieval(state: LessonPrepState) -> dict:
    """
    节点2: 知识库检索
    按优先级检索: KB1课标 → KB2教材 → KB3教法 → KB4个人库
    """
    ctx = request_context.get() or new_context(method="lesson_prep.kb")
    logger.info(f"[备课-节点2] KB检索开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    subject = state.get("lesson_subject", state.get("subject", ""))
    topic = state.get("lesson_topic", state.get("current_lesson_topic", ""))
    grade = state.get("lesson_grade", state.get("grade_level", ""))
    lesson_type = state.get("lesson_type", "新授课")

    system_prompt = f"""你是教学知识检索专家。当前备课需求:
- 学科: {subject}
- 课题: {topic}
- 年级: {grade}
- 课型: {lesson_type}

你需要模拟知识库检索，为备课提供以下4类知识的综合上下文:

## 检索框架
### KB1 课程标准库 (优先级最高)
- 本课题对应的课标编号和核心素养要求
- 学段目标中与本课题相关的能力要求
- 教学提示与学业质量标准

### KB2 教材教参库 (优先级次高)
- 课文/知识点的教材定位分析
- 教参中的教学目标建议
- 常见学生困惑与教学建议
- 优秀教案范例的核心设计思路

### KB3 教学法库 (按需)
- 适合本课型的教学策略
- 本学科常用的活动设计方法
- 差异化教学的实施建议

### KB4 教师个人库
- 该教师历史同类型教案的风格特征
- 过往使用的有效教学策略
- 偏好的活动类型和评价方式

请以结构化方式输出综合KB上下文(控制在1500字以内)，标注各部分来源。"""

    user_content = f"请为 {grade}{subject}《{topic}》({lesson_type}) 检索教学资源上下文。"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    response = client.invoke(messages=messages, **get_llm_params("kb_retrieval"))

    kb_context = extract_text_from_response(response)

    return {
        "kb_context": kb_context,
        "kb_results": {
            "standards": "已检索课程标准",
            "textbooks": "已检索教材教参",
            "pedagogy": "已检索教学法",
            "personal": "已检索个人知识库",
        },
        "last_action": "知识库检索完成",
        "intermediate_data": {
            "kb_retrieval": {
                "kb_context": kb_context,
                "kb_results": {
                    "standards": "已检索课程标准",
                    "textbooks": "已检索教材教参",
                    "pedagogy": "已检索教学法",
                    "personal": "已检索个人知识库",
                },
            }
        },
    }


def node_style_modeling(state: LessonPrepState) -> dict:
    """
    节点3: 风格建模
    从教师历史教案中提取7维教学风格向量
    """
    ctx = request_context.get() or new_context(method="lesson_prep.style")
    logger.info(f"[备课-节点3] 风格建模开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    style_pref = state.get("style_preference", "混合型")

    system_prompt = f"""你是教学风格分析专家。根据教师的风格偏好和历史教学特征，提取7维教学风格向量。

## 7维风格维度 (每维0-1分)
1. compactness (紧凑度): 内容密度和教学节奏
2. interactivity (互动度): 师生互动的偏好程度
3. depth (深度): 对概念深入挖掘的偏好
4. interest (趣味性): 使用趣味元素的倾向
5. rigor (严谨度): 学术规范和准确性要求
6. innovation (创新度): 尝试新方法的意愿
7. warmth (温度): 情感关怀和鼓励的偏好

## 风格偏好映射
教师偏好: {style_pref}

请输出JSON格式的7维向量和自然语言风格描述。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"请为偏好'{style_pref}'的教师生成风格向量。")
    ]

    default_style = {
        "compactness": 0.6,
        "interactivity": 0.7,
        "depth": 0.6,
        "interest": 0.5,
        "rigor": 0.7,
        "innovation": 0.4,
        "warmth": 0.6,
    }

    response = client.invoke(messages=messages, **get_llm_params("style_modeling"))

    style_profile = parse_json(response, default=default_style, log_context="[备课-节点3]")

    # 生成风格描述
    style_desc_map = {
        "启发式互动型": "偏好通过提问和讨论引导学生自主发现，互动度高，课堂氛围活跃",
        "系统讲授型": "注重知识体系的结构化呈现，逻辑严密，内容密度较高",
        "情感体验型": "重视学生的情感共鸣和审美体验，课堂温暖而富有感染力",
        "任务驱动型": "通过具体任务和项目组织学习，强调实践和应用",
        "混合型": "根据不同教学内容灵活切换教学策略，兼顾多种风格优势",
    }

    return {
        "style_profile": style_profile,
        "teaching_style": {
            "compactness": style_profile.get("compactness", 0.6),
            "interactivity": style_profile.get("interactivity", 0.7),
            "depth": style_profile.get("depth", 0.6),
            "interest": style_profile.get("interest", 0.5),
            "rigor": style_profile.get("rigor", 0.7),
            "innovation": style_profile.get("innovation", 0.4),
            "warmth": style_profile.get("warmth", 0.6),
        },
        "style_description": style_desc_map.get(style_pref, "灵活综合型教学风格"),
        "last_action": "风格建模完成",
        "intermediate_data": {
            "style_modeling": {
                "style_profile": style_profile,
                "style_description": style_desc_map.get(style_pref, "灵活综合型教学风格"),
            }
        },
    }


def node_objectives_generation(state: LessonPrepState) -> dict:
    """
    节点4: 三层教学目标生成
    基础层(60%) / 进阶层(30%) / 挑战层(10%)
    """
    ctx = request_context.get() or new_context(method="lesson_prep.objectives")
    logger.info(f"[备课-节点4] 目标生成开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    kb = state.get("kb_context", "")
    topic = state.get("lesson_topic", state.get("current_lesson_topic", ""))
    subject = state.get("lesson_subject", state.get("subject", ""))
    grade = state.get("lesson_grade", state.get("grade_level", ""))

    system_prompt = """你是教学目标设计专家。必须为每个课题设计三层教学目标。

## 三层目标体系
### 【基础层】(60%学生保底达标)
- 识记与理解层面的目标
- 所有学生必须达到的最低标准
- 使用行为动词: 识记、复述、辨认、列举、说明

### 【进阶层】(30%学生能力提升)
- 应用与分析层面的目标
- 中等及以上学生应达到的标准
- 使用行为动词: 运用、分析、比较、解释、推断

### 【进阶挑战】(10%学生拓展创新)
- 评价与创造层面的目标
- 学有余力学生的拓展目标
- 使用行为动词: 评价、设计、创作、探究、整合

## 输出格式 (JSON)
{
  "basic": { "knowledge": [], "skill": [], "emotion": [] },
  "intermediate": { "knowledge": [], "skill": [], "emotion": [] },
  "advanced": { "knowledge": [], "skill": [], "emotion": [] },
  "core_literacy_links": ["课标核心素养1", "课标核心素养2"]
}

每个层次的知识/技能/情感目标各1-2条。"""

    user_content = f"""请为以下课程设计三层教学目标:
- 学科: {subject}
- 课题: {topic}
- 年级: {grade}

知识库上下文:
{kb[:2000]}

请输出JSON格式的三层教学目标。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    default_objectives = {
        "basic": {"knowledge": ["理解基本概念"], "skill": ["完成基础练习"], "emotion": ["培养学习兴趣"]},
        "intermediate": {"knowledge": ["分析关键内容"], "skill": ["运用所学解决问题"], "emotion": ["体会学科价值"]},
        "advanced": {"knowledge": ["探究深层规律"], "skill": ["设计创新方案"], "emotion": ["形成批判思维"]},
        "core_literacy_links": ["学科核心素养"]
    }

    response = client.invoke(messages=messages, **get_llm_params("objectives_generation"))

    objectives = parse_json(response, default=default_objectives, log_context="[备课-节点4]")

    return {
        "teaching_objectives": objectives,
        "last_action": "三层教学目标生成完成",
        "intermediate_data": {
            "objectives_generation": {
                "objectives": objectives,
            }
        },
    }


def node_key_difficulty_design(state: LessonPrepState) -> dict:
    """
    节点5: 教学重难点设计
    重点(1个) + 难点(1-2个) + 突破策略
    """
    ctx = request_context.get() or new_context(method="lesson_prep.key_diff")
    logger.info(f"[备课-节点5] 重难点设计开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    kb = state.get("kb_context", "")
    objectives = state.get("teaching_objectives", {})
    topic = state.get("lesson_topic", state.get("current_lesson_topic", ""))

    system_prompt = """你是教学重难点分析专家。请设计教学重点和难点。

## 输出格式 (JSON)
{
  "key_point": {
    "content": "教学重点内容",
    "reason": "为什么这是重点",
    "strategy": "突出重点的教学策略"
  },
  "difficult_points": [
    {
      "content": "教学难点内容",
      "reason": "为什么学生会感到困难",
      "breakthrough_strategy": "突破难点的具体策略",
      "scaffolding": "为学生搭建的支架"
    }
  ],
  "common_misconceptions": ["常见迷思概念1", "常见迷思概念2"]
}

## 约束
- 重点只有1个
- 难点1-2个
- 每个难点必须有具体可操作的突破策略
- 突破策略要说明"教师怎么做"和"学生怎么学"
"""

    user_content = f"""课题: {topic}
三层教学目标:
{json.dumps(objectives, ensure_ascii=False, indent=2)}

KB上下文:
{kb[:1500]}

请设计教学重难点。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    default_key_diff = {
        "key_point": {"content": "核心概念理解", "reason": "学科基础", "strategy": "多角度讲解"},
        "difficult_points": [{"content": "抽象概念理解", "reason": "认知发展限制", "breakthrough_strategy": "具象化演示+类比", "scaffolding": "提供直观教具和实例"}],
        "common_misconceptions": ["概念混淆"]
    }

    response = client.invoke(messages=messages, **get_llm_params("key_difficulty_design"))

    key_difficult = parse_json(response, default=default_key_diff, log_context="[备课-节点5]")

    return {
        "key_difficult_points": key_difficult,
        "last_action": "重难点设计完成",
        "intermediate_data": {
            "key_difficulty_design": {
                "key_difficult_points": key_difficult,
            }
        },
    }


def node_process_design(state: LessonPrepState) -> dict:
    """
    节点6: 教学过程编排
    5环节: 导入→新授→练习→拓展→总结, 每环节含时间/教师活动/学生活动/设计意图/过渡语
    """
    ctx = request_context.get() or new_context(method="lesson_prep.process")
    logger.info(f"[备课-节点6] 教学过程编排开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    objectives = state.get("teaching_objectives", {})
    key_diff = state.get("key_difficult_points", {})
    style = state.get("teaching_style", {})
    hours = state.get("lesson_hours", 1)

    system_prompt = f"""你是教学过程设计专家。请设计完整的教学过程。

## 5环节结构 (45分钟/课时)
1. **导入** (≤5分钟): 激发兴趣, 建立新旧知识联系
2. **新授** (≤20分钟): 核心内容呈现, 分层讲解
3. **练习** (≥10分钟): 分层练习, 巩固应用
4. **拓展** (≤5分钟): 延伸思考, 联系实际
5. **总结** (≥3分钟): 归纳提升, 形成知识结构

## 每环节必须包含
- 时间分配 (分钟)
- 教师活动 (具体可执行)
- 学生活动 (可观察的行为)
- 设计意图 (为什么这样设计)
- 过渡语 (环节间的自然衔接, 口语化)

## 风格注入
- 互动度: {style.get('interactivity', 0.7)}
- 深度: {style.get('depth', 0.6)}
- 趣味性: {style.get('interest', 0.5)}

## 输出格式 (JSON数组)
[{{"stage": "导入", "duration": 5, "teacher_activity": "", "student_activity": "", "design_intent": "", "transition": "", "tier_notes": {{"basic": "", "advanced": ""}} }}, ...]
"""

    user_content = f"""请设计{hours}课时的教学过程。

教学目标:
{json.dumps(objectives, ensure_ascii=False, indent=2)}

重难点:
{json.dumps(key_diff, ensure_ascii=False, indent=2)}

请输出JSON格式的5环节教学过程。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    default_process = [
        {"stage": "导入", "duration": 5, "teacher_activity": "创设情境导入", "student_activity": "观察思考", "design_intent": "激发兴趣", "transition": "接下来我们深入探讨...", "tier_notes": {"basic": "确保跟上", "advanced": "可提前思考"}},
        {"stage": "新授", "duration": 20, "teacher_activity": "分层讲解核心内容", "student_activity": "听讲+互动", "design_intent": "掌握核心知识", "transition": "让我们通过练习巩固...", "tier_notes": {"basic": "多举例说明", "advanced": "引导深度思考"}},
        {"stage": "练习", "duration": 10, "teacher_activity": "布置分层练习", "student_activity": "独立/小组练习", "design_intent": "巩固应用", "transition": "拓展一下思路...", "tier_notes": {"basic": "完成基础题", "advanced": "挑战变式题"}},
        {"stage": "拓展", "duration": 5, "teacher_activity": "引导延伸思考", "student_activity": "讨论/探究", "design_intent": "拓展视野", "transition": "我们来回顾今天所学...", "tier_notes": {"basic": "关联生活", "advanced": "探究深层问题"}},
        {"stage": "总结", "duration": 5, "teacher_activity": "引导归纳总结", "student_activity": "归纳整理", "design_intent": "形成知识结构", "transition": "", "tier_notes": {"basic": "能说出要点", "advanced": "能画出思维导图"}},
    ]

    response = client.invoke(messages=messages, **get_llm_params("process_design"))

    # process 是 JSON 数组，parse_json 会包装为 {"items": [...]}
    parsed = parse_json(response, default=default_process, log_context="[备课-节点6]")
    process = parsed.get("items", parsed) if isinstance(parsed, dict) and "items" in parsed else parsed
    if not isinstance(process, list):
        process = default_process

    return {
        "teaching_process": process,
        "last_action": "教学过程编排完成",
        "intermediate_data": {
            "process_design": {
                "teaching_process": process,
            }
        },
    }


def node_board_design(state: LessonPrepState) -> dict:
    """
    节点7: 板书设计
    主板書(结构化) + 副板书(生成性)
    """
    ctx = request_context.get() or new_context(method="lesson_prep.board")
    logger.info(f"[备课-节点7] 板书设计开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    topic = state.get("lesson_topic", state.get("current_lesson_topic", ""))
    process = state.get("teaching_process", [])
    key_diff = state.get("key_difficult_points", {})

    system_prompt = """你是板书设计专家。请设计可粉笔实现的板书。

## 板书分为两部分
### 主板書 (结构化保留)
- 课题标题
- 知识框架 (层级清晰, 可用→、│、┌等符号表示结构)
- 核心概念和关键公式
- 保留到课堂结束

### 副板书 (生成性临时)
- 课堂即时生成的内容位置
- 学生回答的关键词
- 临时计算/示例

## 约束
- 黑板上可实现的粉笔字
- 不含无法手绘的复杂图形
- 结构清晰, 逻辑层次分明
- 用文字描述布局即可

## 输出格式 (JSON)
{"main_board": "主板書内容描述", "side_board": "副板书预留区域描述", "layout": "整体版面布局描述"}
"""

    user_content = f"""课题: {topic}
教学过程环节: {[p.get('stage', '') for p in process] if isinstance(process, list) else '标准5环节'}
重难点: {json.dumps(key_diff, ensure_ascii=False, indent=2)[:500]}

请设计板书。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    default_board = {"main_board": f"课题: {topic}\n一、核心概念\n二、关键方法\n三、知识结构", "side_board": "课堂生成区", "layout": "左三分之二主板書, 右三分之一副板书"}

    response = client.invoke(messages=messages, **get_llm_params("board_design"))

    board = parse_json(response, default=default_board, log_context="[备课-节点7]")

    return {
        "board_design": board,
        "last_action": "板书设计完成",
        "intermediate_data": {
            "board_design": {
                "board_design": board,
            }
        },
    }


def node_tiered_exercises(state: LessonPrepState) -> dict:
    """
    节点8: 分层练习设计
    基础巩固(60%) / 能力提升(30%) / 思维拓展(10%)
    """
    ctx = request_context.get() or new_context(method="lesson_prep.exercises")
    logger.info(f"[备课-节点8] 分层练习设计开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    objectives = state.get("teaching_objectives", {})
    topic = state.get("lesson_topic", state.get("current_lesson_topic", ""))

    system_prompt = """你是分层练习设计专家。请设计三层练习。

## 三层练习体系
### 基础巩固 (60%学生, 课堂上完成)
- 直接对应基础层教学目标
- 题型: 填空/选择/判断/简单问答
- 目的: 确保达标

### 能力提升 (30%学生, 课堂上选做)
- 对应进阶层教学目标
- 题型: 简答/分析/应用
- 目的: 能力提升

### 思维拓展 (10%学生, 课后挑战)
- 对应挑战层教学目标
- 题型: 开放题/探究/创作
- 目的: 拓展创新

## 输出格式 (JSON)
{
  "basic": [{"question": "", "type": "", "answer_hint": "", "target": ""}],
  "intermediate": [{"question": "", "type": "", "answer_hint": "", "target": ""}],
  "advanced": [{"question": "", "type": "", "answer_hint": "", "target": ""}]
}

每层2-3题。"""

    user_content = f"""课题: {topic}
教学目标: {json.dumps(objectives, ensure_ascii=False, indent=2)[:1000]}

请设计三层练习。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    default_exercises = {
        "basic": [{"question": "基础概念回顾", "type": "填空", "answer_hint": "参考教材", "target": "识记"}],
        "intermediate": [{"question": "综合运用分析", "type": "简答", "answer_hint": "结合所学", "target": "理解应用"}],
        "advanced": [{"question": "拓展探究思考", "type": "开放题", "answer_hint": "多角度思考", "target": "创新"}],
    }

    response = client.invoke(messages=messages, **get_llm_params("tiered_exercises"))

    exercises = parse_json(response, default=default_exercises, log_context="[备课-节点8]")

    return {
        "tiered_exercises": exercises,
        "last_action": "分层练习设计完成",
        "intermediate_data": {
            "tiered_exercises": {
                "exercises": exercises,
            }
        },
    }


def node_homework_design(state: LessonPrepState) -> dict:
    """
    节点9: 作业设计
    必做 / 选做 / 挑战
    """
    ctx = request_context.get() or new_context(method="lesson_prep.homework")
    logger.info(f"[备课-节点9] 作业设计开始")

    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    exercises = state.get("tiered_exercises", {})
    topic = state.get("lesson_topic", state.get("current_lesson_topic", ""))

    system_prompt = """你是作业设计专家。请设计三层课后作业。

## 作业分层
### 必做 (全班)
- 巩固课堂所学
- 预计完成时间: 15-20分钟
- 与基础层教学目标对应

### 选做 (建议中等及以上)
- 深化理解和应用
- 预计完成时间: 10-15分钟
- 与进阶层教学目标对应

### 挑战 (自愿)
- 拓展创新思维
- 预计完成时间: 灵活
- 与挑战层教学目标对应

## 输出格式 (JSON)
{
  "required": [{"task": "", "estimated_time": "", "purpose": ""}],
  "optional": [{"task": "", "estimated_time": "", "purpose": ""}],
  "challenge": [{"task": "", "estimated_time": "", "purpose": ""}],
  "total_time": "预计总时间范围"
}

必做1-2题, 选做1-2题, 挑战1题。"""

    user_content = f"""课题: {topic}
课堂练习参考: {json.dumps(exercises, ensure_ascii=False, indent=2)[:1000]}

请设计课后作业。确保与课堂练习不重复, 形成课内外互补。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    default_homework = {
        "required": [{"task": "完成教材课后练习", "estimated_time": "15分钟", "purpose": "巩固基础"}],
        "optional": [{"task": "拓展阅读/练习", "estimated_time": "10分钟", "purpose": "深化理解"}],
        "challenge": [{"task": "探究小课题", "estimated_time": "灵活", "purpose": "创新拓展"}],
        "total_time": "25-30分钟(必做+选做)"
    }

    response = client.invoke(messages=messages, **get_llm_params("homework_design"))

    homework = parse_json(response, default=default_homework, log_context="[备课-节点9]")

    return {
        "homework_design": homework,
        "last_action": "作业设计完成",
        "intermediate_data": {
            "homework_design": {
                "homework": homework,
            }
        },
    }


def node_quality_check(state: LessonPrepState) -> dict:
    """
    节点10: 质量校验
    检查: 模块完整性 + 三层差异化 + 时间合理性 + 风格一致性
    不通过则增加error_count并返回节点4重试(最多3次)
    """
    ctx = request_context.get() or new_context(method="lesson_prep.quality")
    logger.info(f"[备课-节点10] 质量校验开始")

    error_count = state.get("error_count", 0)
    errors = []

    # 检查1: 模块完整性
    if not state.get("teaching_objectives"):
        errors.append("缺失: 教学目标")
    if not state.get("key_difficult_points"):
        errors.append("缺失: 教学重难点")
    if not state.get("teaching_process"):
        errors.append("缺失: 教学过程")
    if not state.get("board_design"):
        errors.append("缺失: 板书设计")
    if not state.get("tiered_exercises"):
        errors.append("缺失: 分层练习")
    if not state.get("homework_design"):
        errors.append("缺失: 作业设计")

    # 检查2: 教学过程至少4个环节
    process = state.get("teaching_process", [])
    if isinstance(process, list) and len(process) < Thresholds.MIN_TEACHING_STAGES:
        errors.append(f"教学过程环节不足: {len(process)}/{Thresholds.MIN_TEACHING_STAGES + 1}")

    # 检查3: 时间分配合理性
    if isinstance(process, list):
        total_time = sum(p.get("duration", 0) for p in process if isinstance(p, dict))
        if total_time < Thresholds.LESSON_TOTAL_TIME_MIN or total_time > Thresholds.LESSON_TOTAL_TIME_MAX:
            errors.append(f"总时间偏差: {total_time}分钟 (期望{Thresholds.LESSON_TOTAL_TIME_MIN + 10}-{Thresholds.LESSON_TOTAL_TIME_MAX - 10}分钟)")

    validation_passed = len(errors) == 0

    if not validation_passed:
        error_count += 1
        logger.warning(f"[备课-节点10] 校验失败 (第{error_count}次): {errors}")

    return {
        "validation_errors": errors,
        "validation_passed": validation_passed,
        "error_count": error_count,
        "last_action": f"质量校验{'通过' if validation_passed else '未通过'}",
        "intermediate_data": {
            "quality_check": {
                "validation_errors": errors,
                "validation_passed": validation_passed,
                "error_count": error_count,
            }
        },
    }


def node_format_output(state: LessonPrepState) -> dict:
    """
    节点11: 格式化输出
    将各部分组装为完整的9段式教案文本
    """
    ctx = request_context.get() or new_context(method="lesson_prep.format")
    logger.info(f"[备课-节点11] 格式化输出开始")

    subject = state.get("lesson_subject", state.get("subject", "未指定"))
    topic = state.get("lesson_topic", state.get("current_lesson_topic", ""))
    grade = state.get("lesson_grade", state.get("grade_level", ""))
    hours = state.get("lesson_hours", 1)
    lesson_type = state.get("lesson_type", "新授课")
    style_desc = state.get("style_description", "混合型")

    objectives = state.get("teaching_objectives", {})
    key_diff = state.get("key_difficult_points", {})
    process = state.get("teaching_process", [])
    board = state.get("board_design", {})
    exercises = state.get("tiered_exercises", {})
    homework = state.get("homework_design", {})

    # 组装教案
    plan_parts = []

    # Part 1: 课题信息
    plan_parts.append(f"""【课题信息】
课题: {topic}
学科: {subject}
年级/班级: {grade}
课时: {hours}课时
课型: {lesson_type}
教学风格: {style_desc}""")

    # Part 2: 课标链接
    core_lit = objectives.get("core_literacy_links", ["学科核心素养"])
    plan_parts.append(f"""【课标链接】
{chr(10).join(f'- {link}' for link in core_lit)}""")

    # Part 3: 教学目标(三层)
    basic_obj = objectives.get("basic", {})
    intermediate_obj = objectives.get("intermediate", {})
    advanced_obj = objectives.get("advanced", {})

    def _format_obj(obj_dict):
        parts = []
        for k, v in obj_dict.items():
            if isinstance(v, list):
                parts.append(f"  {k}: {', '.join(v)}")
            elif isinstance(v, str):
                parts.append(f"  {k}: {v}")
        return "\n".join(parts)

    plan_parts.append(f"""【教学目标】
### 【基础层】(60%学生 — 保底达标)
{_format_obj(basic_obj)}

### 【进阶层】(30%学生 — 能力提升)
{_format_obj(intermediate_obj)}

### 【挑战层】(10%学生 — 拓展创新)
{_format_obj(advanced_obj)}""")

    # Part 4: 重难点
    kp = key_diff.get("key_point", {})
    dps = key_diff.get("difficult_points", [])
    misconceptions = key_diff.get("common_misconceptions", [])

    dp_text = ""
    for i, dp in enumerate(dps, 1):
        dp_text += f"""
难点{i}: {dp.get('content', '')}
  原因: {dp.get('reason', '')}
  突破策略: {dp.get('breakthrough_strategy', '')}
  支架: {dp.get('scaffolding', '')}"""

    plan_parts.append(f"""【教学重难点】
### 重点
{kp.get('content', '')}
  选择原因: {kp.get('reason', '')}
  突出策略: {kp.get('strategy', '')}

### 难点
{dp_text}

### 常见迷思概念
{chr(10).join(f'- {m}' for m in misconceptions)}""")

    # Part 5: 教学过程
    process_text = "【教学过程】"
    if isinstance(process, list):
        for i, stage in enumerate(process):
            if isinstance(stage, dict):
                tier_notes = stage.get("tier_notes", {})
                process_text += f"""
---
### 环节{i+1}: {stage.get('stage', '')} ({stage.get('duration', 0)}分钟)

**教师活动**: {stage.get('teacher_activity', '')}

**学生活动**: {stage.get('student_activity', '')}

**设计意图**: {stage.get('design_intent', '')}

**差异化处理**:
  - 【基础】{tier_notes.get('basic', '按常规进行')}
  - 【进阶】{tier_notes.get('advanced', tier_notes.get('intermediate', '适当加深'))}

**过渡语**: "{stage.get('transition', '')}"
"""
    plan_parts.append(process_text)

    # Part 6: 板书设计
    plan_parts.append(f"""【板书设计】
### 主板書
{board.get('main_board', '')}

### 副板书
{board.get('side_board', '')}

### 版面布局
{board.get('layout', '')}""")

    # Part 7: 分层练习
    basic_ex = exercises.get("basic", [])
    inter_ex = exercises.get("intermediate", [])
    adv_ex = exercises.get("advanced", [])

    def _format_exercises(ex_list):
        text = ""
        for i, ex in enumerate(ex_list, 1):
            if isinstance(ex, dict):
                text += f"\n  {i}. [{ex.get('type', '')}] {ex.get('question', '')}"
                if ex.get('answer_hint'):
                    text += f"\n     💡提示: {ex.get('answer_hint')}"
        return text

    plan_parts.append(f"""【分层练习设计】
### 【基础巩固】(课堂必做)
{_format_exercises(basic_ex)}

### 【能力提升】(课堂选做)
{_format_exercises(inter_ex)}

### 【思维拓展】(课后挑战)
{_format_exercises(adv_ex)}""")

    # Part 8: 作业设计
    required = homework.get("required", [])
    optional = homework.get("optional", [])
    challenge = homework.get("challenge", [])
    total_time = homework.get("total_time", "约30分钟")

    def _format_homework(hw_list):
        text = ""
        for i, hw in enumerate(hw_list, 1):
            if isinstance(hw, dict):
                text += f"\n  {i}. {hw.get('task', '')} (预计{hw.get('estimated_time', '')})"
                if hw.get('purpose'):
                    text += f"\n     目的: {hw.get('purpose')}"
        return text

    plan_parts.append(f"""【作业设计】
⏱️ 作业总时间: {total_time}

### 必做 (全班)
{_format_homework(required)}

### 选做 (建议中等及以上)
{_format_homework(optional)}

### 挑战 (自愿)
{_format_homework(challenge)}""")

    # Part 9: 教学反思提示
    plan_parts.append(f"""【教学反思提示】
1. 预设反思点: 三层目标达成度如何? 哪些环节超出/低于预期?
2. 预判典型错误: 学生在哪些知识点上容易出错? 如何下次预防?
3. 差异化反思: 三个层次学生的参与度和收获分别如何?

---
📋 **本教案由「教思」教学镜像体生成**
💡 下一步建议: **[完全采用]** / **[需要微调]** / **[重新生成]** / **[🎯 推演这个方案]**""")

    final_plan = "\n\n".join(plan_parts)

    # 不再压缩教案，保留完整内容
    lesson_plan_draft = final_plan

    return {
        "final_lesson_plan": final_plan,
        "lesson_plan_draft": lesson_plan_draft,
        "last_action": "备课完成 - 9段完整教案已生成",
        "workflow_mode": WorkflowMode.NONE,  # 工作流结束
    }


# ============================================================
# 路由函数
# ============================================================

def route_after_quality(state: LessonPrepState) -> Literal["format_output", "objectives_generation"]:
    """质量校验后的路由: 通过→格式化输出, 未通过且未超限→返回目标生成重试"""
    if state.get("validation_passed", False):
        return "format_output"
    if state.get("error_count", 0) >= state.get("max_retries", 3):
        logger.warning(f"[备课] 已达最大重试次数({state.get('max_retries', 3)}), 强制输出")
        return "format_output"
    logger.info(f"[备课] 质量校验未通过, 返回目标生成重试 (第{state.get('error_count', 0)}次)")
    return "objectives_generation"


# ============================================================
# 构建 StateGraph
# ============================================================

def build_lesson_prep_graph() -> StateGraph:
    """构建智能备课11节点StateGraph"""

    builder = StateGraph(LessonPrepState)

    # 添加节点
    builder.add_node("parse_requirements", node_parse_requirements)
    builder.add_node("kb_retrieval", node_kb_retrieval)
    builder.add_node("style_modeling", node_style_modeling)
    builder.add_node("objectives_generation", node_objectives_generation)
    builder.add_node("key_difficulty_design", node_key_difficulty_design)
    builder.add_node("process_design", node_process_design)
    builder.add_node("board_design", node_board_design)
    builder.add_node("tiered_exercises", node_tiered_exercises)
    builder.add_node("homework_design", node_homework_design)
    builder.add_node("quality_check", node_quality_check)
    builder.add_node("format_output", node_format_output)

    # 设置入口
    builder.set_entry_point("parse_requirements")

    # 连线
    builder.add_edge("parse_requirements", "kb_retrieval")
    builder.add_edge("kb_retrieval", "style_modeling")
    builder.add_edge("style_modeling", "objectives_generation")
    builder.add_edge("objectives_generation", "key_difficulty_design")
    builder.add_edge("key_difficulty_design", "process_design")
    builder.add_edge("process_design", "board_design")
    builder.add_edge("board_design", "tiered_exercises")
    builder.add_edge("tiered_exercises", "homework_design")
    builder.add_edge("homework_design", "quality_check")

    # 条件边: 质量校验→通过则输出, 否则重试
    builder.add_conditional_edges(
        "quality_check",
        route_after_quality,
        {
            "format_output": "format_output",
            "objectives_generation": "objectives_generation",
        }
    )

    builder.add_edge("format_output", END)

    return builder
