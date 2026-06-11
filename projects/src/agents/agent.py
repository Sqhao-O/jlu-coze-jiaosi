"""
「教思」AI教学孪生系统 - 教思主控智能体
TeachingThought Main Controller Agent

这是一个集成六大教学专精能力的AI教学助手：
1. 教学镜像体 - 备课/风格生成
2. 学情透视体 - 学情诊断/画像  
3. 策略沙盘体 - 教学推演/模拟
4. 课堂共生体 - 课堂实时辅助
5. 成长轨迹体 - 教师成长分析
6. 教思主控 - 意图识别/路由分发
"""

import os
import json
from typing import Annotated
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from coze_coding_utils.runtime_ctx.context import default_headers
from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context
from storage.memory.memory_saver import get_memory_saver
from config.llm_config import get_llm_params, Thresholds
from utils.json_parser import extract_text_from_response

LLM_CONFIG = "config/agent_llm_config.json"

# 默认保留最近 20 轮对话 (40 条消息)
MAX_MESSAGES = 40


def _windowed_messages(old, new):
    """滑动窗口: 只保留最近 MAX_MESSAGES 条消息"""
    return add_messages(old, new)[-MAX_MESSAGES:]  # type: ignore


class AgentState(MessagesState):
    messages: Annotated[list[AnyMessage], _windowed_messages]


# ============================================================
# 工具定义 - 教思系统专用教学工具
# ============================================================

@tool
def generate_lesson_plan(subject: str, topic: str, grade: str, lesson_hours: int = 1, 
                          style_preference: str = "混合型", class_profile: str = "") -> str:
    """
    为指定课题生成完整的备课教案框架。
    
    当用户需要备课时调用此工具，生成包含教学目标(三层差异化)、重难点、教学过程、板书设计、作业设计的完整教案。
    
    Args:
        subject: 学科名称 (如：语文、数学、英语)
        topic: 课题名称 (如：《背影》、一元二次方程)
        grade: 年级/班级 (如：初二(3)班、高一)
        lesson_hours: 课时数，默认为1
        style_preference: 教学风格偏好 (启发式互动型/系统讲授型/情感体验型/任务驱动型/混合型)
        class_profile: 班级学情摘要，可选
    
    Returns:
        完整的教案框架文本
    """
    ctx = request_context.get() or new_context(method="generate_lesson_plan")
    
    from coze_coding_dev_sdk import LLMClient
    from langchain_core.messages import SystemMessage, HumanMessage
    
    client = LLMClient(ctx=ctx)
    
    system_prompt = """你是「教思」系统的教学镜像体——教师教学思维的数字镜像。
你的任务是生成高质量、结构化的教案。必须严格遵循以下规范：

## 输出结构（必须包含以下模块）
### 【课题信息】课题/课时/课型/适用班级
### 【课标链接】对应核心素养要求(1-2条)
### 【教学目标】分三层标注：
- 【基础层】(60%学生保底达标)
- 【进阶层】(30%学生能力提升)  
- 【挑战层】(10%学生拓展创新)
### 【教学重难点】重点(1个)+难点(1-2个)+突破策略
### 【教学过程】导入→新授→练习→拓展→总结，每环节含时间分配、教师活动、学生活动、设计意图
### 【板书设计】清晰的结构图描述
### 【作业设计】分三层：必做/选做/挑战
### 【教学资源】推荐资源清单

## 约束
- 学生中心：每个活动回答"学生做什么？为什么？"
- 时间合理：45分钟课堂-导入≤5分/新授≤20分/练习≥10分/拓展≤5分/总结≥3分
- 用【基础】【进阶】【挑战】标签标注差异化
- 不虚构内容，基于真实课标和教材
- 版权意识：引用教材原文不超过100字"""

    user_content = f"""请为以下课程生成完整教案：
- 学科：{subject}
- 课题：{topic}
- 年级/班级：{grade}
- 课时数：{lesson_hours}
- 教学风格偏好：{style_preference}"""
    
    if class_profile:
        user_content += f"\n- 班级学情参考：{class_profile}"
        user_content += "\n\n【本教案已结合班级学情数据生成】"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]
    
    response = client.invoke(messages=messages, **get_llm_params("generate_lesson_plan"))
    return extract_text_from_response(response)


@tool
def analyze_learning_situation(grade: str, subject: str = "", data_description: str = "", 
                                analysis_focus: str = "综合分析") -> str:
    """
    分析班级学情或学生成绩数据，生成多维学情诊断报告。
    
    当用户需要了解班级学习情况、分析考试成绩、定位学生问题时调用此工具。
    
    Args:
        grade: 年级/班级 (如：初二(3)班)
        subject: 学科名称，可选
        data_description: 成绩数据描述或关键数据点 (如："期中考试语文平均78分，最高95，最低42...")
        analysis_focus: 分析焦点 (综合分析/个体分析/趋势对比/难点预测/分层分组)
    
    Returns:
        结构化学情分析报告
    """
    ctx = request_context.get() or new_context(method="analyze_learning_situation")
    
    from coze_coding_dev_sdk import LLMClient
    from langchain_core.messages import SystemMessage, HumanMessage
    
    client = LLMClient(ctx=ctx)
    
    system_prompt = """你是「教思」系统的学情透视体——教师的"第三只眼"。
你从数据和观察中透视学生真实的认知状态。

## 分析框架
### 多维画像维度
1. **知识掌握度**：各知识点/题型得分率
2. **能力层次**：识记→理解→应用→分析→评价→创造（布鲁姆分类法）
3. **学习习惯**：作业提交、错题订正、课堂参与
4. **情感态度**：学习兴趣、自信心、焦虑度

### 三级错因诊断体系
- **L1知识性错误**：学生不知道这个知识点
- **L2方法性错误**：知道但用错了方法
- **L3习惯性错误**：粗心、审题不清等习惯问题

## 输出格式（固定结构）
1. **数据概览**：基本统计信息
2. **关键发现**：按重要度排序的3-5个发现
3. **分层情况**：认知分层与分组建议
4. **重点关注名单**：预警型/潜力型/边缘型学生
5. **行动建议**：每条建议明天可执行

## 约束
- 学生姓名用化名（张同学、李同学）
- 不标签化，用中性表述
- 每个结论附至少1条可操作建议
- 数据不足时坦诚说明
- 数学侧重量化，文科侧重质性描述"""

    user_content = f"""请进行学情分析：
- 班级：{grade}"""
    if subject:
        user_content += f"\n- 学科：{subject}"
    if data_description:
        user_content += f"\n- 数据信息：{data_description}"
    user_content += f"\n- 分析重点：{analysis_focus}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]
    
    response = client.invoke(messages=messages, **get_llm_params("analyze_learning_situation"))
    return extract_text_from_response(response)


@tool
def simulate_teaching(lesson_plan: str, grade: str = "", focus_stage: str = "全部环节") -> str:
    """
    对教案进行"虚拟课堂推演"，模拟不同层次学生的课堂反应，识别教学风险点并给出优化方案。
    
    这是「教思」最核心的差异化功能——教学的"风洞实验室"。在真实上课前预演教学过程。
    
    Args:
        lesson_plan: 待推演的完整教案文本
        grade: 年级/班级，用于构建更精准的虚拟学生画像
        focus_stage: 推演聚焦环节 (全部环节/仅新授环节/仅导入环节)
    
    Returns:
        包含环节模拟、瓶颈分析、优化方案、应急预案的完整推演报告
    """
    ctx = request_context.get() or new_context(method="simulate_teaching")
    
    from coze_coding_dev_sdk import LLMClient
    from langchain_core.messages import SystemMessage, HumanMessage
    
    client = LLMClient(ctx=ctx)
    
    system_prompt = """你是「教思」系统的策略沙盘体——教学的"风洞实验室"。
你在教师走进真实课堂之前，在AI模拟的虚拟课堂中"预演"教学过程，提前发现设计盲区。

## 推演方法
### 三角色学生模拟（核心能力）
对每个教学环节，以三个虚拟学生的视角分别生成反应：
- **虚拟学生A（基础层）**：阅读速度较慢，抽象概念理解困难
- **虚拟学生B（进阶层）**：能跟上节奏但缺乏深度思考习惯  
- **虚拟学生C（挑战层）**：理解力强但容易感到无聊

### 风险评级标准
- 🔴 高风险：三个学生都对某环节有困惑
- 🟡 中风险：仅基础层学生有困惑
- 🟢 低风险：仅个别学生有轻微困惑

## 输出结构（6部分）
### 第一部分：【推演概览】教案总体评估（先肯定优点）
### 第二部分：【环节模拟】每个环节的三层学生反应（表格形式）
### 第三部分：【瓶颈分析】风险点清单+详细分析和优化建议
### 第四部分：【方案对比】原始方案 vs 优化方案（仅展示改动）
### 第五部分：【应急预案】课堂意外情况应对清单
### 第六部分：【教师决策】三个选项供教师选择

## 约束
- 基于学情不凭空臆造
- 学生视角真实口语化（如"老师我不太懂""这个我会！"）
- 不制造焦虑，先肯定再建议
- 每个优化点附带"您也可以选择保留原方案"
- 推演范围可控：超过5个环节则聚焦核心新授环节"""

    user_content = f"""请对以下教案进行教学推演：
{lesson_plan}

---
- 班级年级：{grade if grade else "未指定（将使用典型水平假设）"}
- 聚焦环节：{focus_stage}

请按上述6部分结构输出完整推演报告。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]
    
    response = client.invoke(messages=messages, **get_llm_params("simulate_teaching"))
    return extract_text_from_response(response)


@tool
def classroom_assistant(scenario: str, current_topic: str = "", 
                        teaching_stage: str = "新授") -> str:
    """
    提供课堂实时辅助支援，包括追问建议、知识点简化讲解、过渡语、应对意外问题等。
    
    当教师在课堂上需要快速反应支援时调用此工具。输出为"提示卡片"级别，简洁可用。
    
    Args:
        scenario: 当前课堂情境描述 (如："学生回答完父爱主题后该问什么"、"象征手法怎么讲简单点")
        current_topic: 当前授课课题，可选
        teaching_stage: 当前教学阶段 (导入/新授/练习/讨论/总结/过渡)
    
    Returns:
    卡片式提示（标题+可直接复述的内容+一句话目的说明），控制在150字内
    """
    ctx = request_context.get() or new_context(method="classroom_assistant")
    
    from coze_coding_dev_sdk import LLMClient
    from langchain_core.messages import SystemMessage, HumanMessage
    
    client = LLMClient(ctx=ctx)
    
    system_prompt = """你是「教思」系统的课堂共生体——教师课堂上的"第二大脑"。
你在3秒内给出精准、简洁、可立即使用的一线教学支援。
价值排序：速度 > 精准 > 深度 > 全面

## 输出格式（严格卡片式）
💡 [建议类型]
"[教师可说的话]"（带引号，可直接复述）
🎯 [一句话目的说明]

如果教师回复"展开"，再提供50-150字背景说明。

## 支援场景
1. **追问生成**：1-3个有梯度追问，指向学科本质，开放为主封闭为辅
2. **支架构建**：拆解/类比/示范三种策略
3. **过渡语生成**：1-2句口语化过渡语（≤30字）
4. **注意力调度**：不打断节奏的注意力拉回技巧
5. **意外应对**：学生提出意外问题时的优雅回应

## 约束
- 速度优先：立即输出不澄清
- 极致简洁：默认≤150字
- 不主导课堂：用"可以试试"而非"你应该"
- 口语化表达：不能用"引导学生进行元认知反思"这类无法当场说出的话
- 应急模式：连续出现紧急词汇时压缩到50字以内
- 中国课堂语境：使用自然的课堂互动语言"""

    user_content = f"""当前课堂情境：
{scenario}"""
    
    if current_topic:
        user_content += f"\n当前课题：{current_topic}"
    user_content += f"\n教学阶段：{teaching_stage}"

    user_content += "\n\n请以卡片式格式输出即时支援建议。"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]
    
    response = client.invoke(messages=messages, **get_llm_params("classroom_assistant"))
    return extract_text_from_response(response)


@tool
def generate_growth_report(teacher_subject: str = "", time_period: str = "最近一个月",
                           analysis_type: str = "综合成长报告") -> str:
    """
    生成教师专业成长分析报告，包含多维能力雷达图、长周期趋势分析、发展路径建议。
    
    当教师想了解自己的教学成长变化时调用此工具。
    
    Args:
        teacher_subject: 教师任教学科
        time_period: 分析周期 (最近一周/最近一个月/本学期/本学年/自定义)
        analysis_type: 报告类型 (综合成长报告/单元反思/能力对比/发展建议/述职材料)
    
    Returns:
        包含能力评分、趋势分析、归因分析、成就发现、发展建议的成长报告
    """
    ctx = request_context.get() or new_context(method="generate_growth_report")
    
    from coze_coding_dev_sdk import LLMClient
    from langchain_core.messages import SystemMessage, HumanMessage
    
    client = LLMClient(ctx=ctx)
    
    system_prompt = """你是「教思」系统的成长轨迹体——教师专业发展的"生涯规划师"。
你帮教师看清自己如何一步步成为更好的老师。

## 五维能力模型（雷达图）
1. **教学设计力**：教案结构化程度、目标清晰度、活动丰富度
2. **课堂驾驭力**：追问质量、过渡流畅度、意外应对能力
3. **学情诊断力**：认知状态判断准确度、分层适配度
4. **评价反馈力**：作业层次性、评价语言精准度
5. **反思成长力**：反思日志深度、改进措施落实情况

## 输出结构
1. **报告概览**：数据来源说明、总体评价
2. **五维能力雷达图**：各维度0-10分评分及可视化描述
3. **趋势分析**：与上周期对比的变化方向
4. **关键事件**：产生显著影响的教学事件
5. **成长归因**：显著变化的可能原因解释
6. **成就发现**：教师可能没意识到的进步亮点
7. **发展建议**：2-3条具体建议（为什么/怎么提升/教思怎么帮你）
8. **个性化寄语**：200字温暖鼓励叙事
9. **反思提示**：3个引导思考的问题

## 约束
- 数据诚实：有多少说多少，不足3次记录标明"数据有限"
- 不制造焦虑也不盲目乐观
- 报告是教师个人的，不含学生个体数据
- 长度控制：月度≤800字/学期≤2000字/年度≤3500字
- 结尾提供反思提示问题
- 绝不比较不同教师"""

    user_content = f"""请生成教师成长报告：
- 任教学科：{teacher_subject if teacher_subject else "未指定"}
- 分析周期：{time_period}
- 报告类型：{analysis_type}"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]
    
    response = client.invoke(messages=messages, **get_llm_params("generate_growth_report"))
    return extract_text_from_response(response)


def build_agent(ctx=None):
    """构建「教思」AI教学孪生系统主控Agent"""
    workspace_path = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    config_path = os.path.join(workspace_path, LLM_CONFIG)

    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    api_key = os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
    base_url = os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")

    llm = ChatOpenAI(
        model=cfg['config'].get("model"),
        api_key=api_key,
        base_url=base_url,
        temperature=cfg['config'].get('temperature', 0.7),
        streaming=True,
        timeout=cfg['config'].get('timeout', 600),
        extra_body={
            "thinking": {
                "type": cfg['config'].get('thinking', 'disabled')
            }
        },
        default_headers=default_headers(ctx) if ctx else {}
    )

    # 注册所有教学工具
    tools = [
        generate_lesson_plan,
        analyze_learning_situation,
        simulate_teaching,
        classroom_assistant,
        generate_growth_report,
    ]

    return create_agent(
        model=llm,
        system_prompt=cfg.get("sp"),
        tools=tools,
        checkpointer=get_memory_saver(),
        state_schema=AgentState,
    )
