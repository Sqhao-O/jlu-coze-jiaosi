import argparse
import asyncio
import json
import threading
import traceback
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Iterable, AsyncIterable, AsyncGenerator, Optional
import cozeloop
import uvicorn
import time
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from coze_coding_dev_sdk import LLMClient
from coze_coding_utils.runtime_ctx.context import new_context, Context
from coze_coding_utils.helper import graph_helper
from coze_coding_utils.log.node_log import LOG_FILE
from coze_coding_utils.log.write_log import setup_logging, request_context
from coze_coding_utils.log.config import LOG_LEVEL
from coze_coding_utils.error.classifier import ErrorClassifier, classify_error
from coze_coding_utils.helper.stream_runner import AgentStreamRunner, WorkflowStreamRunner,agent_stream_handler,workflow_stream_handler, RunOpt
from storage.database.db import get_session, get_engine
from storage.memory.memory_saver import get_memory_saver
from storage.database.shared.model import Base
from coze_coding_utils.async_tasks import (
    AsyncTaskRuntime,
    AsyncTaskStorageError,
    extract_biz_context,
    parse_deadline_sec,
)
from coze_coding_utils.async_tasks import config as async_task_config
from coze_coding_utils.async_tasks.headers import HEADER_X_RUN_ID as _ASYNC_HEADER_X_RUN_ID
from coze_coding_utils.runtime_ctx.context import new_context as _new_async_ctx
from sqlalchemy import event

setup_logging(
    log_file=LOG_FILE,
    max_bytes=100 * 1024 * 1024, # 100MB
    backup_count=5,
    log_level=LOG_LEVEL,
    use_json_format=True,
    console_output=True
)

logger = logging.getLogger(__name__)
from coze_coding_utils.helper.agent_helper import to_stream_input
from coze_coding_utils.openai.handler import OpenAIChatHandler
from coze_coding_utils.log.parser import LangGraphParser
from coze_coding_utils.log.err_trace import extract_core_stack
from coze_coding_utils.log.loop_trace import init_run_config, init_agent_config


# 超时配置常量
TIMEOUT_SECONDS = 900  # 15分钟

# === JSON → Markdown 格式化工具 ===

KEY_ZH_MAP = {
    # 课题基本信息
    "subject": "学科", "topic": "课题", "grade": "年级", "lesson_hours": "课时",
    "lesson_type": "课型", "style_preference": "风格偏好", "key_concerns": "关注要点",
    # 教学重难点
    "key_point": "教学重点", "difficult_points": "教学难点", "common_misconceptions": "常见误区",
    "teaching_objectives": "教学目标", "teaching_style": "教学风格", "style_profile": "风格画像",
    # 教学过程
    "teaching_process": "教学过程", "board_design": "板书设计", "stage": "教学环节",
    "duration": "时长", "teacher_activity": "教师活动", "student_activity": "学生活动",
    "design_intent": "设计意图", "transition": "过渡语", "tier_notes": "分层要求",
    # 教学目标分层
    "basic": "基础层", "intermediate": "进阶层", "advanced": "拓展层",
    "knowledge": "知识目标", "skill": "能力目标", "emotion": "情感目标",
    # 重难点详情
    "content": "内容", "reason": "原因", "strategy": "策略", "breakthrough_strategy": "突破策略",
    "scaffolding": "脚手架", "main_board": "主板书", "side_board": "副板书", "layout": "布局",
    "core_literacy_links": "核心素养链接",
    # 分层练习
    "tiered_exercises": "分层练习", "exercises": "练习题",
    "question": "题目", "type": "题型", "answer_hint": "参考答案",
    "target": "训练目标",
    # 作业设计
    "homework": "作业设计", "required": "必做作业", "optional": "选做作业",
    "challenge": "挑战作业", "task": "任务", "estimated_time": "预计时间",
    "purpose": "目的", "total_time": "总时长",
    # 教学风格
    "7维教学风格向量": "7维教学风格向量", "风格描述": "风格描述",
    "compactness": "紧凑度", "interactivity": "互动度",
    "depth": "知识深度", "interest": "趣味性", "rigor": "严谨度",
    "innovation": "创新度", "warmth": "温暖度",
    # 成长分析
    "name": "姓名", "description": "描述", "title": "标题",
    "why_matters": "重要性", "evidence": "证据",
    "steps": "步骤", "materials": "材料", "evaluation": "评价",
    # 教学推演
    "lesson_overview": "教案概述", "stages": "教学环节", "stage_id": "环节编号",
    "stage_name": "环节名称", "core_content": "核心内容", "teacher_action": "教师行为",
    "expected_student_response": "预期学生反应", "potential_difficulty": "潜在困难",
    "duration_min": "时长(分钟)", "total_stages": "总环节数", "key_dependencies": "关键依赖",
    "student_a": "学生A(基础层)", "student_b": "学生B(进阶层)", "student_c": "学生C(挑战层)",
    "tier": "层级", "cognitive_profile": "认知特征", "personality": "性格特征",
    "learning_style": "学习风格", "current_state": "当前状态",
    "typical_response_pattern": "典型反应模式", "class_atmosphere": "班级氛围",
    "virtual_students": "虚拟学生", "attention": "注意力",
    "understanding_level": "理解程度", "inner_monologue": "内心独白",
    "external_behavior": "外在表现", "if_called_answer": "被点名回答",
    "confusion_points": "困惑点", "engagement_score": "参与度",
    "student_simulations": "学生模拟", "student_tier": "学生层级",
    "student_key": "学生标识", "result": "结果",
    "aggregated_results": "聚合结果", "bottlenecks": "瓶颈分析",
    "bottleneck_list": "瓶颈列表", "risk_signals": "风险信号",
    "affected_tiers": "受影响层级", "root_cause": "根本原因",
    "severity": "严重程度", "overall_assessment": "整体评估",
    "risk_assessment": "风险评估", "overall_risk": "整体风险",
    "items": "项目", "summary": "总结", "risk_level": "风险等级",
    "stage": "环节", "contingency_plans": "应急预案", "plans": "方案",
    "for_stage": "针对环节", "scenario": "场景",
    "plan_a": "方案A", "plan_b": "方案B", "signal_to_trigger": "触发信号",
    "optimization_suggestions": "优化建议", "changes": "改动",
    "original": "原始设计", "optimized": "优化后",
    "expected_effect": "预期效果", "keep_original_option": "保留原始选项",
    "comparison_report": "对比报告", "final_simulation_report": "最终推演报告",
    "simulation_result": "推演结果", "bottleneck_count": "瓶颈数量",
    "bottleneck_summary": "瓶颈摘要",
    "student_a_feedback": "学生A反馈", "student_b_feedback": "学生B反馈",
    "student_c_feedback": "学生C反馈", "optimized_plan_snippet": "优化方案摘要",
    "last_action": "最后操作", "workflow_mode": "工作流模式",
    "source_lesson_plan": "源教案", "lesson_plan_draft": "教案草稿",
    "class_profile": "班级画像", "grade_level": "年级",
    # 成长分析
    "period": "分析周期", "analysis_type": "分析类型", "data_sources": "数据来源",
    "lesson_plans": "备课记录", "simulations": "推演记录", "classroom_events": "课堂事件",
    "reflection_logs": "反思日志", "growth_snapshots": "历史快照",
    "data_quality": "数据质量", "collected_at": "采集时间",
    "data_sufficiency": "数据充足度", "estimated_records": "估计记录数",
    "collected_data": "采集数据", "cleaned_data": "清洗后数据",
    "cleaned_at": "清洗时间", "cleaning_notes": "清洗说明",
    "score": "评分", "level": "等级", "strengths": "优势",
    "weaknesses": "待改进", "growth_from_last": "较上期变化",
    "recommendation": "建议", "dimension_design": "教学设计力",
    "dimension_classroom": "课堂驾驭力", "dimension_diagnosis": "学情诊断力",
    "dimension_feedback": "评价反馈力", "dimension_reflection": "反思成长力",
    "dimensions": "各维度", "average_score": "平均分",
    "overall_level": "综合等级", "strongest_dimension": "最强维度",
    "weakest_dimension": "最弱维度", "score_range": "分数区间",
    "radar_data": "雷达图数据", "dimension_trends": "维度趋势",
    "improving_dimensions": "上升维度", "stable_dimensions": "稳定维度",
    "declining_dimensions": "下降维度", "overall_trend": "整体趋势",
    "trend_analysis": "趋势分析", "attribution": "归因分析",
    "details": "详情", "direction": "方向", "magnitude": "幅度",
    "possible_reasons": "可能原因", "confidence": "置信度",
    "suggestion": "建议", "overall_note": "总体说明",
    "achievements": "成就发现", "discoveries": "发现",
    "celebration_message": "庆祝语", "suggestions": "发展建议",
    "focus": "关注维度", "priority": "优先级", "why": "重要性",
    "how": "提升方法", "jiao_si_support": "教思支持",
    "next_step": "下一步", "personalized_narrative": "个性化寄语",
    "final_growth_report": "最终成长报告", "analysis_period": "分析周期",
    "dimension": "维度", "change": "变化", "note": "备注",
    "growth": "增长", "strength": "优势", "radar": "雷达图",
    "trend": "趋势", "source": "来源", "data": "数据",
    "lesson_subject": "学科", "student_profile": "学生画像",
    "academic_performance": "学业表现", "learning_behavior": "学习行为",
    "participation": "课堂参与", "homework_quality": "作业质量",
    "exam_scores": "考试成绩", "progress_trend": "进步趋势",
    "attention_issues": "注意力问题", "knowledge_gaps": "知识漏洞",
    "strength_areas": "优势领域", "weakness_areas": "薄弱领域",
    "personalized_strategy": "个性化策略", "intervention_plan": "干预方案",
    "expected_outcome": "预期效果", "monitoring_metrics": "监控指标",
    "student_name": "学生姓名", "class_name": "班级",
    "report_period": "报告周期", "generated_at": "生成时间",
    "key_findings": "关键发现", "action_items": "行动项",
    "follow_up": "后续跟进", "parent_communication": "家长沟通建议",
    "analysis_summary": "分析摘要", "detailed_analysis": "详细分析",
    "visualization_data": "可视化数据", "chart_type": "图表类型",
    "labels": "标签", "values": "数值", "unit": "单位",
    "comparison": "对比", "baseline": "基线", "current": "当前",
    "target": "目标", "gap": "差距", "progress": "进度",
    "status": "状态", "timestamp": "时间戳", "version": "版本",
    "author": "作者", "reviewer": "审核人", "approved": "已审核",
    "comments": "备注", "tags": "标签", "category": "分类",
    "created_at": "创建时间", "updated_at": "更新时间",
    "input": "输入", "output": "输出", "config": "配置",
    "metadata": "元数据", "error": "错误", "warning": "警告",
    "info": "信息", "debug": "调试", "critical": "严重",
    "success": "成功", "failed": "失败", "pending": "待处理",
    "running": "运行中", "completed": "已完成", "cancelled": "已取消",
    "start_time": "开始时间", "end_time": "结束时间", "duration": "耗时",
    "node": "节点", "edge": "边", "graph": "图",
    "state": "状态", "action": "操作", "event": "事件",
    "message": "消息", "response": "响应", "request": "请求",
    "session": "会话", "user": "用户", "role": "角色",
    "content": "内容", "text": "文本", "html": "HTML",
    "url": "链接", "file": "文件", "path": "路径",
    "size": "大小", "format": "格式", "encoding": "编码",
}

def _translate_key(key: str) -> str:
    return KEY_ZH_MAP.get(key, key)

def _value_to_md(val, depth: int = 0) -> str:
    """递归将 Python 对象转为 Markdown 文本"""
    if isinstance(val, dict):
        lines = []
        for k, v in val.items():
            zh_key = _translate_key(k)
            if isinstance(v, (dict, list)):
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    # 列表中的对象 → 子标题+内容
                    lines.append(f"\n{'#' * (depth + 2)} {zh_key}\n")
                    for idx, item in enumerate(v, 1):
                        lines.append(f"\n{'#' * (depth + 3)} 第 {idx} 项\n")
                        lines.append(_value_to_md(item, depth + 3))
                else:
                    lines.append(f"\n{'#' * (depth + 2)} {zh_key}\n")
                    lines.append(_value_to_md(v, depth + 2))
            else:
                lines.append(f"**{zh_key}**：{v}\n")
        return "\n".join(lines)
    elif isinstance(val, list):
        lines = []
        for idx, item in enumerate(val, 1):
            if isinstance(item, dict):
                lines.append(f"\n**{idx}.** {_value_to_md(item, depth + 1)}\n")
            else:
                lines.append(f"- {item}\n")
        return "\n".join(lines)
    else:
        return str(val)

def _extract_json_strings(text: str) -> list:
    """从混合文本中提取所有 JSON 字符串（对象或数组）"""
    results = []
    i = 0
    while i < len(text):
        if text[i] in ('{', '['):
            start = i
            depth = 0
            in_str = False
            escape = False
            j = i
            while j < len(text):
                ch = text[j]
                if escape:
                    escape = False
                elif ch == '\\' and in_str:
                    escape = True
                elif ch == '"' and not escape:
                    in_str = not in_str
                elif not in_str:
                    if ch in ('{', '['):
                        depth += 1
                    elif ch in ('}', ']'):
                        depth -= 1
                        if depth == 0:
                            candidate = text[start:j + 1]
                            try:
                                obj = json.loads(candidate)
                                results.append((start, j + 1, obj))
                            except (json.JSONDecodeError, ValueError):
                                pass
                            i = j + 1
                            break
                j += 1
            else:
                i += 1
        else:
            i += 1
    return results

def format_teaching_content(content: str) -> str:
    """将混合格式内容（含JSON和文本）转为结构化 Markdown"""
    # 检测内容中是否包含 JSON
    json_parts = _extract_json_strings(content)
    if not json_parts:
        return content

    # 替换每个 JSON 片段为 Markdown
    result_parts = []
    last_end = 0
    has_meaningful_json = False

    for start, end, obj in json_parts:
        # 保留 JSON 前的非 JSON 文本
        if start > last_end:
            between = content[last_end:start].strip()
            if between:
                result_parts.append(between)

        # 只转换有实质内容的 JSON（跳过小型配置类 JSON）
        obj_str = json.dumps(obj, ensure_ascii=False)
        if len(obj_str) > 50:  # 有实质内容
            has_meaningful_json = True
            md = _value_to_md(obj, depth=0)
            result_parts.append(md)
        # 小 JSON 跳过（如 {"last_action": "xxx"}）

        last_end = end

    # 保留最后的非 JSON 文本
    if last_end < len(content):
        remaining = content[last_end:].strip()
        if remaining:
            result_parts.append(remaining)

    if not has_meaningful_json:
        return content

    # 组合结果
    full_md = "\n\n---\n\n".join(result_parts)

    # 添加文档标题
    return f"# 📚 教学方案\n\n{full_md}"

class GraphService:
    def __init__(self):
        # 用于跟踪正在运行的任务（使用asyncio.Task）
        self.running_tasks: Dict[str, asyncio.Task] = {}
        # 错误分类器
        self.error_classifier = ErrorClassifier()
        # stream runner
        self._agent_stream_runner = AgentStreamRunner()
        self._workflow_stream_runner = WorkflowStreamRunner()
        self._graph = None
        self._graph_lock = threading.Lock()

    def set_graph(self, graph) -> None:
        """Inject the compiled graph used by sync endpoints. Called once from
        lifespan with a no-checkpointer build, so /run /stream_run /node_run
        never hit the checkpoint DB."""
        self._graph = graph

    def _get_graph(self, ctx=Context):
        if self._graph is not None:
            return self._graph
        with self._graph_lock:
            if self._graph is not None:
                return self._graph
            if graph_helper.is_agent_proj():
                self._graph = graph_helper.get_agent_instance("agents.agent", ctx)
            else:
                self._graph = graph_helper.get_graph_instance("graphs.graph")
            return self._graph

    @staticmethod
    def _sse_event(data: Any, event_id: Any = None) -> str:
        id_line = f"id: {event_id}\n" if event_id else ""
        return f"{id_line}event: message\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"

    def _get_stream_runner(self):
        if graph_helper.is_agent_proj():
            return self._agent_stream_runner
        else:
            return self._workflow_stream_runner

    # 流式运行（原始迭代器）：本地调用使用
    def stream(self, payload: Dict[str, Any], run_config: RunnableConfig, ctx=Context) -> Iterable[Any]:
        graph = self._get_graph(ctx)
        stream_runner = self._get_stream_runner()
        for chunk in stream_runner.stream(payload, graph, run_config, ctx):
            yield chunk

    @staticmethod
    def _is_json_like_string(value: Any) -> bool:
        """Check if a value looks like a JSON string."""
        if not isinstance(value, str):
            return False
        trimmed = value.strip()
        return (trimmed.startswith("{") and trimmed.endswith("}")) or \
               (trimmed.startswith("[") and trimmed.endswith("]"))

    @staticmethod
    def _format_json_value(value: Any) -> str:
        """Try to parse a JSON string and return formatted Markdown."""
        if not isinstance(value, str):
            return str(value) if value is not None else ""
        trimmed = value.strip()
        if not ((trimmed.startswith("{") and trimmed.endswith("}")) or
                (trimmed.startswith("[") and trimmed.endswith("]"))):
            return value
        try:
            import json
            data = json.loads(trimmed)
            return GraphService._json_to_markdown(data)
        except Exception:
            return value

    @staticmethod
    def _json_to_markdown(data: Any, level: int = 0) -> str:
        """Recursively convert JSON data to Markdown."""
        if data is None:
            return ""
        if isinstance(data, str):
            return data
        if isinstance(data, (int, float, bool)):
            return str(data)

        indent = "  " * level
        lines = []

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # Object in list: render as sub-section
                    item_md = GraphService._json_to_markdown(item, level + 1)
                    lines.append(f"{indent}- {item_md.strip()}")
                else:
                    lines.append(f"{indent}- {GraphService._json_to_markdown(item, level + 1)}")
            return "\n".join(lines)

        if isinstance(data, dict):
            for key, val in data.items():
                display_key = GraphService._translate_key(key)
                if isinstance(val, dict):
                    lines.append(f"{indent}**{display_key}**\n")
                    lines.append(GraphService._json_to_markdown(val, level + 1))
                elif isinstance(val, list):
                    lines.append(f"{indent}**{display_key}**\n")
                    for item in val:
                        if isinstance(item, dict):
                            item_md = GraphService._json_to_markdown(item, level + 1)
                            lines.append(f"{indent}- {item_md.strip()}")
                        else:
                            lines.append(f"{indent}- {GraphService._json_to_markdown(item, level + 1)}")
                elif isinstance(val, str) and len(val) > 100:
                    lines.append(f"{indent}**{display_key}**：{val}\n")
                else:
                    lines.append(f"{indent}**{display_key}**：{val}\n")
            return "\n".join(lines)

        return str(data)

    @staticmethod
    def _translate_key(key: str) -> str:
        """Translate English keys to Chinese."""
        mapping = {
            "subject": "学科",
            "topic": "课题",
            "grade": "年级",
            "lesson_hours": "课时",
            "lesson_type": "课型",
            "style_preference": "风格偏好",
            "key_concerns": "关注要点",
            "compactness": "紧凑度",
            "interactivity": "互动度",
            "depth": "知识深度",
            "interest": "趣味性",
            "rigor": "严谨性",
            "innovation": "创新性",
            "warmth": "亲和度",
            "basic": "基础层",
            "intermediate": "进阶层",
            "advanced": "拓展层",
            "knowledge": "知识目标",
            "skill": "能力目标",
            "emotion": "素养目标",
            "key_point": "教学重点",
            "difficult_points": "教学难点",
            "content": "内容",
            "reason": "理由",
            "strategy": "策略",
            "breakthrough_strategy": "突破策略",
            "scaffolding": "脚手架",
            "teacher_activity": "教师活动",
            "student_activity": "学生活动",
            "design_intent": "设计意图",
            "transition": "过渡语",
            "tier_notes": "分层说明",
            "stage": "环节",
            "duration": "时长(分钟)",
            "core_literacy_links": "核心素养关联",
            "common_misconceptions": "常见误区",
            "core_literacy": "核心素养",
            "teaching_objectives": "教学目标",
            "teaching_process": "教学过程",
            "reflection": "教学反思",
            "teaching_resources": "教学资源",
            "assessment": "教学评价",
        }
        return mapping.get(key, key)

    async def _format_output(self, result: Dict[str, Any], ctx) -> Dict[str, Any]:
        """Format output to beautiful Markdown using an LLM agent."""
        if not isinstance(result, dict):
            return result

        # Find the output content field - look for any long string value
        content = None
        content_key = None
        for key in ["output", "result", "content", "response", "answer", "data", "message"]:
            if key in result and isinstance(result[key], str) and len(result[key]) > 50:
                content = result[key]
                content_key = key
                break

        # Fallback: find any long string value
        if content is None:
            for key, val in result.items():
                if isinstance(val, str) and len(val) > 50:
                    content = val
                    content_key = key
                    break

        if content is None:
            return result

        try:
            client = LLMClient(ctx=ctx)
            system_prompt = """你是一个专业的教学文档排版助手。你的任务是将输入的内容（可能包含JSON、混合格式文本等）转换为结构清晰、排版美观的纯Markdown格式文档。

要求：
1. 将所有JSON数据转换为Markdown格式：对象用标题和列表，数组用列表，键名翻译为中文
2. 已有的Markdown内容保持并优化排版
3. 使用Markdown标题层级（#、##、###）组织文档结构
4. 教学环节使用表格呈现（环节、时长、教师活动、学生活动、设计意图）
5. 知识点、重难点使用列表和引用块呈现
6. 在文档开头添加一个简短的总体概述
7. 输出纯Markdown文本，不要添加任何解释性文字或代码块包裹"""

            user_prompt = f"请将以下教学数据转换为美观的Markdown文档：\n\n{content}"

            from langchain_core.messages import SystemMessage, HumanMessage
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            llm_response = await asyncio.wait_for(
                asyncio.to_thread(client.invoke, messages=messages, model="doubao-seed-2-0-lite-260215", temperature=0.3, max_completion_tokens=8000),
                timeout=60.0
            )

            if llm_response and hasattr(llm_response, 'content') and llm_response.content:
                result_copy = dict(result)
                result_copy[content_key] = llm_response.content.strip()
                result_copy["_formatted"] = True
                return result_copy

            return result

        except Exception as e:
            logger.warning(f"Output formatting failed: {e}")
            return result

    # 同步运行：本地/HTTP 通用
    async def run(self, payload: Dict[str, Any], ctx=None) -> Dict[str, Any]:
        if ctx is None:
            ctx = new_context("run")

        run_id = ctx.run_id
        logger.info(f"Starting run with run_id: {run_id}")

        try:
            graph = self._get_graph(ctx)
            # custom tracer
            run_config = init_run_config(graph, ctx)

            # 直接调用，LangGraph会在当前任务上下文中执行
            # 如果当前任务被取消，LangGraph的执行也会被取消
            result = await graph.ainvoke(payload, config=run_config, context=ctx)

            # Format JSON output to Markdown (disabled - handled in openai_chat_completions instead)
            # result = await self._format_output(result, ctx)
            return result

        except asyncio.CancelledError:
            logger.info(f"Run {run_id} was cancelled")
            return {"status": "cancelled", "run_id": run_id, "message": "Execution was cancelled"}
        except Exception as e:
            # 使用错误分类器分类错误
            err = self.error_classifier.classify(e, {"node_name": "run", "run_id": run_id})
            # 记录详细的错误信息和堆栈跟踪
            logger.error(
                f"Error in GraphService.run: [{err.code}] {err.message}\n"
                f"Category: {err.category.name}\n"
                f"Traceback:\n{extract_core_stack()}"
            )
            # 保留原始异常堆栈，便于上层返回真正的报错位置
            raise
        finally:
            # 清理任务记录
            self.running_tasks.pop(run_id, None)

    # 流式运行（SSE 格式化）：HTTP 路由使用
    async def stream_sse(self, payload: Dict[str, Any], ctx=None, run_opt: Optional[RunOpt] = None) -> AsyncGenerator[str, None]:
        if ctx is None:
            ctx = new_context(method="stream_sse")
        if run_opt is None:
            run_opt = RunOpt()

        run_id = ctx.run_id
        logger.info(f"Starting stream with run_id: {run_id}")
        graph = self._get_graph(ctx)
        if graph_helper.is_agent_proj():
            run_config = init_agent_config(graph, ctx)
        else:
            run_config = init_run_config(graph, ctx)  # vibeflow

        is_workflow = not graph_helper.is_agent_proj()

        try:
            async for chunk in self.astream(payload, graph, run_config=run_config, ctx=ctx, run_opt=run_opt):
                if is_workflow and isinstance(chunk, tuple):
                    event_id, data = chunk
                    yield self._sse_event(data, event_id)
                else:
                    yield self._sse_event(chunk)
        finally:
            # 清理任务记录
            self.running_tasks.pop(run_id, None)
            cozeloop.flush()

    # 取消执行 - 使用asyncio的标准方式
    def cancel_run(self, run_id: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
        """
        取消指定run_id的执行

        使用asyncio.Task.cancel()来取消任务,这是标准的Python异步取消机制。
        LangGraph会在节点之间检查CancelledError,实现优雅的取消。
        """
        logger.info(f"Attempting to cancel run_id: {run_id}")

        # 查找对应的任务
        if run_id in self.running_tasks:
            task = self.running_tasks[run_id]
            if not task.done():
                # 使用asyncio的标准取消机制
                # 这会在下一个await点抛出CancelledError
                task.cancel()
                logger.info(f"Cancellation requested for run_id: {run_id}")
                return {
                    "status": "success",
                    "run_id": run_id,
                    "message": "Cancellation signal sent, task will be cancelled at next await point"
                }
            else:
                logger.info(f"Task already completed for run_id: {run_id}")
                return {
                    "status": "already_completed",
                    "run_id": run_id,
                    "message": "Task has already completed"
                }
        else:
            logger.warning(f"No active task found for run_id: {run_id}")
            return {
                "status": "not_found",
                "run_id": run_id,
                "message": "No active task found with this run_id. Task may have already completed or run_id is invalid."
            }

    # 运行指定节点：本地/HTTP 通用
    async def run_node(self, node_id: str, payload: Dict[str, Any], ctx=None) -> Any:
        if ctx is None or Context.run_id == "":
            ctx = new_context(method="node_run")

        _graph = self._get_graph()
        node_func, input_cls, output_cls = graph_helper.get_graph_node_func_with_inout(_graph.get_graph(), node_id)
        if node_func is None or input_cls is None:
            raise KeyError(f"node_id '{node_id}' not found")

        parser = LangGraphParser(_graph)
        metadata = parser.get_node_metadata(node_id) or {}

        _g = StateGraph(input_cls, input_schema=input_cls, output_schema=output_cls)
        _g.add_node("sn", node_func, metadata=metadata)
        _g.set_entry_point("sn")
        _g.add_edge("sn", END)
        _graph = _g.compile()

        run_config = init_run_config(_graph, ctx)
        return await _graph.ainvoke(payload, config=run_config)

    def graph_inout_schema(self) -> Any:
        if graph_helper.is_agent_proj():
            return {"input_schema": {}, "output_schema": {}}
        builder = getattr(self._get_graph(), 'builder', None)
        if builder is not None:
            input_cls = getattr(builder, 'input_schema', None) or self.graph.get_input_schema()
            output_cls = getattr(builder, 'output_schema', None) or self.graph.get_output_schema()
        else:
            logger.warning(f"No builder input schema found for graph_inout_schema, using graph input schema instead")
            input_cls = self.graph.get_input_schema()
            output_cls = self.graph.get_output_schema()

        return {
            "input_schema": input_cls.model_json_schema(), 
            "output_schema": output_cls.model_json_schema(),
            "code":0,
            "msg":""
        }

    async def astream(self, payload: Dict[str, Any], graph: CompiledStateGraph, run_config: RunnableConfig, ctx=Context, run_opt: Optional[RunOpt] = None) -> AsyncIterable[Any]:
        stream_runner = self._get_stream_runner()
        async for chunk in stream_runner.astream(payload, graph, run_config, ctx, run_opt):
            yield chunk


service = GraphService()

async_runtime: Optional[AsyncTaskRuntime] = None
async_graph: Optional[CompiledStateGraph] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    @event.listens_for(engine, "connect")
    def _set_utc(dbapi_conn, _):
        with dbapi_conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC'")
    checkpointer = get_memory_saver()
    if graph_helper.is_agent_proj():
        base = graph_helper.get_agent_instance("agents.agent", None)
    else:
        base = graph_helper.get_graph_instance("graphs.graph")
    sync_graph = base.builder.compile()
    global async_graph, async_runtime
    async_graph = base.builder.compile(checkpointer=checkpointer)
    service.set_graph(sync_graph)
    async_runtime = AsyncTaskRuntime(
        session_factory=get_session, engine=engine,
        graph=async_graph, checkpointer=checkpointer,
    )
    yield
    if async_runtime is not None:
        await async_runtime.shutdown()

app = FastAPI(lifespan=lifespan)


# 静态文件目录（项目根目录下的 assets）
import os
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


@app.get("/")
async def root():
    """根路径 - 返回前端页面"""
    index_path = os.path.join(ASSETS_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {
        "service": "vibe-coding",
        "status": "running",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "endpoints": {
            "POST /v1/chat/completions": "OpenAI 兼容对话接口",
            "POST /run": "同步运行任务",
            "POST /stream_run": "流式运行任务",
            "POST /async_run": "异步运行任务",
            "GET /health": "健康检查",
            "GET /task/{task_id}": "查询任务状态",
        },
    }


# OpenAI 兼容接口处理器
openai_handler = OpenAIChatHandler(service)


@app.post("/async_run")
async def http_async_run(request: Request) -> dict:
    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_async_run: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {extract_core_stack()}")
    try:
        deadline_sec = parse_deadline_sec(request.headers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 一个 ID 走到底：task_id == run_id == thread_id == ctx.run_id == coze_run_id。
    # 优先用上游 x-run-id；没传就生成 UUID。
    run_id = request.headers.get(_ASYNC_HEADER_X_RUN_ID) or uuid.uuid4().hex

    # ctx 在 handler scope 构造，与同步 /run 路径一致；后面 new_context 默认会
    # 给 run_id 一个新 UUID，同步路径也是显式覆盖（main.py /run 处），这里同理。
    ctx = _new_async_ctx(method="async_run", headers=request.headers)
    ctx.run_id = run_id
    request_context.set(ctx)  # 与其他 HTTP endpoint 一致：让日志组件拿到 run_id 等信息
    run_config = init_run_config(async_graph, ctx)
    run_config["recursion_limit"] = async_task_config.RECURSION_LIMIT
    run_config.setdefault("configurable", {})["thread_id"] = run_id

    biz_context = extract_biz_context(request.headers) or {}
    biz_context[_ASYNC_HEADER_X_RUN_ID] = run_id  # 也留 DB 一份方便审计/排查

    try:
        return await async_runtime.submit(
            task_id=run_id,
            payload=payload,
            biz_context=biz_context,
            deadline_sec=deadline_sec,
            run_config=run_config,
            ctx=ctx,
        )
    except AsyncTaskStorageError as e:
        raise HTTPException(status_code=503,
                            detail=f"async-task storage unavailable: {e}")


@app.get("/task/{task_id}")
async def http_get_task(task_id: str) -> dict:
    try:
        row = await async_runtime.get(task_id)
    except AsyncTaskStorageError as e:
        raise HTTPException(status_code=503,
                            detail=f"async-task storage unavailable: {e}")
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")
    return row


HEADER_X_RUN_ID = "x-run-id"
@app.post("/run")
async def http_run(request: Request) -> Dict[str, Any]:
    global result
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except Exception as e:
        body_text = str(raw_body)
        raise HTTPException(status_code=400,
                            detail=f"Invalid JSON format: {body_text}, traceback: {traceback.format_exc()}, error: {e}")

    ctx = new_context(method="run", headers=request.headers)
    # 优先使用上游指定的 run_id，保证 cancel 能精确匹配
    upstream_run_id = request.headers.get(HEADER_X_RUN_ID)
    if upstream_run_id:
        ctx.run_id = upstream_run_id
    run_id = ctx.run_id
    request_context.set(ctx)

    logger.info(
        f"Received request for /run: "
        f"run_id={run_id}, "
        f"query={dict(request.query_params)}, "
        f"body={body_text}"
    )

    try:
        payload = await request.json()

        # 创建任务并记录 - 这是关键，让我们可以通过run_id取消任务
        task = asyncio.create_task(service.run(payload, ctx))
        service.running_tasks[run_id] = task

        try:
            result = await asyncio.wait_for(task, timeout=float(TIMEOUT_SECONDS))
        except asyncio.TimeoutError:
            logger.error(f"Run execution timeout after {TIMEOUT_SECONDS}s for run_id: {run_id}")
            task.cancel()
            try:
                result = await task
            except asyncio.CancelledError:
                return {
                    "status": "timeout",
                    "run_id": run_id,
                    "message": f"Execution timeout: exceeded {TIMEOUT_SECONDS} seconds"
                }

        if not result:
            result = {}
        if isinstance(result, dict):
            result["run_id"] = run_id
        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format, {extract_core_stack()}")

    except asyncio.CancelledError:
        logger.info(f"Request cancelled for run_id: {run_id}")
        result = {"status": "cancelled", "run_id": run_id, "message": "Execution was cancelled"}
        return result

    except Exception as e:
        # 使用错误分类器获取错误信息
        error_response = service.error_classifier.get_error_response(e, {"node_name": "http_run", "run_id": run_id})
        logger.error(
            f"Unexpected error in http_run: [{error_response['error_code']}] {error_response['error_message']}, "
            f"traceback: {traceback.format_exc()}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": error_response["error_code"],
                "error_message": error_response["error_message"],
                "stack_trace": extract_core_stack(),
            }
        )
    finally:
        cozeloop.flush()


HEADER_X_WORKFLOW_STREAM_MODE = "x-workflow-stream-mode"


def _register_task(run_id: str, task: asyncio.Task):
    service.running_tasks[run_id] = task


@app.post("/stream_run")
async def http_stream_run(request: Request):
    ctx = new_context(method="stream_run", headers=request.headers)
    # 优先使用上游指定的 run_id，保证 cancel 能精确匹配
    upstream_run_id = request.headers.get(HEADER_X_RUN_ID)
    if upstream_run_id:
        ctx.run_id = upstream_run_id
    workflow_stream_mode = request.headers.get(HEADER_X_WORKFLOW_STREAM_MODE, "").lower()
    workflow_debug = workflow_stream_mode == "debug"
    request_context.set(ctx)
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except Exception as e:
        body_text = str(raw_body)
        raise HTTPException(status_code=400,
                            detail=f"Invalid JSON format: {body_text}, traceback: {extract_core_stack()}, error: {e}")
    run_id = ctx.run_id
    is_agent = graph_helper.is_agent_proj()
    logger.info(
        f"Received request for /stream_run: "
        f"run_id={run_id}, "
        f"is_agent_project={is_agent}, "
        f"query={dict(request.query_params)}, "
        f"body={body_text}"
    )
    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_stream_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format:{extract_core_stack()}")

    if is_agent:
        stream_generator = agent_stream_handler(
            payload=payload,
            ctx=ctx,
            run_id=run_id,
            stream_sse_func=service.stream_sse,
            sse_event_func=service._sse_event,
            error_classifier=service.error_classifier,
            register_task_func=_register_task,
        )
    else:
        stream_generator = workflow_stream_handler(
            payload=payload,
            ctx=ctx,
            run_id=run_id,
            stream_sse_func=service.stream_sse,
            sse_event_func=service._sse_event,
            error_classifier=service.error_classifier,
            register_task_func=_register_task,
            run_opt=RunOpt(workflow_debug=workflow_debug),
        )

    response = StreamingResponse(stream_generator, media_type="text/event-stream")
    return response

@app.post("/cancel/{run_id}")
async def http_cancel(run_id: str, request: Request):
    """
    取消指定run_id的执行

    使用asyncio.Task.cancel()实现取消,这是Python标准的异步任务取消机制。
    LangGraph会在节点之间的await点检查CancelledError,实现优雅取消。
    """
    ctx = new_context(method="cancel", headers=request.headers)
    request_context.set(ctx)
    logger.info(f"Received cancel request for run_id: {run_id}")
    result = service.cancel_run(run_id, ctx)
    return result


@app.post(path="/node_run/{node_id}")
async def http_node_run(node_id: str, request: Request):
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        body_text = str(raw_body)
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {body_text}")
    ctx = new_context(method="node_run", headers=request.headers)
    request_context.set(ctx)
    logger.info(
        f"Received request for /node_run/{node_id}: "
        f"query={dict(request.query_params)}, "
        f"body={body_text}",
    )

    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_node_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format:{extract_core_stack()}")
    try:
        return await service.run_node(node_id, payload, ctx)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail=f"node_id '{node_id}' not found or input miss required fields, traceback: {extract_core_stack()}")
    except Exception as e:
        # 使用错误分类器获取错误信息
        error_response = service.error_classifier.get_error_response(e, {"node_name": node_id})
        logger.error(
            f"Unexpected error in http_node_run: [{error_response['error_code']}] {error_response['error_message']}, "
            f"traceback: {traceback.format_exc()}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": error_response["error_code"],
                "error_message": error_response["error_message"],
                "stack_trace": extract_core_stack(),
            }
        )
    finally:
        cozeloop.flush()


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """OpenAI Chat Completions API 兼容接口"""
    ctx = new_context(method="openai_chat", headers=request.headers)
    request_context.set(ctx)

    logger.info(f"Received request for /v1/chat/completions: run_id={ctx.run_id}")

    try:
        payload = await request.json()
        result = await openai_handler.handle(payload, ctx)

        # Format JSON content in the response to readable Markdown
        # result may be JSONResponse (has body) or dict
        result_body = result
        if hasattr(result, 'body'):
            result_body = json.loads(result.body)

        if isinstance(result_body, dict) and "choices" in result_body:
            for choice in result_body.get("choices", []):
                msg = choice.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 100:
                    try:
                        msg["content"] = format_teaching_content(content)
                    except Exception as fmt_err:
                        logger.warning(f"Content formatting failed: {fmt_err}")

            return JSONResponse(content=result_body)

        return result
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in openai_chat_completions: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    finally:
        cozeloop.flush()


@app.get("/health")
async def health_check():
    try:
        # 这里可以添加更多的健康检查逻辑
        return {
            "status": "ok",
            "message": "Service is running",
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get(path="/graph_parameter")
async def http_graph_inout_parameter(request: Request):
    return service.graph_inout_schema()

# 挂载静态文件（前端资源）
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

def parse_args():
    parser = argparse.ArgumentParser(description="Start FastAPI server")
    parser.add_argument("-m", type=str, default="http", help="Run mode, support http,flow,node")
    parser.add_argument("-n", type=str, default="", help="Node ID for single node run")
    parser.add_argument("-p", type=int, default=5000, help="HTTP server port")
    parser.add_argument("-i", type=str, default="", help="Input JSON string for flow/node mode")
    return parser.parse_args()


def parse_input(input_str: str) -> Dict[str, Any]:
    """Parse input string, support both JSON string and plain text"""
    if not input_str:
        return {"text": "你好"}

    # Try to parse as JSON first
    try:
        return json.loads(input_str)
    except json.JSONDecodeError:
        # If not valid JSON, treat as plain text
        return {"text": input_str}

def start_http_server(port):
    workers = 1
    reload = False
    if graph_helper.is_dev_env():
        reload = True

    logger.info(f"Start HTTP Server, Port: {port}, Workers: {workers}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload, workers=workers)

if __name__ == "__main__":
    args = parse_args()
    if args.m == "http":
        start_http_server(args.p)
    elif args.m == "flow":
        payload = parse_input(args.i)
        result = asyncio.run(service.run(payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.m == "node" and args.n:
        payload = parse_input(args.i)
        result = asyncio.run(service.run_node(args.n, payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.m == "agent":
        agent_ctx = new_context(method="agent")
        for chunk in service.stream(
                {
                    "type": "query",
                    "session_id": "1",
                    "message": "你好",
                    "content": {
                        "query": {
                            "prompt": [
                                {
                                    "type": "text",
                                    "content": {"text": "现在几点了？请调用工具获取当前时间"},
                                }
                            ]
                        }
                    },
                },
                run_config={"configurable": {"session_id": "1"}},
                ctx=agent_ctx,
        ):
            print(chunk)
