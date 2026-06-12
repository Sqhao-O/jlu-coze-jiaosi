# 「教思」AI 教学孪生系统

> 基于 LangGraph 多智能体工作流的 AI 教学辅助平台，覆盖智能备课、教学推演、成长分析三大核心场景。

---

## 目录

1. [系统架构](#1-系统架构)
2. [技术栈](#2-技术栈)
3. [目录结构](#3-目录结构)
4. [核心模块实现](#4-核心模块实现)
   - [4.1 HTTP 服务层 (`main.py`)](#41-http-服务层-mainpy)
   - [4.2 全局状态定义 (`graphs/state.py`)](#42-全局状态定义-graphsstatepy)
   - [4.3 工作流路由 (`graphs/graph.py`)](#43-工作流路由-graphsgraphpy)
   - [4.4 智能备课 (`graphs/lesson_prep.py`)](#44-智能备课-graphslesson_preppy)
   - [4.5 教学推演 (`graphs/teaching_simulation.py`)](#45-教学推演-graphsteaching_simulationpy)
   - [4.6 成长分析 (`graphs/growth_analysis.py`)](#46-成长分析-graphsgrowth_analysispy)
   - [4.7 主控 Agent (`agents/agent.py`)](#47-主控-agent-agentsagentpy)
   - [4.8 存储层 (`storage/`)](#48-存储层-storage)
   - [4.9 JSON→Markdown 格式化引擎](#49-jsonmarkdown-格式化引擎)
   - [4.10 前端聊天界面 (`assets/index.html`)](#410-前端聊天界面-assetsindexhtml)
5. [API 接口规范](#5-api-接口规范)
6. [完整数据流](#6-完整数据流)
7. [运行与部署](#7-运行与部署)
8. [配置体系](#8-配置体系)
9. [开发降级方案](#9-开发降级方案)
10. [常见问题](#10-常见问题)

---

## 1. 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         用户交互层                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ 前端聊天界面  │  │ API 文档 /docs│  │ OpenAI 兼容接口 /v1/...  │ │
│  │ (HTML/CSS/JS)│  │ (Swagger UI) │  │ (第三方客户端接入)        │ │
│  └──────┬──────┘  └──────┬───────┘  └────────────┬─────────────┘ │
└─────────┼────────────────┼───────────────────────┼───────────────┘
          │                │                       │
          ▼                ▼                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                      HTTP 服务层 (FastAPI + Uvicorn)               │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  main.py                                                     │ │
│  │  ├─ GraphService: 工作流执行引擎 (run / stream_run / async)   │ │
│  │  ├─ OpenAIChatHandler: OpenAI 协议适配                       │ │
│  │  ├─ format_teaching_content(): JSON→Markdown 规则引擎         │ │
│  │  └─ 静态文件挂载: assets/index.html                          │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    工作流编排层 (LangGraph)                        │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐  │
│  │ 智能备课 (11节点) │ │ 教学推演 (12节点) │ │ 成长分析 (12节点) │  │
│  │ lesson_prep.py   │ │ teaching_        │ │ growth_analysis  │  │
│  │                  │ │ simulation.py    │ │ .py              │  │
│  └────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘  │
│           │                    │                    │             │
│           └────────────────────┼────────────────────┘             │
│                                ▼                                  │
│                    ┌──────────────────────┐                       │
│                    │   graphs/graph.py    │                       │
│                    │   工作流路由 + 图编译  │                       │
│                    └──────────────────────┘                       │
└──────────────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────────┐
│                     基础设施层                                     │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────────┐ │
│  │ LLM Client │ │ 状态管理    │ │ 存储层      │ │ 工具基础设施   │ │
│  │ (扣子SDK)  │ │ (StateGraph│ │ PostgreSQL  │ │ RAG检索       │ │
│  │            │ │  + 检查点)  │ │ / SQLite    │ │ 变量管理      │ │
│  └────────────┘ └────────────┘ └────────────┘ └───────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 架构设计原则

| 原则 | 实现 |
|------|------|
| **工作流即代码** | 每个教学场景封装为独立的 LangGraph StateGraph，节点函数纯 Python |
| **状态驱动** | 全局 `TeachingState` 通过 LangGraph 的 `TypedDict + Annotated` 机制在各节点间自动合并传递 |
| **协议兼容** | 通过 `OpenAIChatHandler` 将内部 LangGraph 流适配为 OpenAI `/v1/chat/completions` 格式 |
| **降级优先** | 开发环境自动降级（PostgreSQL→SQLite, PostgresSaver→MemorySaver），零配置启动 |

---

## 2. 技术栈

| 类别 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **语言** | Python | 3.12 | 主语言 |
| **Web 框架** | FastAPI | 0.115+ | HTTP 路由、中间件、OpenAPI 文档 |
| **ASGI 服务器** | Uvicorn | 0.34+ | 生产级异步 HTTP 服务 |
| **工作流引擎** | LangGraph | 0.6+ | StateGraph 有向图编排、条件路由、并行 Send |
| **LLM 调用** | coze-coding-dev-sdk | latest | 扣子平台 LLM Client，支持流式/非流式/思考模式 |
| **LLM 集成** | LangChain | 0.3+ | 消息类型（SystemMessage/HumanMessage）、工具定义 |
| **数据库 ORM** | SQLAlchemy | 2.0+ | 数据库引擎管理、连接池 |
| **数据库** | PostgreSQL / SQLite | 16+ / 3.x | 生产用 PG，开发降级 SQLite |
| **依赖管理** | uv | 0.5+ | Python 包管理、虚拟环境 |
| **前端渲染** | marked.js | 15+ | Markdown→HTML 解析 |
| **代码高亮** | highlight.js | 11+ | 代码块语法着色 |
| **前端** | 原生 HTML/CSS/JS | — | 零框架依赖，单文件 1500+ 行 |
| **序列化** | JSON | — | 工作流节点间数据交换格式 |
| **配置** | TOML | — | `.coze` 部署/预览配置 |

---

## 3. 目录结构

```
projects/                          # 技术项目根目录
├── .coze                          # 子项目配置（sub_id, name, project_type）
├── README.md                      # 本文档
├── pyproject.toml                 # Python 项目元数据 + 依赖声明
├── uv.lock                        # uv 依赖锁文件
│
├── src/                           # 源码根目录
│   ├── main.py                    # ★ HTTP 服务入口 + GraphService + 格式化引擎
│   │
│   ├── graphs/                    # LangGraph 工作流定义
│   │   ├── __init__.py            # 包初始化
│   │   ├── graph.py               # ★ 工作流路由：根据 workflow 参数分发到不同子图
│   │   ├── state.py               # ★ 全局状态定义（TeachingState + 3 个工作流 State）
│   │   ├── lesson_prep.py         # ★ 智能备课：11 节点 StateGraph
│   │   ├── teaching_simulation.py # ★ 教学推演：12 节点 + 3 路并行 Send
│   │   ├── growth_analysis.py     # ★ 成长分析：12 节点 StateGraph
│   │   └── nodes/                 # 共享节点函数（工具调用等）
│   │
│   ├── agents/                    # LangChain Agent 定义
│   │   └── agent.py               # 主控 Agent：意图识别 + 5 个教学 Tool
│   │
│   ├── tools/                     # 工具基础设施
│   │   └── utility_tools.py       # RAG 检索、变量管理、提示词加载
│   │
│   ├── storage/                   # 存储层
│   │   ├── database/
│   │   │   └── db.py              # 数据库引擎（PG 主 + SQLite 降级）
│   │   └── memory/
│   │       └── memory_saver.py    # 状态检查点（PostgresSaver + MemorySaver 降级）
│   │
│   └── utils/                     # 工具模块
│       ├── helper.py              # 运行配置辅助（init_run_config 等）
│       └── log/
│           ├── __init__.py
│           └── loop_trace.py      # Agent/Graph 配置初始化
│
├── assets/                        # 静态资源
│   └── index.html                 # ★ 前端聊天界面（1500+ 行单文件）
│
├── config/                        # 配置文件
│   ├── agent_llm_config.json      # LLM 模型配置（模型名、temperature、timeout）
│   └── prompts/                   # 提示词模板目录
│
└── scripts/                       # 运行脚本
    ├── setup.sh                   # 依赖安装（uv sync）
    └── http_run.sh                # ★ HTTP 服务启动（设置 DEV_MODE + 激活 venv）
```

---

## 4. 核心模块实现

### 4.1 HTTP 服务层 (`main.py`)

**文件**: `src/main.py`（约 950 行）

#### 4.1.1 GraphService 类

核心工作流执行引擎，封装 LangGraph 的调用生命周期：

```python
class GraphService:
    def __init__(self):
        self._graph = None           # 懒加载的 CompiledStateGraph
        self._checkpointer = None    # 状态检查点实例

    def _get_graph(self, ctx):
        """懒加载 + 缓存编译后的图"""
        if self._graph is None:
            raw_graph = Graph(workflow="lesson_prep").builder
            checkpointer = get_checkpointer()
            self._graph = raw_graph.compile(checkpointer=checkpointer)
        return self._graph

    async def run(self, payload, ctx):
        """同步执行：await graph.ainvoke()，返回完整结果"""
        ...

    async def stream_run(self, payload, ctx):
        """SSE 流式执行：async for chunk in graph.astream()"""
        ...

    async def async_run(self, payload, ctx):
        """异步执行：asyncio.create_task() + 返回 task_id"""
        ...
```

**三种执行模式对比**：

| 模式 | 方法 | 返回方式 | 适用场景 |
|------|------|---------|---------|
| 同步 | `run()` | 一次性返回完整 JSON | 批量处理、API 调用 |
| 流式 | `stream_run()` | SSE (text/event-stream) | 实时展示进度 |
| 异步 | `async_run()` | task_id + 轮询 `GET /task/{id}` | 长时间任务 |

#### 4.1.2 OpenAI 协议适配

```python
@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    # 1. 解析 OpenAI 格式请求体
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    session_id = body.get("session_id", str(uuid.uuid4()))

    # 2. 通过 OpenAIChatHandler 调用 LangGraph 工作流
    openai_handler = OpenAIChatHandler()
    result = openai_handler.handle(
        model=body.get("model", "test"),
        messages=messages,
        session_id=session_id,
        stream=stream,
    )

    # 3. 非流式响应：对 content 执行 JSON→Markdown 格式化
    if isinstance(result, JSONResponse):
        data = json.loads(result.body)
        for choice in data.get("choices", []):
            content = choice["message"]["content"]
            choice["message"]["content"] = format_teaching_content(content)
        return JSONResponse(content=data)

    return result  # 流式响应直接返回
```

**关键设计**：`OpenAIChatHandler.handle()` 内部调用 `graph.stream(stream_mode="messages")`，通过 `collect_langgraph_to_response()` 收集所有 AI 节点的文本输出，组装为 OpenAI 格式的 `JSONResponse`。

#### 4.1.3 路由表

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 返回前端聊天界面 (assets/index.html) |
| `/health` | GET | 健康检查 `{"status":"ok"}` |
| `/docs` | GET | Swagger UI API 文档 |
| `/openapi.json` | GET | OpenAPI 规范 JSON |
| `/v1/chat/completions` | POST | OpenAI 兼容对话接口 |
| `/run` | POST | 同步执行工作流 |
| `/stream_run` | POST | SSE 流式执行 |
| `/async_run` | POST | 异步执行（返回 task_id） |
| `/task/{task_id}` | GET | 查询异步任务状态 |
| `/graph_parameter` | GET | 获取工作流参数定义 |

---

### 4.2 全局状态定义 (`graphs/state.py`)

**文件**: `src/graphs/state.py`（约 160 行）

#### 4.2.1 状态体系

```
TeachingState (全局会话状态, 10 个字段)
├── subject, grade, grade_level          # 基础信息
├── teaching_style (TeachingStyle)       # 7 维风格向量
├── style_description                    # 风格自然语言描述
├── current_lesson_topic                 # 当前课题
├── lesson_plan_draft                    # 教案全文
├── simulation_result                    # 推演结果摘要
├── last_action                          # 最近操作
├── workflow_mode                        # 当前工作流
├── error_count, max_retries             # 重试控制
├── kb_results (KnowledgeBaseResults)    # KB 检索缓存
├── validation_errors, validation_passed # 质量校验
└── messages (Annotated[list, add_messages])  # LangGraph 消息累加器

    ├── LessonPrepState (继承)           # 备课专用字段
    │   ├── lesson_subject, lesson_topic, lesson_grade
    │   ├── kb_context, style_profile
    │   ├── teaching_objectives, key_difficult_points
    │   ├── teaching_process (list[dict])
    │   ├── board_design, tiered_exercises, homework_design
    │   └── final_lesson_plan
    │
    ├── SimulationState (继承)           # 推演专用字段
    │   ├── lesson_overview, stages
    │   ├── virtual_students (list[dict])
    │   ├── student_simulations (dict)
    │   ├── bottlenecks, risk_assessment
    │   └── optimized_plan, comparison_report
    │
    └── GrowthAnalysisState (继承)       # 成长分析专用字段
        ├── teaching_records, cleaned_data
        ├── five_dimension_scores (dict)
        ├── trends, attributions
        ├── key_events, achievements
        └── personalized_suggestions, growth_report
```

#### 4.2.2 7 维教学风格向量

```python
class TeachingStyle(TypedDict, total=False):
    compactness: float      # 紧凑度 (0-1): 内容密度和节奏
    interactivity: float    # 互动度 (0-1): 师生互动偏好
    depth: float            # 深度 (0-1): 概念深入挖掘偏好
    interest: float         # 趣味性 (0-1): 趣味元素使用倾向
    rigor: float            # 严谨度 (0-1): 学术规范要求
    innovation: float       # 创新度 (0-1): 新方法尝试意愿
    warmth: float           # 温度 (0-1): 情感关怀偏好
```

每个维度 0-1 连续值，由风格建模节点从教师历史数据中提取，驱动后续所有节点的个性化输出。

#### 4.2.3 用户变量（跨会话持久化）

```python
class UserProfile(TypedDict, total=False):
    teacher_name: str                # 教师姓名
    subjects_taught: list[str]       # 任教科目
    grade_taught: str                # 任教年级
    years_of_experience: int         # 教龄
    preferred_model: str             # 偏好模型: "pro"/"lite"
    # historical_lesson_plans: S3 key 列表
    # teaching_journal: 教学反思日志
    # growth_history: 五维成长历史快照
```

---

### 4.3 工作流路由 (`graphs/graph.py`)

**文件**: `src/graphs/graph.py`（约 25 行）

```python
class Graph:
    def __init__(self, workflow: str = "lesson_prep"):
        self.workflow = workflow
        self.builder = self._build()

    def _build(self):
        if self.workflow == "lesson_prep":
            return build_lesson_prep_graph()      # → lesson_prep.py
        elif self.workflow == "simulation":
            return build_simulation_graph()        # → teaching_simulation.py
        elif self.workflow == "growth":
            return build_growth_analysis_graph()   # → growth_analysis.py
        else:
            raise ValueError(f"Unknown workflow: {self.workflow}")
```

`graph_helper.get_graph_instance()` 从 `graphs.graph` 模块中查找 `Graph` 类实例，调用 `graph.builder.compile(checkpointer=...)` 编译为 `CompiledStateGraph`。

---

### 4.4 智能备课 (`graphs/lesson_prep.py`)

**文件**: `src/graphs/lesson_prep.py`（约 1100 行）

#### 4.4.1 工作流拓扑

```
用户输入
   │
   ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点1: node_parse_requirements()                              │
│   LLM: doubao-seed-2-0-lite | temperature=0.3 | max_tokens=1000│
│   输入: messages[-1] + state 已有字段                          │
│   输出: {"subject":"数学","topic":"二次函数","grade":"初三"...} │
│   写入: state.subject, state.lesson_topic, state.lesson_hours  │
└────────┬─────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点2: node_kb_retrieval()                                    │
│   LLM: doubao-seed-2-0-pro | temperature=0.5 | max_tokens=6000│
│   并行检索 4 个知识库:                                         │
│     KB1 课程标准库 → 核心素养框架 + 学段能力要求                │
│     KB2 教材教参库 → 教材定位 + 教学目标 + 学生困惑             │
│     KB3 教学法库   → 通用教学策略 + 活动设计 + 差异化建议        │
│     KB4 教师个人库 → 风格特征 + 有效策略 + 偏好活动              │
│   输出: 融合后的 kb_context (Markdown)                         │
└────────┬─────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点3: node_style_modeling()                                  │
│   LLM: doubao-seed-2-0-pro | temperature=0.5 | max_tokens=4000│
│   输入: kb_context + 教师历史数据                              │
│   输出: {"7维教学风格向量":{...},"风格描述":"该教师为混合型..."} │
│   写入: state.teaching_style, state.style_description         │
└────────┬─────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点4: node_objective_generation()                            │
│   LLM: doubao-seed-2-0-pro | temperature=0.5 | max_tokens=4000│
│   输出: 三层教学目标                                           │
│     basic:      {knowledge:[...], skill:[...], emotion:[...]} │
│     intermediate: {knowledge:[...], skill:[...], emotion:[...]}│
│     advanced:   {knowledge:[...], skill:[...], emotion:[...]} │
│     core_literacy_links: ["必备品格:...", "关键能力:..."]      │
└────────┬─────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点5: node_key_difficult_points()                            │
│   LLM: doubao-seed-2-0-pro | temperature=0.5 | max_tokens=4000│
│   输出:                                                        │
│     key_point: {content, reason, strategy}                    │
│     difficult_points: [{content, reason, breakthrough_strategy,│
│                         scaffolding}, ...]                     │
│     common_misconceptions: ["误区1", "误区2", "误区3"]         │
└────────┬─────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点6: node_teaching_process()                                │
│   LLM: doubao-seed-2-0-pro | temperature=0.7 | max_tokens=8000│
│   输出: 5 环节教学过程编排                                     │
│     [                                                         │
│       {stage:"导入", duration:5, teacher_activity:"...",      │
│        student_activity:"...", design_intent:"...",           │
│        transition:"...", tier_notes:{basic:"...",advanced:"..."}},│
│       {stage:"新授", duration:20, ...},                        │
│       {stage:"练习", duration:12, ...},                        │
│       {stage:"拓展", duration:5, ...},                         │
│       {stage:"总结", duration:3, ...}                          │
│     ]                                                         │
│   每个环节包含: 教师活动、学生活动、设计意图、过渡语、分层要求    │
└────────┬─────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点7: node_board_design()                                    │
│   LLM: doubao-seed-2-0-pro | temperature=0.5 | max_tokens=3000│
│   输出: {main_board:"...", side_board:"...", layout:"..."}    │
└────────┬─────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点8: node_tiered_exercises()                                │
│   LLM: doubao-seed-2-0-pro | temperature=0.5 | max_tokens=4000│
│   输出: {basic:[{question,type,answer_hint,target},...],      │
│          intermediate:[...], advanced:[...]}                  │
└────────┬─────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点9: node_homework_design()                                 │
│   LLM: doubao-seed-2-0-pro | temperature=0.5 | max_tokens=3000│
│   输出: {required:[{task,estimated_time,purpose},...],        │
│          optional:[...], challenge:[...], total_time:"..."}   │
└────────┬─────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点10: node_quality_check()                                  │
│   LLM: doubao-seed-2-0-pro | temperature=0.3 | max_tokens=3000│
│   检查: 结构完整性、字段非空、逻辑一致性                         │
│   重试: 最多 3 次，每次根据错误列表修正                         │
│   条件路由: validation_passed ? → 节点11 : → 重试节点2-9       │
└────────┬─────────────────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────────────────────────┐
│ 节点11: node_format_output()                                  │
│   LLM: doubao-seed-2-0-pro | temperature=0.3 | 无 token 限制   │
│   输入: state 中所有中间产物 JSON                               │
│   输出: final_lesson_plan (完整 Markdown 教案)                  │
│   写入: state.final_lesson_plan                                │
└──────────────────────────────────────────────────────────────┘
```

#### 4.4.2 节点实现模式

每个节点遵循统一模式：

```python
def node_xxx(state: LessonPrepState) -> dict:
    # 1. 获取上下文
    ctx = request_context.get() or new_context(method="lesson_prep.xxx")

    # 2. 创建 LLM Client
    from coze_coding_dev_sdk import LLMClient
    client = LLMClient(ctx=ctx)

    # 3. 构建 System Prompt + User Message
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ]

    # 4. 调用 LLM
    response = client.invoke(
        messages=messages,
        model="doubao-seed-2-0-pro-260215",
        temperature=0.5,
        max_completion_tokens=4000,
        thinking="disabled"
    )

    # 5. 提取文本 + 清理 Markdown 代码块
    content = _extract_text(response)
    content = _clean_markdown_fence(content)

    # 6. JSON 解析 + 容错
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = _fallback_parse(content)

    # 7. 返回 state 更新
    return {"key_difficult_points": parsed, "messages": [AIMessage(content=content)]}
```

**关键细节**：
- 每个节点通过 `return {"field": value}` 更新 state，LangGraph 自动合并
- `messages` 字段使用 `Annotated[list, add_messages]` 累加器，所有 AI 消息自动追加
- `_extract_text()` 处理 `response.content` 可能是 `str` 或 `list[dict]` 的情况
- `_clean_markdown_fence()` 去除 LLM 输出中包裹的 ```json ... ``` 标记

---

### 4.5 教学推演 (`graphs/teaching_simulation.py`)

**文件**: `src/graphs/teaching_simulation.py`（约 1100 行）

#### 4.5.1 核心概念：教学"风洞实验室"

模拟 3 类虚拟学生在同一教案下的反应，预测教学效果瓶颈：

```
教案输入
   │
   ▼
┌─────────────────┐
│ 节点1: 教案解析   │  提取教学环节、教师行为、预期反应
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点2: 虚拟课堂   │  构建 3 个虚拟学生画像
│                  │  学生A: 基础层 (知识薄弱、依赖性强)
│                  │  学生B: 进阶层 (中等水平、偶有困惑)
│                  │  学生C: 挑战层 (学有余力、思维活跃)
└────────┬────────┘
         │
    ┌────┼────┐
    ▼    ▼    ▼
┌──────┐┌──────┐┌──────┐
│学生A  ││学生B  ││学生C  │  3 路并行 Send (LangGraph)
│模拟   ││模拟   ││模拟   │  每个学生独立 LLM 调用
└──┬───┘└──┬───┘└──┬───┘
   │       │       │
   └───────┼───────┘
           ▼
┌─────────────────┐
│ 节点6: 结果聚合   │  合并 3 个学生的模拟结果
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点7: 瓶颈识别   │  识别教学瓶颈 + 受影响层级
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点8: 风险评级   │  red / yellow / green 三级
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点9: 预案生成   │  针对每个瓶颈生成教学预案
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点10: 优化建议  │  教案优化建议
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点11: 对比报告  │  优化前后对比
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点12: 格式化输出│  Markdown 推演报告
└─────────────────┘
```

#### 4.5.2 3 路并行 Send 实现

```python
# 节点2 返回 Send 列表，触发并行执行
def node_build_virtual_classroom(state: SimulationState) -> dict:
    students = [
        {"tier": "basic", "cognitive_profile": "...", "personality": "..."},
        {"tier": "intermediate", "cognitive_profile": "...", "personality": "..."},
        {"tier": "advanced", "cognitive_profile": "...", "personality": "..."},
    ]
    state["virtual_students"] = students
    # 返回 Send 列表，每个 Send 触发一次 node_simulate_student
    return [
        Send("node_simulate_student", {"student": s, "lesson_overview": state["lesson_overview"]})
        for s in students
    ]

# 每个学生独立模拟
def node_simulate_student(state: dict) -> dict:
    student = state["student"]
    # 独立 LLM 调用，模拟该学生在每个教学环节的反应
    ...
    return {"student_key": student["tier"], "result": simulation_result}
```

#### 4.5.3 虚拟学生模拟维度

每个虚拟学生在每个教学环节模拟以下维度：

| 维度 | 说明 |
|------|------|
| `attention` | 注意力水平 (0-100) |
| `understanding_level` | 理解程度 (0-100) |
| `inner_monologue` | 内心独白 |
| `external_behavior` | 外在表现 |
| `if_called_answer` | 被点名时的回答 |
| `confusion_points` | 困惑点列表 |
| `engagement_score` | 参与度 (0-100) |

---

### 4.6 成长分析 (`graphs/growth_analysis.py`)

**文件**: `src/graphs/growth_analysis.py`（约 900 行）

#### 4.6.1 工作流拓扑

```
历史教学数据
   │
   ▼
┌─────────────────┐
│ 节点1: 数据采集   │  从数据库/S3 拉取历史教案、推演报告、课堂记录
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点2: 数据清洗   │  去重、格式化、时间对齐
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点3-7: 5维评估  │  并行评估 5 个维度:
│   设计能力        │    教案结构、目标设定、活动设计
│   课堂执行        │    时间管理、互动质量、应变能力
│   诊断能力        │    学情判断、错因分析、分层精准度
│   反馈能力        │    作业评语、课堂点评、激励效果
│   反思能力        │    教学日志深度、改进措施、成长意识
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点8: 五维聚合   │  加权计算综合成长分
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点9: 趋势分析   │  时间序列分析，识别上升/平台/下降趋势
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点10: 归因分析  │  识别关键影响因素
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点11: 关键事件  │  里程碑事件识别 + 成就发现
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点12: 个性化建议│  针对性成长建议 + 激励寄语
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点13: 格式化输出│  Markdown 成长报告
└─────────────────┘
```

---

### 4.7 主控 Agent (`agents/agent.py`)

**文件**: `src/agents/agent.py`（约 150 行）

基于 LangChain Agent 框架的意图路由层：

```python
def create_teaching_agent():
    tools = [
        generate_lesson_plan_tool,       # → 智能备课工作流
        analyze_learning_situation_tool,  # → 学情诊断
        simulate_teaching_tool,           # → 教学推演工作流
        classroom_assistant_tool,         # → 课堂实时辅助
        generate_growth_report_tool,      # → 成长分析工作流
    ]

    llm = ChatOpenAI(model="doubao-seed-2-0-pro-260215", ...)

    agent = create_react_agent(llm, tools, state_modifier=SYSTEM_PROMPT)
    return agent
```

**Agent 模式 vs Graph 模式**：

| 模式 | 触发条件 | 路由方式 | 适用场景 |
|------|---------|---------|---------|
| Agent | `graph_helper.is_agent_proj() == True` | LLM 意图识别 → Tool 选择 | 多意图混合输入 |
| Graph | `graph_helper.is_agent_proj() == False` | 直接进入 StateGraph | 单一明确任务 |

当前项目默认使用 **Graph 模式**。

---

### 4.8 存储层 (`storage/`)

#### 4.8.1 数据库引擎 (`storage/database/db.py`)

```python
def get_engine():
    global _engine
    if _engine is None:
        url = get_db_url()  # PGDATABASE_URL 环境变量
        if url:
            _engine = create_engine(url, pool_size=10, ...)
        elif os.getenv("DEV_MODE") == "1":
            _engine = _create_sqlite_fallback()  # → /tmp/vibe_coding_dev.db
        else:
            raise ValueError("PGDATABASE_URL is not set")
    return _engine
```

**连接获取优先级**：
1. `PGDATABASE_URL` 环境变量
2. `coze_workload_identity.Client().get_project_env_vars()` 平台注入
3. `DEV_MODE=1` 时降级 SQLite
4. 以上均无 → 抛出 `ValueError`

#### 4.8.2 状态检查点 (`storage/memory/memory_saver.py`)

```python
def get_checkpointer():
    if os.getenv("DEV_MODE") == "1":
        return MemorySaver()  # 内存存储，重启丢失
    else:
        engine = get_engine()
        PostgresSaver.setup(engine)  # 自动建表
        return PostgresSaver(engine)
```

---

### 4.9 JSON→Markdown 格式化引擎

**位置**: `src/main.py` 中的 `format_teaching_content()` 函数（约 120 行）

#### 4.9.1 设计动机

LangGraph 工作流的中间节点输出 JSON 格式的结构化数据，`collect_langgraph_to_response()` 将所有 AI 消息拼接为最终 content。这些混合内容（JSON + Markdown）直接展示给用户体验极差。

#### 4.9.2 实现原理

```
输入: 混合文本 (JSON 块 + Markdown 块)
   │
   ▼
┌──────────────────────────────────────┐
│ 1. 正则匹配所有 JSON 块               │
│    re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)│
│                                      │
│ 2. 逐个 JSON.parse()                 │
│    - 成功 → 递归转为 Markdown         │
│    - 失败 → 保留原文                  │
│                                      │
│ 3. 递归转换规则:                      │
│    dict → "**键名**: 值" 逐行输出     │
│    list → 编号列表                    │
│    str  → 直接输出                    │
│    int/float → 直接输出               │
│                                      │
│ 4. 键名翻译: KEY_ZH_MAP (296 个映射)  │
│    "subject" → "学科"                │
│    "key_point" → "教学重点"           │
│    "breakthrough_strategy" → "突破策略"│
│    ...                               │
│                                      │
│ 5. 输出: 纯 Markdown 文本             │
└──────────────────────────────────────┘
```

#### 4.9.3 翻译映射表（部分）

```python
KEY_ZH_MAP = {
    # 课题信息 (7 个)
    "subject": "学科", "topic": "课题", "grade": "年级",
    "lesson_hours": "课时", "lesson_type": "课型",
    "style_preference": "风格偏好", "key_concerns": "关注要点",

    # 教学重难点 (8 个)
    "key_point": "教学重点", "difficult_points": "教学难点",
    "common_misconceptions": "常见误区",
    "content": "内容", "reason": "原因", "strategy": "策略",
    "breakthrough_strategy": "突破策略", "scaffolding": "脚手架",

    # 教学过程 (10 个)
    "teaching_process": "教学过程", "stage": "教学环节",
    "duration": "时长", "teacher_activity": "教师活动",
    "student_activity": "学生活动", "design_intent": "设计意图",
    "transition": "过渡语", "tier_notes": "分层要求",

    # 教学目标分层 (9 个)
    "basic": "基础层", "intermediate": "进阶层", "advanced": "拓展层",
    "knowledge": "知识目标", "skill": "能力目标", "emotion": "情感目标",

    # 教学推演 (40+ 个)
    "virtual_students": "虚拟学生", "student_simulations": "学生模拟",
    "attention": "注意力", "understanding_level": "理解程度",
    "inner_monologue": "内心独白", "external_behavior": "外在表现",
    "bottlenecks": "瓶颈分析", "risk_assessment": "风险评估",
    # ... 共 296 个映射
}
```

---

### 4.10 前端聊天界面 (`assets/index.html`)

**文件**: `assets/index.html`（约 1500 行，单文件）

#### 4.10.1 技术选型

| 选择 | 理由 |
|------|------|
| 零框架 | 避免 npm/webpack 构建链，直接通过 FastAPI StaticFiles 挂载 |
| marked.js CDN | 轻量 Markdown 解析（~30KB） |
| highlight.js CDN | 代码语法着色（~50KB） |
| CSS 变量 + 暗色主题 | 玻璃拟态效果，无预处理器依赖 |
| Fetch API | 原生异步请求，无 axios 依赖 |

#### 4.10.2 核心交互流程

```
用户输入 → Enter 或点击发送
   │
   ▼
sendMessage()
   ├── 创建用户消息气泡
   ├── 创建 AI 消息占位气泡（含加载动画）
   ├── POST /v1/chat/completions {stream: false}
   │     timeout: 300s
   │
   ├── 成功:
   │   ├── 提取 choices[0].message.content
   │   ├── marked.parse(content) → HTML
   │   ├── highlight.js 着色代码块
   │   ├── 添加代码块复制按钮
   │   └── 打字机动画逐字显示
   │
   └── 失败:
       └── 显示错误提示 + 重试建议
```

#### 4.10.3 打字机动画实现

```javascript
function typewriterEffect(element, html, speed = 30) {
    // 1. 创建临时 DOM 解析 HTML 结构
    const temp = document.createElement('div');
    temp.innerHTML = html;

    // 2. 递归遍历 DOM 树
    function traverse(node, targetParent) {
        if (node.nodeType === Node.TEXT_NODE) {
            // 文本节点：逐字添加
            const text = node.textContent;
            for (let i = 0; i < text.length; i++) {
                targetParent.appendChild(document.createTextNode(text[i]));
                await sleep(speed);
            }
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            // 元素节点：创建对应标签，递归处理子节点
            const el = document.createElement(node.tagName);
            for (const child of node.childNodes) {
                await traverse(child, el);
            }
            targetParent.appendChild(el);
        }
    }

    await traverse(temp, element);
}
```

---

## 5. API 接口规范

### 5.1 OpenAI 兼容接口

```bash
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "test",                    # 模型标识（内部路由用）
  "messages": [
    {"role": "user", "content": "帮我备一节数学课"}
  ],
  "stream": false,                    # false: 完整返回; true: SSE 流式
  "session_id": "optional-session-id" # 可选，用于会话状态恢复
}
```

**非流式响应** (`stream: false`)：

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "test",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "# 数学教案\n\n## 课题信息\n- **学科**: 数学\n- **课题**: 二次函数\n..."
    },
    "finish_reason": "stop"
  }]
}
```

### 5.2 内部 API

| 接口 | 方法 | Content-Type | 说明 |
|------|------|-------------|------|
| `/run` | POST | `application/json` | 同步执行，返回完整 state |
| `/stream_run` | POST | `application/json` | SSE 流式，`text/event-stream` |
| `/async_run` | POST | `application/json` | 异步执行，返回 `{"task_id":"..."}` |
| `/task/{task_id}` | GET | — | 查询异步任务状态 |
| `/health` | GET | — | `{"status":"ok"}` |
| `/graph_parameter` | GET | — | 工作流输入参数 schema |

---

## 6. 完整数据流

### 6.1 智能备课请求全链路

```
1. 用户输入 "帮我备一节数学课"
         │
2. POST /v1/chat/completions  (stream: false)
         │
3. openai_chat_completions()
   ├── 解析请求体 → messages, session_id, stream
   ├── 创建 OpenAIChatHandler 实例
   └── handler.handle(model, messages, session_id, stream=False)
         │
4. OpenAIChatHandler._handle_non_stream()
   ├── 构建 payload: {messages: [{role:"user", content:"..."}]}
   ├── 获取编译后的图: graph_helper.get_graph_instance()
   ├── 初始化运行配置: init_run_config(graph, ctx)
   └── graph.stream(payload, config, stream_mode="messages")
         │
5. LangGraph 流式执行 (11 个节点依次执行)
   ├── 节点1: LLM 调用 → {"subject":"数学","topic":"二次函数",...}
   ├── 节点2: LLM 调用 → KB 检索上下文 (Markdown)
   ├── 节点3: LLM 调用 → 7维风格向量
   ├── 节点4: LLM 调用 → 三层教学目标
   ├── 节点5: LLM 调用 → 重难点分析
   ├── 节点6: LLM 调用 → 5环节教学过程
   ├── 节点7: LLM 调用 → 板书设计
   ├── 节点8: LLM 调用 → 分层练习
   ├── 节点9: LLM 调用 → 作业设计
   ├── 节点10: LLM 调用 → 质量校验 (最多3次重试)
   └── 节点11: LLM 调用 → final_lesson_plan (Markdown)
         │
6. collect_langgraph_to_response()
   ├── 遍历 stream 中的每个 chunk
   ├── 提取所有 AI 消息的 content
   └── 拼接为完整文本 (JSON + Markdown 混合)
         │
7. 返回 JSONResponse → openai_chat_completions()
         │
8. format_teaching_content(content)
   ├── 正则匹配 JSON 块 → JSON.parse()
   ├── 递归转为 Markdown (dict→键值对, list→编号列表)
   ├── KEY_ZH_MAP 翻译键名 (296 个映射)
   └── 返回纯 Markdown 文本
         │
9. 更新 choices[0].message.content → 新的 JSONResponse
         │
10. 前端接收
    ├── marked.parse(markdown) → HTML
    ├── highlight.js 着色代码块
    ├── 添加复制按钮
    └── 打字机动画逐字显示
```

### 6.2 时间线估算

| 阶段 | 耗时 | 说明 |
|------|------|------|
| 请求解析 | < 10ms | JSON 解析 + 路由 |
| 图编译 | < 100ms | 首次懒加载，后续缓存 |
| 节点1-11 LLM 调用 | 60-120s | 11 次 LLM API 调用（每次 2-10s） |
| 响应收集 | < 10ms | 文本拼接 |
| JSON→MD 格式化 | < 100ms | 纯 CPU 正则 + 递归 |
| 前端渲染 | < 500ms | marked.js + highlight.js + 打字机 |
| **总计** | **60-120s** | 主要瓶颈在 LLM API 调用 |

---

## 7. 运行与部署

### 7.1 本地开发

```bash
# 1. 进入项目目录
cd projects

# 2. 安装依赖
bash scripts/setup.sh
# 等价于: uv sync

# 3. 启动服务
export DEV_MODE=1
export PYTHONPATH="src:$PYTHONPATH"
source .venv/bin/activate
python src/main.py -m http -p 5000

# 4. 验证
curl http://localhost:5000/health
# → {"status":"ok"}

# 5. 访问
# 前端界面: http://localhost:5000/
# API 文档:  http://localhost:5000/docs
```

### 7.2 预览模式（扣子平台）

点击平台「预览」按钮，自动执行 `.coze` 中定义的命令：

```toml
[dev]
build = ["bash", "projects/scripts/setup.sh"]   # uv sync
run   = ["bash", "projects/scripts/http_run.sh"]  # 启动 HTTP 服务
```

`http_run.sh` 自动设置 `DEV_MODE=1`，启用数据库降级。

### 7.3 生产部署

```toml
[deploy]
build = ["bash", "projects/scripts/setup.sh"]
run   = ["bash", "projects/scripts/http_run.sh"]
```

生产环境需配置：

| 环境变量 | 说明 | 必填 |
|---------|------|------|
| `PGDATABASE_URL` | PostgreSQL 连接串 | 生产必填 |
| `DEV_MODE` | 设为 `1` 启用降级 | 开发用，生产不设 |

---

## 8. 配置体系

### 8.1 `.coze` 双文件体系

| 文件 | 位置 | 关键字段 |
|------|------|---------|
| 根 `.coze` | `/workspace/projects/.coze` | `project_type`, `preview_enable`, `[dev]`, `[deploy]`, `[subprojects]` |
| 子项目 `.coze` | `/workspace/projects/projects/.coze` | `sub_id`, `name`, `project_type`, `preview_enable` |

根 `.coze` 是平台唯一读取入口，子项目 `.coze` 记录项目自身元信息。两者 `project_type` 和 `preview_enable` 必须一致。

### 8.2 LLM 配置 (`config/agent_llm_config.json`)

```json
{
  "config": {
    "model": "doubao-seed-2-0-pro-260215",
    "temperature": 0.7,
    "timeout": 600,
    "thinking": "disabled"
  },
  "sp": "你是教思AI教学助手，专注于为教师提供..."
}
```

### 8.3 可用模型（扣子平台免费额度）

| 模型 ID | 类型 | 特点 | 适用场景 |
|---------|------|------|---------|
| `doubao-seed-2-0-pro-260215` | 旗舰 | 复杂推理、多模态 | 备课/推演/分析主流程 |
| `doubao-seed-2-0-lite-260215` | 均衡 | 性能与成本平衡 | 需求解析、格式化 |
| `doubao-seed-2-0-mini-260215` | 轻量 | 低延迟、高并发 | 简单任务 |
| `deepseek-v3-2-251201` | 通用 | 平衡推理与输出 | 通用对话 |
| `kimi-k2-5-260127` | 多模态 | Agent 能力强 | 复杂 Agent 任务 |

---

## 9. 开发降级方案

当 `DEV_MODE=1` 时，系统自动启用以下降级：

| 组件 | 生产环境 | 开发降级 | 影响 |
|------|---------|---------|------|
| 数据库引擎 | PostgreSQL (SQLAlchemy) | SQLite (`/tmp/vibe_coding_dev.db`) | 数据不跨会话持久化 |
| 状态检查点 | PostgresSaver | MemorySaver (内存) | 重启后 LangGraph 状态丢失 |
| LLM 调用 | 扣子平台 API | 同生产（免费额度） | 无影响 |
| 端口 | 5000 | 5000 | 无影响 |

**降级触发条件**：
1. `DEV_MODE=1` 环境变量已设置
2. `PGDATABASE_URL` 未配置或为空

---

## 10. 常见问题

### Q1: 预览显示 `{"detail":"Not Found"}`
**原因**: 根路径 `/` 未定义路由或静态文件未挂载。
**解决**: 确认 `main.py` 中有 `app.mount("/", StaticFiles(...))` 和 `assets/index.html` 存在。

### Q2: 对话接口超时（60-120 秒无响应）
**原因**: 智能备课涉及 11 次 LLM 调用，总耗时 60-120 秒。
**解决**: 前端超时设为 300 秒；使用 `stream: true` 获取实时进度反馈。

### Q3: 输出显示原始 JSON 而非 Markdown
**原因**: 前端使用 `stream: true` 绕过了 `format_teaching_content()`。
**解决**: 使用 `stream: false` 确保后端格式化生效。

### Q4: `PGDATABASE_URL is not set`
**原因**: 未配置数据库连接串。
**解决**: 设置 `DEV_MODE=1` 启用 SQLite 降级；或配置真实 PostgreSQL 连接串。

### Q5: `ModuleNotFoundError: No module named 'coze_coding_utils.xxx'`
**原因**: 依赖未安装或版本不兼容。
**解决**: 运行 `bash scripts/setup.sh` 重新安装。如遇 `pycairo` 编译失败，从 `pyproject.toml` 移除该依赖（后端服务不需要 GUI 库）。

### Q6: 如何切换工作流？
**解决**: 修改 `src/graphs/graph.py` 中的默认 workflow 参数：
```python
_wrapper = _GraphWrapper(workflow="simulation")  # 教学推演
_wrapper = _GraphWrapper(workflow="growth")      # 成长分析
```

### Q7: 输出中部分字段仍显示英文
**原因**: `KEY_ZH_MAP` 中缺少对应键的翻译。
**解决**: 在 `src/main.py` 的 `KEY_ZH_MAP` 字典中添加映射。当前已覆盖 296 个键。

---

## 附录

### A. 依赖清单

核心依赖（`pyproject.toml`）：

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
langgraph>=0.6.0
langchain>=0.3.0
langchain-core>=0.3.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
coze-coding-utils
coze-coding-dev-sdk
python-dotenv>=1.0.0
```

### B. 端口约定

| 端口 | 用途 | 备注 |
|------|------|------|
| 5000 | HTTP 服务 | 唯一对外端口 |
| 9000 | 系统保留 | 禁止使用 |

### C. 编码规范

- Python: 遵循 PEP 8，4 空格缩进
- 节点函数命名: `node_<功能描述>` (如 `node_parse_requirements`)
- 工作流构建函数: `build_<场景>_graph()` (如 `build_lesson_prep_graph`)
- State 类: 继承 `TeachingState`，`total=False` 允许部分字段
- 日志: 使用 `logging.getLogger(__name__)`，格式 `[模块-节点] 描述`
