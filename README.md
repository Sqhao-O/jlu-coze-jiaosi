# 「教思」AI 教学孪生系统

> **教思 — 教之以思，而非教之以器**
>
> 基于 LangGraph StateGraph 的 AI 教学辅助平台，为教师提供智能备课、课堂预演、学情推演、互动设计、智能命题、PPT 大纲等一站式教学支持。

---

## 目录

1. [系统架构](#1-系统架构)
2. [项目目录结构](#2-项目目录结构)
3. [核心模块详解](#3-核心模块详解)
   - [3.1 HTTP 服务层 (`main.py`)](#31-http-服务层-mainpy)
   - [3.2 工作流引擎 (`graphs/`)](#32-工作流引擎-graphs)
   - [3.3 知识库系统 (`knowledge/`)](#33-知识库系统-knowledge)
   - [3.4 存储层 (`storage/`)](#34-存储层-storage)
   - [3.5 配置与工具 (`config/` `utils/` `tools/`)](#35-配置与工具-config-utils-tools)
   - [3.6 API 路由 (`api/`)](#36-api-路由-api)
4. [API 接口规范](#4-api-接口规范)
5. [运行与部署](#5-运行与部署)
6. [技术栈清单](#6-技术栈清单)
7. [开发指南](#7-开发指南)

---

## 1. 系统架构

### 1.1 整体架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                         用户交互层                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ 前端聊天界面       │  │  Swagger UI      │  │ OpenAI 兼容接口 │  │
│  │ (HTML/CSS/JS)     │  │  (/docs)         │  │ /v1/chat/...   │  │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬────────┘  │
└───────────┼─────────────────────┼────────────────────┼───────────┘
            │                     │                    │
            ▼                     ▼                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                   HTTP 服务层 (FastAPI + Uvicorn)                  │
│                                                                  │
│  GraphService — 工作流执行引擎                                     │
│  ├─ run()            同步执行 (graph.ainvoke)                     │
│  ├─ stream_sse()     SSE 流式执行 (graph.astream)                 │
│  ├─ run_node()       单节点调试                                    │
│  └─ cancel_run()     取消运行                                     │
│                                                                  │
│  API 路由                                                        │
│  ├─ /v1/chat/completions    OpenAI 兼容对话接口                    │
│  ├─ /api/teacher-config     教师配置选项                           │
│  ├─ /api/knowledge-bases/*  知识库 CRUD + 上传 + 检索              │
│  ├─ /run  /stream_run       内部执行接口                           │
│  └─ /health                 健康检查                              │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                  工作流编排层 (LangGraph StateGraph)               │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  lesson_prep.py — 多功能工作流 (唯一活跃工作流)              │   │
│  │                                                           │   │
│  │  intent_router → rag_enrich → {功能节点} → format_output   │   │
│  │                                                           │   │
│  │  8 种功能模式:                                              │   │
│  │  📋教案生成  🎭课堂预演  🔍盲区检测  👥学情推演              │   │
│  │  💬互动设计  📝智能命题  📊PPT大纲   🗨️自由对话              │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                        基础设施层                                  │
│                                                                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │
│  │ LLM 客户端  │ │ 状态管理    │ │ 存储层      │ │ 知识库系统    │  │
│  │            │ │            │ │            │ │              │  │
│  │ LLMClient  │ │ StateGraph │ │ PostgreSQL │ │ 文档解析     │  │
│  │ (扣子 SDK) │ │ TypedDict  │ │ / SQLite   │ │ PDF/Word/    │  │
│  │            │ │ Annotated  │ │            │ │ Excel/PPT    │  │
│  │ Embedding  │ │            │ │ AsyncPG    │ │              │  │
│  │ Client     │ │ 条件路由    │ │ Saver      │ │ 文本分块     │  │
│  │            │ │            │ │ /Memory    │ │ 向量化       │  │
│  │ 模型:      │ │ Checkpoint │ │ Saver      │ │ 语义检索     │  │
│  │ doubao-    │ │            │ │            │ │              │  │
│  │ seed-pro   │ │            │ │ S3 存储    │ │ 元数据管理   │  │
│  │ /lite      │ │            │ │            │ │              │  │
│  └────────────┘ └────────────┘ └────────────┘ └──────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 请求数据流

```
用户输入（前端 / API / OpenAI 客户端）
    │
    ▼
┌────────────────────────────────────────────┐
│ FastAPI 路由层                              │
│ ├─ 解析请求体                               │
│ ├─ 创建请求上下文 (new_context)              │
│ ├─ 提取 session_id / mode / extra_body      │
│ └─ 构建 stream_input: {messages, mode,      │
│       lesson_subject, lesson_grade, ...}    │
└──────────────────┬─────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────┐
│ GraphService                                │
│ ├─ 获取编译后的 StateGraph (懒加载 + 缓存)    │
│ ├─ 设置 thread_id + recursion_limit=50      │
│ ├─ 注入 checkpointer (状态持久化)            │
│ └─ graph.astream(input, stream_mode=        │
│       ["messages", "updates"])              │
└──────────────────┬─────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────┐
│ LangGraph 工作流执行（条件路由）               │
│                                             │
│ ① intent_router:  确定 mode → intent        │
│ ② rag_enrich:     知识库检索 + 上下文注入    │
│ ③ {功能节点}:     LLM 生成结构化 JSON       │
│ ④ format_output:  JSON → Markdown 格式化    │
└──────────────────┬─────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────┐
│ 响应输出                                     │
│ ├─ SSE:         实时推送 + 节点进度          │
│ ├─ JSONResponse: OpenAI 兼容格式            │
│ └─ Dict:        内部 API 原始结果            │
└────────────────────────────────────────────┘
```

### 1.3 架构设计原则

| 原则 | 实现 |
|------|------|
| **单一工作流** | 全部功能集成在 1 个 StateGraph 中，根据 `mode` 字段路由到不同功能节点 |
| **状态驱动** | `LessonPrepState` 通过 `TypedDict + Annotated` 在各节点间自动合并传递 |
| **意图路由** | 前端显式传入 `mode` → 后端关键词降级 → 条件边路由 |
| **RAG 增强** | 所有功能模式共享统一的 `rag_enrich` 节点，知识库上下文注入 System Prompt |
| **格式分离** | LLM 生成 JSON → `format_output` 统一转 Markdown，关注点分离 |
| **协议兼容** | 内置 OpenAI `/v1/chat/completions` 兼容接口 |
| **降级优先** | 开发环境自动降级：PostgreSQL→SQLite, PostgresSaver→MemorySaver, 向量DB→内存 |

---

## 2. 项目目录结构

```
projects/
├── .coze                          # 平台项目配置 (sub_id, name, project_type)
├── pyproject.toml                 # Python 依赖声明 + uv 配置
├── uv.lock                        # uv 依赖锁文件
│
├── src/                           # 源码根目录
│   ├── main.py                    # ★ HTTP 服务入口 (670 行)
│   │
│   ├── graphs/                    # LangGraph 工作流
│   │   ├── __init__.py            # Graph 包装器 → 编译入口
│   │   ├── graph.py               # compile_graph() 编译函数
│   │   ├── state.py               # ★ 状态定义 — LessonPrepState + WorkflowMode
│   │   └── lesson_prep.py         # ★ 多功能工作流 (1500 行)
│   │                              #   intent_router → rag_enrich → 8个功能节点 → format_output
│   │
│   ├── knowledge/                 # 知识库核心
│   │   ├── parser.py              # 文档解析 (PDF/Word/Excel/PPT/TXT)
│   │   ├── chunker.py             # 文本分块 (段落感知 + 滑动窗口)
│   │   ├── embedder.py            # 向量化 + 语义检索
│   │   ├── vector_store.py        # VectorStore 抽象 + InMemoryVectorStore
│   │   └── store.py               # 知识库/文档元数据管理 (JSON 文件)
│   │
│   ├── api/
│   │   └── knowledge.py           # 知识库 REST API (CRUD + 上传 + 检索)
│   │
│   ├── storage/                   # 存储层
│   │   ├── database/
│   │   │   ├── db.py              # ★ 数据库引擎 (PG 主 + SQLite 降级 + 重试)
│   │   │   └── shared/model.py    # SQLAlchemy Base
│   │   ├── memory/
│   │   │   └── memory_saver.py    # ★ 状态检查点 (AsyncPostgresSaver + MemorySaver)
│   │   └── s3/
│   │       └── s3_storage.py      # S3 对象存储 (上传/下载/分片/签名URL)
│   │
│   ├── config/
│   │   └── llm_config.py          # LLM 配置 (3种预设 + 模型常量 + 阈值)
│   │
│   ├── tools/
│   │   └── utility_tools.py       # 工具集 (提示词管理/RAG检索/格式化辅助)
│   │
│   ├── utils/
│   │   ├── helper.py              # graph_helper 代理
│   │   ├── json_parser.py         # ★ 统一 JSON 解析 (容错/清洗/Markdown清理)
│   │   ├── ppt_client.py          # Coze PPT 工作流客户端
│   │   ├── file/file.py           # 通用文件操作
│   │   └── log/loop_trace.py      # 循环追踪配置
│   │
│   ├── agents/                    # (备用) LangChain Agent 模式
│   │   ├── agent.py               # 主控 Agent + 5 个教学 Tool
│   │   └── prompts.py             # 6 个专业 Agent 提示词模板
│   │
│   └── __init__.py
│
├── assets/                        # 静态资源
│   ├── index.html                 # 前端聊天界面
│   └── logo.png
│
├── config/                        # 配置文件
│   ├── agent_llm_config.json      # Agent LLM 配置 (备用)
│   └── prompts/                   # 6 个专业提示词模板文件
│       ├── teaching_mirror.txt
│       ├── learning_insight.txt
│       ├── strategy_sandbox.txt
│       ├── classroom_co.txt
│       ├── growth_tracker.txt
│       └── student_simulator.txt
│
└── scripts/                       # 运行脚本
    ├── setup.sh                   # 依赖安装 (uv sync)
    ├── http_run.sh                # HTTP 服务启动 (含环境检测)
    ├── local_run.sh               # 本地调试运行
    ├── pack.sh                    # 依赖锁定 (uv lock)
    ├── load_env.sh                # 环境变量加载
    └── load_env.py                # 平台环境变量注入
```

---

## 3. 核心模块详解

### 3.1 HTTP 服务层 (`main.py`)

**文件位置**: `src/main.py`（670 行）

#### 3.1.1 GraphService — 工作流执行引擎

整个系统的核心调度类，封装 LangGraph 的完整调用生命周期。

```python
class GraphService:
    """
    工作流执行引擎 — 单例管理 CompiledStateGraph 的懒加载、执行和生命周期。

    三种执行模式:
      run()        — 同步执行，await graph.ainvoke() → 完整 Dict
      stream_sse() — SSE 流式，async for graph.astream() → AsyncGenerator[str]
      run_node()   — 单节点调试，graph.ainvoke(debug=False)
    """

    def _get_graph(self, ctx):
        """懒加载 + 缓存编译后的图（线程安全）"""
        if self._graph is not None:
            return self._graph
        with self._graph_lock:
            if self._graph is not None:
                return self._graph
            # 当前使用 Graph 模式（非 Agent 模式）
            self._graph = graph_helper.get_graph_instance("graphs.graph")
            return self._graph
```

**三种执行模式对比**:

| 模式 | 方法 | 返回方式 | 适用场景 |
|------|------|---------|---------|
| 同步 | `run()` | 一次性返回完整 JSON | 批量处理、API 调用 |
| 流式 | `stream_sse()` | SSE (`text/event-stream`) | 实时展示进度 |
| 单节点 | `run_node()` | 一次返回单节点结果 | 调试 |

#### 3.1.2 OpenAI 兼容接口

```python
@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """
    完整兼容 OpenAI Chat Completions API 协议。

    流程:
    1. 解析 OpenAI 格式请求 → 提取 messages / model / stream / session_id
    2. 构建完整 messages（上下文联动，不丢失历史消息）
    3. 从 extra_body 注入教师参数到 stream_input
    4. 非流式: service.run() → 提取 final_output → 组装 OpenAI 格式响应
    5. 流式:   _filtered_stream_generator() → SSE 推送 + 节点进度
    """
```

**流式过滤策略** (`_filtered_stream_generator`):

```
graph.stream(stream_mode=["messages", "updates"])
    │
    ├── updates 模式 → 推送节点完成进度 (node_progress 事件)
    │   └── format_output 节点的 final_output → OpenAI chunk
    │
    └── messages 模式 → LLM token 流
        └── 只放行 chat_reply 节点（闲聊文本）
```

**进度事件映射**:

```python
NODE_PROGRESS_MAP = {
    "intent_router":        "intent",
    "rag_enrich":           "retrieving",
    "chat_reply":           "intent",
    "generate_lesson_plan": "generating",
    "simulate_classroom":   "generating",
    "detect_blindspots":    "generating",
    "simulate_students":    "generating",
    "design_interactions":  "generating",
    "generate_exam":        "generating",
    "generate_ppt":         "generating",
    "format_output":        "formatting",
}
```

#### 3.1.3 全路由表

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端聊天界面 (`assets/index.html`) |
| `/health` | GET | 健康检查 `{"status":"ok"}` |
| `/api/teacher-config` | GET | 教师配置选项（学科/年级/风格/模式等） |
| `/api/knowledge-bases/*` | * | 知识库 CRUD + 文档上传 + 检索 |
| `/v1/chat/completions` | POST | OpenAI 兼容对话接口 |
| `/run` | POST | 同步执行工作流 |
| `/stream_run` | POST | SSE 流式执行 |
| `/async_run` | POST | 异步执行（返回 task_id） |
| `/task/{task_id}` | GET | 查询异步任务状态 |
| `/cancel/{run_id}` | POST | 取消运行中的任务 |
| `/node_run/{node_id}` | POST | 单节点调试执行 |
| `/graph_parameter` | GET | 工作流输入/输出参数 schema |

#### 3.1.4 应用生命周期

```python
async def lifespan(app: FastAPI):
    # 启动时
    engine = get_engine()
    # 设置 UTC 时区
    # 初始化 checkpointer (AsyncPostgresSaver / MemorySaver)
    # 编译 StateGraph
    sync_graph = compile_graph(base.builder)
    async_graph = compile_graph(base.builder, checkpointer=checkpointer)
    # 初始化 AsyncTaskRuntime
    service.set_graph(sync_graph)
    yield
    # 关闭时
    await async_runtime.shutdown()
```

---

### 3.2 工作流引擎 (`graphs/`)

#### 3.2.1 图编译入口

**文件**: `graphs/__init__.py` + `graphs/graph.py`

```python
# graphs/__init__.py
class Graph:
    """Graph 包装器 — 为 main.py 提供 .builder 属性"""
    def __init__(self, workflow: str = "lesson_prep"):
        self._workflow = workflow

    def _build(self):
        from graphs.lesson_prep import build_lesson_prep_graph
        return build_lesson_prep_graph()  # 只构建这一种图

# graphs/graph.py
def compile_graph(builder, checkpointer=None):
    """编译 StateGraph → CompiledStateGraph"""
    kwargs = {}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    return builder.compile(**kwargs)
```

**编译链**: `build_lesson_prep_graph()` 返回 `StateGraph` → `compile_graph()` 编译为 `CompiledStateGraph` → 注入 `checkpointer` 启用状态持久化。

#### 3.2.2 状态定义 (`state.py`)

```python
class LessonPrepState(TypedDict, total=False):
    """
    统一工作流 State — 所有功能模式共享

    字段分类:
    ┌─────────────────────────────────────────────────────┐
    │ 对话消息                                             │
    │   messages: Annotated[list[AnyMessage], add_messages]│
    │                                                     │
    │ 意图路由                                             │
    │   intent: str        # "chat" / 功能模式名           │
    │   mode: str          # 前端传入的功能模式             │
    │                                                     │
    │ 教师输入参数 (前端表单)                                │
    │   lesson_subject      lesson_topic                   │
    │   lesson_grade         lesson_objectives              │
    │   key_points           difficult_points              │
    │   lesson_duration      style_preference              │
    │                                                     │
    │ 中间数据 (各功能节点写入的 JSON)                       │
    │   _lesson_plan_json     _classroom_sim_json           │
    │   _blind_spot_json      _student_sim_json            │
    │   _interaction_json     _exam_json                   │
    │   _ppt_outline_json                                  │
    │                                                     │
    │ RAG                                                   │
    │   knowledge_base_id    _knowledge_context             │
    │                                                     │
    │ 输出                                                 │
    │   final_output: str    # 最终 Markdown                │
    └─────────────────────────────────────────────────────┘
    """

class WorkflowMode:
    """工作流模式枚举 — 8 种模式"""
    LESSON_PREP        = "lesson_prep"         # 📋 教案生成
    CLASSROOM_SIM      = "classroom_sim"       # 🎭 课堂预演
    BLIND_SPOT         = "blind_spot"          # 🔍 盲区检测
    STUDENT_SIM        = "student_sim"         # 👥 学情推演
    INTERACTION_DESIGN = "interaction_design"  # 💬 互动设计
    EXAM_GEN           = "exam_gen"            # 📝 智能命题
    PPT_GEN            = "ppt_gen"             # 📊 PPT 大纲
    CHAT               = "chat"               # 🗨️ 自由对话
```

**关键设计**:
- `total=False` — 所有字段可选，节点只需返回自己关心的字段
- `messages` 使用 `Annotated[list, add_messages]` — LangGraph 自动累加，不会覆盖
- `_xxx_json` 前缀 — 中间 JSON 数据，供 `format_output` 消费
- `_knowledge_context` — RAG 节点写入，所有功能节点 System Prompt 中注入

#### 3.2.3 多功能工作流 (`lesson_prep.py`)

**文件**: `src/graphs/lesson_prep.py`（1500 行）— 唯一活跃的 StateGraph。

##### 工作流拓扑

```
SET_ENTRY: intent_router
    │
    ▼
intent_router ────→ rag_enrich
                      │
     ┌────────────────┼────────────────┬────────────┬────────────┬────────────┬────────────┐
     ▼                ▼                ▼            ▼            ▼            ▼            ▼
chat_reply    generate_lesson   simulate_     detect_      simulate_    design_      generate_
                   _plan        classroom    blindspots    students   interactions    exam
     │                │                │            │            │            │            │
     │                │                │            │            │            │      ┌─────┘
     └────────────────┴────────────────┴────────────┴────────────┴────────────┘     ▼
                                           │                                   generate_ppt
                                           ▼                                        │
                                     format_output ←────────────────────────────────┘
                                           │
                                           ▼
                                          END
```

##### 节点 1: `intent_router` — 意图路由

```python
def node_intent_router(state: LessonPrepState) -> dict:
    """
    路由策略:
    1. 前端传入 mode → 直接使用（第一优先级）
    2. 无 mode 但有 lesson_subject/lesson_topic → lesson_prep
    3. 消息含"备课""教案"关键词 → lesson_prep
    4. 以上都不满足 → chat
    """
    mode = state.get("mode", "")

    if not mode:
        if state.get("lesson_subject") or state.get("lesson_topic"):
            mode = WorkflowMode.LESSON_PREP
        else:
            # 关键词降级
            user_input = last_message_content(state).lower()
            prep_keywords = ["备课", "教案", "教学设计", "课程设计"]
            mode = WorkflowMode.LESSON_PREP if any(kw in user_input for kw in prep_keywords) else WorkflowMode.CHAT

    return {"intent": mode if mode != WorkflowMode.CHAT else "chat", "mode": mode}
```

##### 节点 2: `rag_enrich` — RAG 上下文增强

```python
def node_rag_enrich(state: LessonPrepState) -> dict:
    """
    通用 RAG 增强层 — 所有功能模式共享。

    流程:
    1. 无 knowledge_base_id → 跳过，返回空上下文
    2. 组合查询: 用户最新消息 + lesson_topic
    3. 调用 knowledge.embedder.retrieve_context(query, kb_id, top_k=3)
    4. 拼接为上下文文本，注入后续节点的 System Prompt
    """
    kb_id = state.get("knowledge_base_id", "")
    if not kb_id:
        return {"_knowledge_context": ""}

    # 构图检索查询
    query = build_query(state)  # 最新消息 + 课题
    results = retrieve_context(query, kb_id, top_k=3)

    # 拼接上下文
    context = "\n\n".join(f"【片段 {i}】\n{r['content']}" for i, r in enumerate(results, 1))
    return {"_knowledge_context": context}
```

**RAG 上下文注入模板**（追加到每个功能节点的 System Prompt 末尾）:

```
【参考资料（来自知识库）】
{context}

请参考以上资料，确保生成内容与知识库中的信息一致。
如果知识库内容与你的专业知识有冲突，以知识库为准并标注。
```

##### 路由分发（`route_intent`）

```python
# 路由映射 — 条件边的路径表
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
    """条件边: 根据 intent 分流到对应功能节点"""
    return MODE_NODE_MAP.get(state.get("intent", "chat"), "chat_reply")
```

##### 节点 3-10: 功能生成节点（统一模式）

每个功能节点遵循相同的实现模式：

```
┌─────────────────────────────────────────────────────────┐
│  1. 创建请求上下文 (new_context)                          │
│  2. 创建 LLMClient (扣子 SDK)                            │
│  3. 提取教师参数 (_extract_teacher_params)               │
│  4. 构建 System Prompt (含 RAG 上下文注入)                │
│  5. 构建 User Message (_build_user_content)              │
│  6. LLM 调用 client.invoke(messages, **llm_params)      │
│  7. JSON 解析 parse_json(response) + 容错                │
│  8. 写入 state: {"_xxx_json": json.dumps(result)}        │
└─────────────────────────────────────────────────────────┘
```

**LLM 参数分配**:

| 节点 | preset | 模型 | temperature | max_tokens |
|------|--------|------|-------------|------------|
| chat_reply | `chat` | lite | 0.7 | 500 |
| generate_lesson_plan | `creative` | pro | 0.7 | 8000 |
| simulate_classroom | `creative` | pro | 0.7 | 8000 |
| detect_blindspots | `precise` | lite | 0.3 | 2000 |
| simulate_students | `creative` | pro | 0.7 | 8000 |
| design_interactions | `creative` | pro | 0.7 | 8000 |
| generate_exam | `creative` | pro | 0.7 | 8000 |
| generate_ppt | `creative` | pro | 0.7 | 8000 |

**教师参数提取**:

```python
def _extract_teacher_params(state: LessonPrepState) -> dict:
    """从 state 中提取教师输入参数，构建统一的参数字典"""
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
```

**各功能节点的 System Prompt 输出结构**:

| 节点 | LLM 输出结构 |
|------|------------|
| `generate_lesson_plan` | `{title, subject, grade, standards, objectives(三层), key_difficulties, teaching_process(4+环节), board_design, exercises(三层), homework(三层), reflection_prompts}` |
| `simulate_classroom` | `{scenarios(4+种情境: 名称/触发点/概率/学生表现/教师风险/应对策略/预防措施), time_risk, overall_risk_level, key_reminder}` |
| `detect_blindspots` | `{blindspots(4+个: 类型/位置/描述/风险/影响/建议), overall_assessment, priority_fix}` |
| `simulate_students` | `{student_profiles(优等生/中等生/学困生: 思维路径/卡点/脚手架/替代路径), classroom_dynamics, key_insight}` |
| `design_interactions` | `{interactions(4+环节: 提问/小组活动/即时评估/过渡话术), icebreaker, overall_tips}` |
| `generate_exam` | `{exam_meta(总分/时长/难度比例), questions(选择题/填空/判断/简答/应用题), difficulty_summary, exam_tips}` |
| `generate_ppt` | `{title, slides(12-20页: 标题/版式/要点/内容概要/视觉建议/讲解提示), design_notes}` |

##### 节点 11: `format_output` — 多模式格式化输出

```python
def node_format_output(state: LessonPrepState) -> dict:
    """
    统一格式化输出 — 根据 intent 选择不同的格式化器。

    闲聊 (chat): 直接返回（chat_reply 已通过 messages 流式推送文本）
    功能模式: JSON → Markdown 转换

    格式化器注册表:
    """
    FORMATTERS = {
        WorkflowMode.LESSON_PREP:        _format_lesson_plan,       # 教案 → 结构化 Markdown
        WorkflowMode.CLASSROOM_SIM:      _format_classroom_sim,     # 预演 → 情境卡片
        WorkflowMode.BLIND_SPOT:         _format_blind_spot,        # 盲区 → 风险清单
        WorkflowMode.STUDENT_SIM:        _format_student_sim,       # 推演 → 学生画像
        WorkflowMode.INTERACTION_DESIGN: _format_interaction_design, # 互动 → 方案详情
        WorkflowMode.EXAM_GEN:           _format_exam,              # 命题 → 试卷格式
        WorkflowMode.PPT_GEN:            _format_ppt_outline,       # PPT → 幻灯片大纲
    }
```

**格式化器的核心能力**:
- JSON dict 递归展开 → Markdown 层级标题
- 字段名中文化（`FIELD_NAMES` 映射表，296 个键）
- 列表 → 编号/项目符号列表
- 嵌套对象 → 子标题 + 缩进
- 风险等级 → Emoji 标注（🔴🟡🟢）
- 难度标签 → 颜色标记（🟢基础 🟡提高 🔴挑战）
- RAG 引用 → 末尾来源标注

##### 图构建代码

```python
def build_lesson_prep_graph() -> StateGraph:
    """构建多功能工作流图"""
    builder = StateGraph(LessonPrepState)

    # 注册全部 11 个节点（条件路由，每次请求仅执行单一功能节点）
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

    # 入口
    builder.set_entry_point("intent_router")

    # intent_router → rag_enrich (所有请求统一经过 RAG 增强层)
    builder.add_edge("intent_router", "rag_enrich")

    # rag_enrich → 条件路由到各功能节点
    route_map = {name: name for name in MODE_NODE_MAP.values()}
    builder.add_conditional_edges("rag_enrich", route_intent, route_map)

    # 所有功能节点 → format_output → END
    for node_name in MODE_NODE_MAP.values():
        builder.add_edge(node_name, "format_output")
    builder.add_edge("format_output", END)

    return builder
```

### 3.3 知识库系统 (`knowledge/`)

完整的 RAG 管道，支持从文档上传到语义检索的全流程。

#### 3.3.1 处理管道

```
文件上传
  │
  ▼
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ 文档解析  │ → │ 文本分块  │ → │ 向量化    │ → │ 向量存储  │
│ parser   │   │ chunker  │   │ embedder │   │ vector   │
│          │   │          │   │          │   │ store    │
│ PDF      │   │ 段落感知  │   │ Embedding│   │ 内存存储  │
│ Word     │   │ 滑动窗口  │   │ Client   │   │ + 持久化  │
│ Excel    │   │ ≤500字/块│   │ 10条/批  │   │ JSON文件  │
│ PPT      │   │ 50字重叠  │   │          │   │          │
│ TXT/MD   │   │ ≤200块   │   │          │   │          │
└──────────┘   └──────────┘   └──────────┘   └──────────┘

检索流程
  │
  ▼
┌──────────┐   ┌──────────┐   ┌──────────────────────────┐
│ Query    │ → │ 余弦相似度 │ → │ [(content, meta, score)] │
│ 向量化    │   │ Top-K 检索 │   │                          │
└──────────┘   └──────────┘   └──────────────────────────┘
```

#### 3.3.2 文档解析器 (`parser.py`)

| 格式 | 解析库 | 方法 |
|------|--------|------|
| PDF | `pypdf` | `PdfReader.pages[].extract_text()` |
| Word | `docx2python` | 递归提取 body 文本 |
| Excel | `openpyxl` | `load_workbook(read_only=True)` 逐行读取 |
| PPT | `python-pptx` | 遍历 slides → shapes → paragraphs |
| TXT/MD | 内置 | UTF-8 解码 |

#### 3.3.3 文本分块器 (`chunker.py`)

```python
DEFAULT_CHUNK_SIZE = 500      # 每块最大字符数
DEFAULT_CHUNK_OVERLAP = 50    # 相邻块重叠字符数
DEFAULT_MAX_CHUNKS = 200      # 单文档最大分块数

def split_into_chunks(text) -> List[dict]:
    """
    分块策略:
    1. 按双换行 (\n\n) 预切分为段落
    2. 段落 ≤ chunk_size → 合并
    3. 单段落 > chunk_size → 按中文标点 (。！？；) 再切分
    4. 相邻块保留 chunk_overlap 字符重叠
    5. 总块数截断到 max_chunks
    """
```

#### 3.3.4 向量化与检索 (`embedder.py`)

```python
def embed_and_store(kb_id, doc_id, chunks) -> int:
    """将 chunks 向量化并存入 VectorStore"""
    embedder = EmbeddingClient()       # 扣子 SDK
    store = get_vector_store()         # InMemoryVectorStore
    # 每批 10 条，逐个向量化 + 存储

def retrieve_context(query, kb_id, top_k=3) -> List[dict]:
    """语义检索"""
    query_vec = embedder.embed_text(query)
    results = store.search(query_vec, kb_id=kb_id, top_k=top_k)
    # 返回 [{"content": str, "score": float, "doc_id": str, "chunk_index": int}]
```

#### 3.3.5 向量存储 (`vector_store.py`)

```python
class InMemoryVectorStore(VectorStore):
    """
    内存向量存储 — 开发/预览环境方案

    实现细节:
    - 向量以 numpy array 存储在内存 dict (chunk_id → {embedding, metadata, content, kb_id})
    - 检索: numpy 余弦相似度 (np.dot / (norm1 * norm2))
    - 持久化: 序列化为 JSON → .knowledge_vectors/vectors.json
    - 重启后: 从 JSON 文件反序列化加载
    - 适用规模: < 10k chunks
    """
```

#### 3.3.6 元数据管理 (`store.py`)

使用 JSON 文件（`.knowledge_meta/knowledge_bases.json`）管理：

- **知识库 CRUD**: 创建/列表/获取/删除（含向量级联删除）
- **文档 CRUD**: 添加/列表/删除（含向量级联删除）
- **状态追踪**: `processing` → `ready`
- **chunk 计数**: 自动汇总

---

### 3.4 存储层 (`storage/`)

#### 3.4.1 数据库引擎 (`db.py`)

```
连接获取优先级链:
  1. PGDATABASE_URL 环境变量
  2. coze_workload_identity.Client().get_project_env_vars() 平台注入
  3. DEV_MODE=1 → SQLite 降级 (/tmp/vibe_coding_dev.db)
  4. 以上均无 → ValueError
```

```python
def _create_engine_with_retry():
    url = get_db_url()
    if not url and is_dev_env():
        return _create_sqlite_fallback()

    engine = create_engine(
        url,
        pool_size=100,          # 连接池大小
        max_overflow=100,       # 溢出连接数
        pool_pre_ping=True,     # 连接前自动检测有效性
        pool_recycle=1800,      # 30 分钟回收
        pool_timeout=30,        # 获取连接超时
    )

    # 带重试的连接验证 (最多 20 秒)
    while elapsed < 20:
        conn.execute("SELECT 1") → return engine
```

#### 3.4.2 状态检查点 (`memory_saver.py`)

LangGraph 状态持久化 — 跨请求对话记忆。

```python
class MemoryManager:
    """单例管理 checkpointer 生命周期"""

    def get_checkpointer(self) -> BaseCheckpointSaver:
        """
        降级链: AsyncPostgresSaver → MemorySaver

        1. 获取 db_url
        2. 连接 PostgreSQL → CREATE SCHEMA IF NOT EXISTS memory
        3. PostgresSaver(conn).setup()  # 自动建表
        4. 创建 AsyncConnectionPool + AsyncPostgresSaver
        5. 任何步骤失败 → MemorySaver (内存存储，重启丢失)
        """
```

**重试机制**: 2 次尝试，每次 15 秒连接超时，间隔 1 秒。

#### 3.4.3 S3 对象存储 (`s3_storage.py`)

完整的 S3 兼容存储实现（420 行），能力清单：

| 方法 | 功能 | 关键参数 |
|------|------|---------|
| `upload_file()` | 单文件上传 | 自动生成唯一 Key |
| `stream_upload_file()` | 流式分片上传 | `multipart_chunksize=5MB` |
| `trunk_upload_file()` | 字节迭代器上传 | 显式 Multipart Upload |
| `upload_from_url()` | 远程 URL 上传 | `timeout=30s` |
| `read_file()` | 下载为 bytes | — |
| `delete_file()` | 删除对象 | — |
| `list_files()` | 前缀过滤 + 分页 | `max_keys≤1000` |
| `file_exists()` | Head 检查 | — |
| `generate_presigned_url()` | 临时签名 URL | 默认 30 分钟有效期 |

**安全机制**:
- `before-call.s3` 事件钩子自动注入 `x-storage-token`
- `coze_workload_identity` 自动获取访问令牌
- 文件名校验（长度≤1024 / 允许字符集 / 路径格式）

---

### 3.5 配置与工具 (`config/` `utils/` `tools/`)

#### 3.5.1 LLM 配置 (`config/llm_config.py`)

3 种参数预设模板：

```python
class ModelName:
    PRO  = "doubao-seed-2-0-pro-260215"   # 旗舰模型
    LITE = "doubao-seed-2-0-lite-260215"  # 轻量模型

LLM_PRESETS = {
    "precise":  {"model": LITE, "temperature": 0.3, "max_completion_tokens": 2000},
    "creative": {"model": PRO,  "temperature": 0.7, "max_completion_tokens": 8000},
    "chat":     {"model": LITE, "temperature": 0.7, "max_completion_tokens": 500},
}
```

| 预设 | 模型 | temperature | max_tokens | 适用场景 |
|------|------|-------------|------------|---------|
| `precise` | lite | 0.3 | 2000 | 结构化提取（盲区检测） |
| `creative` | pro | 0.7 | 8000 | 创意生成（教案/推演/命题/PPT） |
| `chat` | lite | 0.7 | 500 | 闲聊对话 |

```python
def get_llm_params(preset="creative", temperature=None, max_tokens=None, model=None):
    """获取 LLM 参数，支持字段级覆盖"""
```

#### 3.5.2 JSON 解析工具 (`utils/json_parser.py`)

统一的容错 JSON 解析入口，消除分散的 try/except：

```python
def parse_json(content, default=None, log_context=""):
    """
    安全解析 JSON 字符串 — 统一容错入口。

    处理流程:
    1. extract_text_from_response() — 兼容 response.content 是 str/list[dict]
    2. clean_markdown_code_block() — 移除 ```json ... ``` 包裹
    3. json.loads() — 解析
    4. 失败 → 返回 default + 记录警告日志
    """
```

#### 3.5.3 工具集 (`tools/utility_tools.py`)

```python
# 提示词管理
load_prompt(prompt_name)          # 加载提示词模板文件（支持缓存 + 回退）
format_prompt(prompt_name, **kw)  # 格式化提示词（变量填充）

# RAG 检索
kb_search(query, kb_type)         # 单知识库检索（4级优先级: 课标→教材→教法→个人）
kb_multi_search(query)            # 多知识库并发检索
merge_kb_results(results)         # 合并多库结果

# 格式化辅助
format_risk_badge(level)          # 风险等级徽章 (🔴🟡🟢)
format_error_tier(tier)           # 错因层级标签 (L1/L2/L3)
format_radar_chart_text(dims)     # ASCII 艺术风格雷达图
format_student_name(index, tier)  # 化名学生姓名
```

---

### 3.6 API 路由 (`api/`)

#### 3.6.1 知识库 API (`api/knowledge.py`)

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/knowledge-bases` | GET | 列出所有知识库 |
| `/api/knowledge-bases` | POST | 创建知识库（`name` + `description`） |
| `/api/knowledge-bases/{kb_id}` | DELETE | 删除知识库（含向量级联清理） |
| `/api/knowledge-bases/{kb_id}/documents` | GET | 列出知识库文档 |
| `/api/knowledge-bases/{kb_id}/upload` | POST | 上传文档 → 自动解析→分块→向量化 |
| `/api/knowledge-bases/{kb_id}/documents/{doc_id}` | DELETE | 删除文档（含向量级联清理） |
| `/api/knowledge-bases/{kb_id}/search` | POST | 语义检索（`query` + `top_k`） |

**上传流程**: 文件校验 → `extract_text()` → `split_into_chunks()` → `add_document(status="processing")` → `embed_and_store()` → `update_document_status("ready")`

---

## 4. API 接口规范

### 4.1 OpenAI 兼容接口

```bash
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "jiao-si",
  "messages": [
    {"role": "user", "content": "帮我备一节初三数学二次函数的课"}
  ],
  "stream": false,
  "session_id": "optional-session-id",
  "extra_body": {
    "mode": "lesson_prep",
    "lesson_subject": "数学",
    "lesson_grade": "初三",
    "lesson_topic": "二次函数",
    "lesson_duration": 45,
    "style_preference": "启发式互动型",
    "lesson_objectives": "掌握二次函数图像性质",
    "key_points": "二次函数顶点式与图像变换",
    "difficult_points": "参数a,b,c对图像的影响",
    "knowledge_base_id": "kb-xxx"
  }
}
```

**extra_body 参数**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `mode` | string | 功能模式（不传则后端自动识别） |
| `lesson_subject` | string | 学科 |
| `lesson_grade` | string | 年级 |
| `lesson_topic` | string | 课题名称 |
| `lesson_objectives` | string | 教学目标 |
| `key_points` | string | 教学重点 |
| `difficult_points` | string | 教学难点 |
| `lesson_duration` | int | 课时时长（分钟），默认 45 |
| `style_preference` | string | 教学风格 |
| `knowledge_base_id` | string | 知识库 ID（RAG 增强） |

**非流式响应**:

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "jiao-si",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "# 📋 二次函数\n\n## 课题信息\n..."
    },
    "finish_reason": "stop"
  }]
}
```

**流式响应 (SSE)**:

```
event: node_progress
data: {"node":"intent_router","progress_id":"intent","status":"completed"}

event: node_progress
data: {"node":"generate_lesson_plan","progress_id":"generating","status":"completed"}

event: node_progress
data: {"node":"format_output","progress_id":"formatting","status":"completed"}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"delta":{"role":"assistant"},"index":0}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"delta":{"content":"# 📋 二次函数\n\n..."},"index":0}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"delta":{},"finish_reason":"stop","index":0}]}

data: [DONE]
```

### 4.2 教师配置 API

```bash
GET /api/teacher-config
```

返回前端表单所需的所有下拉选项：

```json
{
  "subjects": ["语文","数学","英语","物理","化学","生物","历史","地理","政治","体育","音乐","美术","信息技术"],
  "grades": ["一年级","二年级","三年级","四年级","五年级","六年级","初一","初二","初三","高一","高二","高三"],
  "objectives": ["知识与技能","过程与方法","情感态度与价值观","核心素养导向","综合能力培养"],
  "key_points": ["概念理解","公式推导","方法掌握","技能训练","思维培养","知识应用"],
  "difficult_points": ["抽象概念理解","复杂计算","逻辑推理","知识迁移","综合应用","创新思维"],
  "durations": [20,30,40,45,60,90],
  "styles": ["启发式互动型","系统讲授型","情感体验型","任务驱动型","混合型"],
  "modes": [
    {"id":"lesson_prep","name":"教案生成","icon":"📋","desc":"生成完整结构化教案"},
    {"id":"classroom_sim","name":"课堂预演","icon":"🎭","desc":"预判课堂意外情境与应对"},
    {"id":"blind_spot","name":"盲区检测","icon":"🔍","desc":"发现教案中的逻辑漏洞"},
    {"id":"student_sim","name":"学情推演","icon":"👥","desc":"模拟不同学生的思维路径"},
    {"id":"interaction_design","name":"互动设计","icon":"💬","desc":"设计师生互动方案和话术"},
    {"id":"exam_gen","name":"智能命题","icon":"📝","desc":"一键生成结构化试题"},
    {"id":"ppt_gen","name":"PPT大纲","icon":"📊","desc":"一键生成PPT课件大纲"},
    {"id":"chat","name":"自由对话","icon":"🗨️","desc":"闲聊或提问"}
  ]
}
```

---

## 5. 运行与部署

### 5.1 本地开发

```bash
cd projects
bash scripts/setup.sh                  # uv sync 安装依赖
export DEV_MODE=1                      # 启用数据库降级
source .venv/bin/activate
python src/main.py -m http -p 5000

# 验证
curl http://localhost:5000/health      # → {"status":"ok"}

# 命令行模式测试
python src/main.py -m flow -i '{
  "messages":[{"role":"user","content":"帮我备一节数学课"}],
  "lesson_subject":"数学","lesson_topic":"二次函数","lesson_grade":"初三"
}'
```

### 5.2 平台预览

点击平台「预览」按钮，自动执行：

```toml
[dev]
build = ["bash", "scripts/setup.sh"]     # uv sync
run   = ["bash", "scripts/http_run.sh"]   # 启动 HTTP 服务
```

`http_run.sh` 自动处理：检测部署环境、设置 `DEV_MODE=1`、清理端口残留、激活虚拟环境。

### 5.3 生产部署

```bash
# 生产环境需配置 PostgreSQL
export PGDATABASE_URL="postgresql://user:pass@host:5432/dbname"

# 可选 S3 存储
export COZE_BUCKET_ENDPOINT_URL="https://s3.example.com"
export COZE_BUCKET_NAME="jiao-si-storage"
```

### 5.4 关键环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `PGDATABASE_URL` | PostgreSQL 连接串 | 生产必填 |
| `DEV_MODE` | 设为 `1` 启用 SQLite + MemorySaver 降级 | 开发用 |
| `COZE_PROJECT_ENV` | 项目环境标识 (`DEV`/`PROD`) | 平台注入 |
| `COZE_WORKSPACE_PATH` | 工作空间路径 | 平台注入 |
| `COZE_BUCKET_ENDPOINT_URL` | S3 存储端点 | 选填 |
| `COZE_BUCKET_NAME` | S3 Bucket | 选填 |
| `COZE_LOOP_API_TOKEN` | Coze 工作流 API Token | PPT 生成需要 |
| `DEPLOY_RUN_PORT` | HTTP 服务端口，默认 5000 | 选填 |

### 5.5 降级方案

`DEV_MODE=1` 时自动启用：

| 组件 | 生产环境 | 开发降级 | 影响 |
|------|---------|---------|------|
| 数据库引擎 | PostgreSQL | SQLite (`/tmp/vibe_coding_dev.db`) | 数据不跨会话持久化 |
| 状态检查点 | AsyncPostgresSaver | MemorySaver | 重启后对话历史丢失 |
| 向量存储 | (可替换为 pgvector) | InMemoryVectorStore | < 10k chunks，JSON 文件持久化 |
| LLM 调用 | 扣子平台 API | 同生产 | 无影响 |

---

## 6. 技术栈清单

### 核心框架

| 技术 | 版本 | 用途 |
|------|------|------|
| **Python** | ≥3.12 | 主语言 |
| **FastAPI** | ≥0.121 | HTTP 路由、中间件、OpenAPI 文档 |
| **Uvicorn** | ≥0.38 | ASGI 异步 HTTP 服务器 |
| **LangGraph** | 1.0.2 | StateGraph 工作流编排、条件路由 |
| **LangChain** | 1.0.3 | 消息类型 (SystemMessage/HumanMessage/AIMessage) |
| **coze-coding-dev-sdk** | >0.5.0 | LLM Client + Embedding Client |
| **coze-coding-utils** | 0.2.8 | GraphService、OpenAI 适配、流式处理、日志 |
| **coze-workload-identity** | ≥0.1.4 | Workload Identity 令牌获取 |

### 数据层

| 技术 | 版本 | 用途 |
|------|------|------|
| **SQLAlchemy** | ≥2.0 | ORM + 连接池 |
| **PostgreSQL** | 16+ | 生产数据库 |
| **SQLite** | 3.x | 开发降级 |
| **langgraph-checkpoint-postgres** | ≥3.0 | LangGraph 状态 PG 持久化 |
| **psycopg[binary]** | ≥3.3 | PostgreSQL 异步驱动 |
| **psycopg-pool** | ≥3.3 | PostgreSQL 异步连接池 |
| **boto3** | ≥1.40 | S3 兼容对象存储 |
| **Pydantic** | ≥2.12 | 数据验证 |

### 知识库与文档

| 技术 | 版本 | 用途 |
|------|------|------|
| **pypdf** | ≥6.4 | PDF 文本提取 |
| **docx2python** | ≥3.5 | Word 文档解析 |
| **openpyxl** | ≥3.1 | Excel 数据读取 |
| **python-pptx** | ≥1.0 | PPT 文本提取 |
| **numpy** | — | 余弦相似度向量检索 |
| **chardet** | ≥5.2 | 文件编码检测 |

### 前端

| 技术 | 说明 |
|------|------|
| **原生 HTML/CSS/JS** | 零构建依赖，单文件部署 |
| **marked.js** 15+ (CDN) | Markdown → HTML |
| **highlight.js** 11+ (CDN) | 代码语法着色 |

### 开发与部署

| 技术 | 版本 | 用途 |
|------|------|------|
| **uv** | 0.5+ | Python 包管理 |
| **python-dotenv** | ≥1.2 | .env 加载 |
| **Jinja2** | ≥3.1 | 模板引擎（预留） |
| **alembic** | ≥1.16 | 数据库迁移（预留） |

---

## 7. 开发指南

### 7.1 添加新的功能模式

1. **在 `state.py` 中定义中间数据字段**:
```python
class LessonPrepState(TypedDict, total=False):
    _new_feature_json: str  # 功能节点写入的中间 JSON
```

2. **在 `lesson_prep.py` 中添加 System Prompt + 生成节点**:
```python
NEW_FEATURE_SYSTEM_PROMPT = """你是...严格按以下 JSON 结构输出..."""

def node_generate_new_feature(state: LessonPrepState) -> dict:
    ctx = request_context.get() or new_context(method="new_feature.generate")
    client = LLMClient(ctx=ctx)
    params = _extract_teacher_params(state)
    # RAG 上下文注入
    system_prompt = NEW_FEATURE_SYSTEM_PROMPT
    if state.get("_knowledge_context"):
        system_prompt += KNOWLEDGE_CONTEXT_TEMPLATE.format(context=state["_knowledge_context"])
    # LLM 调用 + JSON 解析
    response = client.invoke(...)
    result = parse_json(response, ...)
    return {"_new_feature_json": json.dumps(result, ensure_ascii=False)}
```

3. **添加 Markdown 格式化器**:
```python
def _format_new_feature(data: dict) -> str:
    md = []
    # JSON → Markdown 递归转换
    return "\n".join(md)
```

4. **注册到三张映射表**:
```python
MODE_NODE_MAP["new_feature"] = "generate_new_feature"
FORMATTERS["new_feature"] = _format_new_feature
MODE_DATA_FIELD["new_feature"] = "_new_feature_json"
```

5. **在 `build_lesson_prep_graph()` 中注册节点和边**:
```python
builder.add_node("generate_new_feature", node_generate_new_feature)
builder.add_edge("generate_new_feature", "format_output")
```

6. **在 `state.py` 的 `WorkflowMode` 中添加常量，在 `main.py` 的 `TEACHER_CONFIG["modes"]` 中添加前端入口**。

### 7.2 扩展向量存储

实现 `VectorStore` 抽象接口即可替换实现：

```python
class PgVectorStore(VectorStore):
    def add_vectors(self, ids, embeddings, metadatas, contents, kb_id):
        # INSERT INTO vectors ...
    def search(self, query_embedding, kb_id, top_k):
        # SELECT ... ORDER BY embedding <=> $1 LIMIT top_k
    def delete_by_kb(self, kb_id): ...
    def delete_by_doc(self, kb_id, doc_id): ...
    def count(self, kb_id): ...

# 替换全局实例
def get_vector_store():
    return PgVectorStore()
```

### 7.3 编码规范

| 规范 | 说明 |
|------|------|
| Python | PEP 8，4 空格缩进 |
| 节点函数 | `node_<功能描述>`，如 `node_generate_lesson_plan` |
| 格式化器 | `_format_<模式名>`，如 `_format_lesson_plan` |
| 图构建 | `build_<场景>_graph()`，如 `build_lesson_prep_graph` |
| JSON 解析 | 统一使用 `parse_json()`，不手写 try/except |
| State 更新 | 通过 `return {"field": value}` 机制 |
| 日志格式 | `[模块-节点] 描述`，如 `[教案生成] 开始` |

### 7.4 调试

```bash
# 单节点调试
curl -X POST http://localhost:5000/node_run/generate_lesson_plan \
  -H "Content-Type: application/json" \
  -d '{"session_id":"debug","lesson_subject":"数学","lesson_topic":"二次函数","lesson_grade":"初三"}'

# 查看工作流结构
curl http://localhost:5000/graph_parameter

# 命令行完整运行
python src/main.py -m flow -i '{"messages":[{"role":"user","content":"你好"}]}'
```

---

<div align="center">

**「教思」— 教之以思，而非教之以器**

</div>
