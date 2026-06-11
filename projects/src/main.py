"""
教思 AI 教学孪生系统 — 主入口

重构 v3.0: 简化架构
- 删除 KEY_ZH_MAP / format_teaching_content 等 JSON→Markdown 代码（已在 lesson_prep.py 的 format_output 中处理）
- 简化流式过滤：3 节点只需区分 chat_reply vs format_output
- 新增 /api/teacher-config 端点供前端获取/保存教师配置
"""

import argparse
import asyncio
import contextvars
import json
import threading
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Iterable, AsyncIterable, AsyncGenerator, Optional
import cozeloop
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from coze_coding_dev_sdk import LLMClient
from coze_coding_utils.runtime_ctx.context import new_context, Context
from coze_coding_utils.helper import graph_helper
from coze_coding_utils.log.node_log import LOG_FILE
from coze_coding_utils.log.write_log import setup_logging, request_context
from coze_coding_utils.log.config import LOG_LEVEL
from coze_coding_utils.error.classifier import ErrorClassifier, classify_error
from coze_coding_utils.helper.stream_runner import AgentStreamRunner, WorkflowStreamRunner, RunOpt
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
    max_bytes=100 * 1024 * 1024,
    backup_count=5,
    log_level=LOG_LEVEL,
    use_json_format=True,
    console_output=True,
)

logger = logging.getLogger(__name__)
from coze_coding_utils.helper.agent_helper import to_stream_input
from coze_coding_utils.openai.handler import OpenAIChatHandler
from coze_coding_utils.openai.converter.response_converter import ResponseConverter
from coze_coding_utils.log.parser import LangGraphParser
from coze_coding_utils.log.err_trace import extract_core_stack
from coze_coding_utils.log.loop_trace import init_run_config, init_agent_config
from config.llm_config import Thresholds
from graphs.graph import compile_graph

TIMEOUT_SECONDS = Thresholds.TIMEOUT_SECONDS


# ============================================================
# GraphService
# ============================================================

class GraphService:
    def __init__(self):
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.error_classifier = ErrorClassifier()
        self._agent_stream_runner = AgentStreamRunner()
        self._workflow_stream_runner = WorkflowStreamRunner()
        self._graph = None
        self._graph_lock = threading.Lock()

    def set_graph(self, graph) -> None:
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
        return self._workflow_stream_runner

    def stream(self, payload: Dict[str, Any], run_config: RunnableConfig, ctx=Context) -> Iterable[Any]:
        graph = self._get_graph(ctx)
        runner = self._get_stream_runner()
        return runner.stream(graph, payload, run_config, ctx)

    async def run(self, payload: Dict[str, Any], ctx=None) -> Dict[str, Any]:
        if ctx is None:
            ctx = new_context(method="run")
        graph = self._get_graph(ctx)
        config = {"configurable": {"thread_id": payload.get("session_id", "default")}, "recursion_limit": 50}
        result = await graph.ainvoke(payload, config=config, context=ctx)
        return result

    async def stream_sse(self, payload: Dict[str, Any], ctx=None, run_opt: Optional[RunOpt] = None) -> AsyncGenerator[str, None]:
        if ctx is None:
            ctx = new_context(method="stream_sse")
        graph = self._get_graph(ctx)
        runner = self._get_stream_runner()
        async for event in runner.astream(graph, payload, ctx, run_opt=run_opt):
            yield self._sse_event(event)

    def cancel_run(self, run_id: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
        task = self.running_tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            del self.running_tasks[run_id]
            return {"status": "cancelled", "run_id": run_id}
        return {"status": "not_found", "run_id": run_id}

    async def run_node(self, node_id: str, payload: Dict[str, Any], ctx=None) -> Any:
        if ctx is None:
            ctx = new_context(method="run_node")
        graph = self._get_graph(ctx)
        config = {"configurable": {"thread_id": payload.get("session_id", "default")}, "recursion_limit": 50}
        result = await graph.ainvoke(payload, config=config, context=ctx, debug=False)
        return result

    def graph_inout_schema(self) -> Any:
        try:
            graph = self._get_graph()
            return graph.get_graph()
        except Exception:
            return {}


service = GraphService()
openai_handler = OpenAIChatHandler(service)
async_graph = None
async_runtime = None


# ============================================================
# Lifespan & App
# ============================================================

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
    sync_graph = compile_graph(base.builder)
    global async_graph, async_runtime
    async_graph = compile_graph(base.builder, checkpointer=checkpointer)
    service.set_graph(sync_graph)
    async_runtime = AsyncTaskRuntime(
        session_factory=get_session, engine=engine,
        graph=async_graph, checkpointer=checkpointer,
    )
    yield
    if async_runtime is not None:
        await async_runtime.shutdown()

app = FastAPI(lifespan=lifespan)

import os
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


# ============================================================
# 前端页面 & 教师配置 API
# ============================================================

@app.get("/")
async def root():
    index_path = os.path.join(ASSETS_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"service": "vibe-coding", "status": "running"}


# 教师配置选项（供前端表单下拉选择）
TEACHER_CONFIG = {
    "subjects": ["语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "政治", "体育", "音乐", "美术", "信息技术"],
    "grades": ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级",
               "初一", "初二", "初三", "高一", "高二", "高三"],
    "objectives": ["知识与技能", "过程与方法", "情感态度与价值观", "核心素养导向", "综合能力培养"],
    "key_points": ["概念理解", "公式推导", "方法掌握", "技能训练", "思维培养", "知识应用"],
    "difficult_points": ["抽象概念理解", "复杂计算", "逻辑推理", "知识迁移", "综合应用", "创新思维"],
    "durations": [20, 30, 40, 45, 60, 90],
    "styles": ["启发式互动型", "系统讲授型", "情感体验型", "任务驱动型", "混合型"],
}


@app.get("/api/teacher-config")
async def get_teacher_config():
    """返回教师配置选项列表，供前端表单使用"""
    return TEACHER_CONFIG


# ============================================================
# 异步任务相关端点
# ============================================================

@app.post("/async_run")
async def http_async_run(request: Request) -> dict:
    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    ctx = new_context(method="async_run", headers=request.headers)
    request_context.set(ctx)
    deadline_sec = parse_deadline_sec(request.headers)
    biz_context = extract_biz_context(payload)
    session_id = payload.get("session_id", str(uuid.uuid4()))

    if async_runtime is None:
        raise HTTPException(status_code=503, detail="Async runtime not initialized")

    try:
        task_id = await async_runtime.submit(
            payload=payload,
            session_id=session_id,
            deadline_sec=deadline_sec,
            biz_context=biz_context,
            ctx=ctx,
        )
        return {"task_id": task_id, "status": "submitted", "session_id": session_id}
    except AsyncTaskStorageError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cozeloop.flush()


@app.get("/task/{task_id}")
async def http_get_task(task_id: str) -> dict:
    if async_runtime is None:
        raise HTTPException(status_code=503, detail="Async runtime not initialized")
    result = await async_runtime.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return result


# ============================================================
# 同步运行
# ============================================================

@app.post("/run")
async def http_run(request: Request) -> Dict[str, Any]:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    ctx = new_context(method="run", headers=request.headers)
    request_context.set(ctx)
    try:
        result = await service.run(payload, ctx=ctx)
        return result
    except Exception as e:
        logger.error(f"Run error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cozeloop.flush()


def _register_task(run_id: str, task: asyncio.Task):
    service.running_tasks[run_id] = task


@app.post("/stream_run")
async def http_stream_run(request: Request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    ctx = new_context(method="stream_run", headers=request.headers)
    request_context.set(ctx)
    try:
        return StreamingResponse(
            service.stream_sse(payload, ctx=ctx),
            media_type="text/event-stream",
        )
    except Exception as e:
        logger.error(f"Stream run error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cozeloop.flush()


@app.post("/cancel/{run_id}")
async def http_cancel(run_id: str, request: Request):
    ctx = new_context(method="cancel", headers=request.headers)
    request_context.set(ctx)
    result = service.cancel_run(run_id, ctx=ctx)
    cozeloop.flush()
    return result


@app.post(path="/node_run/{node_id}")
async def http_node_run(node_id: str, request: Request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    ctx = new_context(method="node_run", headers=request.headers)
    request_context.set(ctx)
    try:
        result = await service.run_node(node_id, payload, ctx=ctx)
        return result
    except Exception as e:
        logger.error(f"Node run error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cozeloop.flush()


# ============================================================
# OpenAI 兼容接口（简化流式过滤）
# ============================================================

# 3 节点的进度映射
NODE_PROGRESS_MAP = {
    "intent_router":           "intent",
    "chat_reply":              "intent",
    "generate_lesson_plan":    "generating",
    "format_output":           "formatting",
}

# 只放行这些节点的 LLM token 流
OUTPUT_NODES = {"format_output", "chat_reply"}


def _build_sse_event(event_type: str, data: Any) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_openai_chunk(request_id: str, model: str, created: int,
                        delta_content: str = "", delta_role: str = "",
                        finish_reason: str = None) -> str:
    delta = {}
    if delta_role:
        delta["role"] = delta_role
    if delta_content:
        delta["content"] = delta_content
    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """OpenAI Chat Completions API 兼容接口"""
    ctx = new_context(method="openai_chat", headers=request.headers)
    request_context.set(ctx)

    try:
        payload = await request.json()
        req = openai_handler.request_converter.parse(payload)
        session_id = openai_handler.request_converter.get_session_id(req)
        if not session_id:
            return JSONResponse(
                content={"error": {"message": "session_id is required", "type": "invalid_request_error", "code": "400001"}},
                status_code=400,
            )

        stream_input = openai_handler.request_converter.to_stream_input(req)
        if not stream_input.get("messages"):
            return JSONResponse(
                content={"error": {"message": "No user message found", "type": "invalid_request_error", "code": "400002"}},
                status_code=400,
            )

        # 注入教师信息到 state（从前端 extra_body 传入）
        extra = payload.get("extra_body", {}) or {}
        for field in ["lesson_subject", "lesson_grade", "lesson_objectives",
                       "key_points", "difficult_points", "lesson_duration",
                       "style_preference", "lesson_topic"]:
            if extra.get(field):
                stream_input[field] = extra[field]

        if not req.stream:
            # 非流式
            result = await openai_handler._handle_non_stream(
                stream_input, session_id,
                ResponseConverter(request_id=f"chatcmpl-{ctx.run_id}", model=req.model),
                ctx,
            )
            return result

        # 流式：自定义过滤
        return StreamingResponse(
            _filtered_stream_generator(stream_input, session_id, req.model, ctx),
            media_type="text/event-stream",
        )

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    finally:
        cozeloop.flush()


async def _filtered_stream_generator(
    stream_input: Dict[str, Any],
    session_id: str,
    model: str,
    ctx,
) -> AsyncGenerator[str, None]:
    """
    简化版流式生成器（3 节点架构）：
    - updates 模式：推送节点进度 + format_output 的教案 Markdown
    - messages 模式：只放行 chat_reply 的闲聊文本
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    context_copy = contextvars.copy_context()
    request_id = f"chatcmpl-{ctx.run_id}"
    created = int(time.time())

    def producer():
        from utils.helper import graph_helper as _gh
        graph = service._get_graph(ctx)

        if _gh.is_agent_proj():
            run_config = init_agent_config(graph, ctx)
        else:
            run_config = init_run_config(graph, ctx)

        run_config["recursion_limit"] = 50
        run_config["configurable"] = {"thread_id": session_id}

        sent_role = False
        completed_nodes = set()
        text_sent_via_messages = False

        try:
            items = graph.stream(
                stream_input,
                stream_mode=["messages", "updates"],
                config=run_config,
                context=ctx,
            )

            for mode, chunk_data in items:
                # --- updates 模式：节点进度 + format_output 输出 ---
                if mode == "updates":
                    if isinstance(chunk_data, dict):
                        for node_name, node_output in chunk_data.items():
                            # 推送节点完成进度
                            if node_name not in completed_nodes:
                                completed_nodes.add(node_name)
                                progress_id = NODE_PROGRESS_MAP.get(node_name, node_name)
                                loop.call_soon_threadsafe(queue.put_nowait,
                                    _build_sse_event("node_progress", {
                                        "node": node_name,
                                        "progress_id": progress_id,
                                        "status": "completed",
                                    })
                                )

                            # format_output: 提取最终教案
                            if node_name == "format_output" and isinstance(node_output, dict) and not text_sent_via_messages:
                                lesson_plan = node_output.get("final_lesson_plan", "")
                                if lesson_plan:
                                    if not sent_role:
                                        sent_role = True
                                        loop.call_soon_threadsafe(queue.put_nowait,
                                            _build_openai_chunk(request_id, model, created, delta_role="assistant"))
                                    loop.call_soon_threadsafe(queue.put_nowait,
                                        _build_openai_chunk(request_id, model, created, delta_content=lesson_plan))
                    continue

                # --- messages 模式：LLM token 流（只放行 chat_reply） ---
                if mode == "messages":
                    chunk, meta = chunk_data
                    chunk_type = chunk.__class__.__name__
                    node_name = (meta or {}).get("langgraph_node", "")

                    if chunk_type in ("AIMessageChunk", "AIMessage"):
                        text = getattr(chunk, "content", "")
                        if not text:
                            continue
                        # 只放行 chat_reply（闲聊文本）
                        if node_name == "chat_reply":
                            text_sent_via_messages = True
                            if not sent_role:
                                sent_role = True
                                loop.call_soon_threadsafe(queue.put_nowait,
                                    _build_openai_chunk(request_id, model, created, delta_role="assistant"))
                            loop.call_soon_threadsafe(queue.put_nowait,
                                _build_openai_chunk(request_id, model, created, delta_content=text))

            # 流结束
            if sent_role:
                loop.call_soon_threadsafe(queue.put_nowait,
                    _build_openai_chunk(request_id, model, created, finish_reason="stop"))
            loop.call_soon_threadsafe(queue.put_nowait, "data: [DONE]\n\n")

        except Exception as ex:
            logger.error(f"Stream producer error: {ex}", exc_info=True)
            err = classify_error(ex, {"node_name": "openai_stream"})
            error_data = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "error": {"message": str(ex), "type": "internal_error", "code": str(err.code)},
            }
            loop.call_soon_threadsafe(queue.put_nowait,
                f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n")
            loop.call_soon_threadsafe(queue.put_nowait, "data: [DONE]\n\n")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=lambda: context_copy.run(producer), daemon=True).start()

    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
    except asyncio.CancelledError:
        logger.info(f"Stream cancelled for run_id: {ctx.run_id}")
        raise


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Service is running"}


@app.get(path="/graph_parameter")
async def http_graph_inout_parameter(request: Request):
    return service.graph_inout_schema()


# 挂载静态文件
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


def parse_args():
    parser = argparse.ArgumentParser(description="Start FastAPI server")
    parser.add_argument("-m", type=str, default="http", help="Run mode")
    parser.add_argument("-n", type=str, default="", help="Node ID for single node run")
    parser.add_argument("-p", type=int, default=5000, help="HTTP server port")
    parser.add_argument("-i", type=str, default="", help="Input JSON string")
    return parser.parse_args()


def parse_input(input_str: str) -> Dict[str, Any]:
    if not input_str:
        return {"text": "你好"}
    try:
        return json.loads(input_str)
    except json.JSONDecodeError:
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
