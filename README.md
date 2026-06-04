# 「教思」AI 教学孪生系统

> **TeachingThought** — 教师教学思维的数字镜像

「教思」是一个基于 **LangGraph + FastAPI** 构建的 AI 教学辅助系统，为教师提供智能备课、教学推演、学情分析、课堂辅助和成长分析五大核心能力。系统通过多节点 StateGraph 工作流编排，调用扣子平台免费 LLM（豆包/DeepSeek/Kimi 等），实现从需求解析到教案输出的全流程自动化。

---

## 目录

- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [目录结构](#目录结构)
- [核心模块详解](#核心模块详解)
  - [1. 主入口 `main.py`](#1-主入口-mainpy)
  - [2. 图入口 `graphs/graph.py`](#2-图入口-graphsgraphpy)
  - [3. 状态定义 `graphs/state.py`](#3-状态定义-graphsstatepy)
  - [4. 智能备课工作流 `graphs/lesson_prep.py`](#4-智能备课工作流-graphslesson_preppy)
  - [5. 教思主控 Agent `agents/agent.py`](#5-教思主控-agent-agentsagentpy)
  - [6. 工具基础设施 `tools/utility_tools.py`](#6-工具基础设施-toolsutility_toolspy)
  - [7. 存储层 `storage/`](#7-存储层-storage)
  - [8. 前端页面 `assets/index.html`](#8-前端页面-assetsindexhtml)
- [API 接口](#api-接口)
- [数据流](#数据流)
- [运行与部署](#运行与部署)
- [配置说明](#配置说明)
- [开发模式降级方案](#开发模式降级方案)
- [常见问题](#常见问题)

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                        用户交互层                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐ │
│  │  Web 聊天界面 │  │  OpenAI API  │  │  内部 HTTP API (run/stream)  │ │
│  │  (index.html) │  │  /v1/chat/   │  │  /run /stream_run /async_run │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┬───────────────┘ │
│         │                 │                          │                 │
│         └────────────┬────┴──────────────────────────┘                 │
│                      ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                    FastAPI HTTP 服务层                             │ │
│  │  • 路由注册  • 请求/响应处理  • SSE 流式输出  • CORS              │ │
│  └──────────────────────────────┬───────────────────────────────────┘ │
│                                 ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                     GraphService (核心调度)                        │ │
│  │  • run()        — 同步/异步执行工作流                              │ │
│  │  • stream_sse() — SSE 流式执行                                    │ │
│  │  • cancel_run() — 任务取消                                        │ │
│  │  • format_teaching_content() — JSON→Markdown 格式化               │ │
│  └──────────────────────────────┬───────────────────────────────────┘ │
│                                 ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                    LangGraph 工作流引擎                            │ │
│  │                                                                   │ │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │ │
│  │  │ 智能备课 (11节点) │  │ 教学推演 (12节点) │  │ 成长分析 (12节点) │ │ │
│  │  │ lesson_prep.py   │  │ simulation.py    │  │ growth_analysis  │ │ │
│  │  └─────────────────┘  └──────────────────┘  └──────────────────┘ │ │
│  │                                                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │ 教思主控 Agent (agents/agent.py)                             │ │ │
│  │  │ • 意图识别 → 路由分发 → 工具调用                              │ │ │
│  │  │ • 5 个教学专用 Tool                                           │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────┬───────────────────────────────────┘ │
│                                 ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                        基础设施层                                  │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │ │
│  │  │ LLM 调用  │  │ 数据库   │  │ 状态管理 │  │ 日志/追踪/错误   │ │ │
│  │  │ SDK/API  │  │ PG/SQLite│  │ Memory   │  │ cozeloop/log     │ │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **语言** | Python | ≥3.12 | 主语言 |
| **Web 框架** | FastAPI + uvicorn | ≥0.121 | HTTP 服务 |
| **工作流引擎** | LangGraph | 1.0.2 | StateGraph 多节点编排 |
| **LLM SDK** | coze-coding-dev-sdk | >0.5.0 | 扣子平台 LLM 调用（免费额度） |
| **LLM 框架** | LangChain | 1.0.3 | Agent/Tool 构建 |
| **数据库** | PostgreSQL + SQLAlchemy | ≥2.0 | 生产环境持久化 |
| **数据库降级** | SQLite (aiosqlite) | — | 开发环境自动降级 |
| **状态检查点** | langgraph-checkpoint-postgres | ≥3.0 | 工作流状态持久化 |
| **状态降级** | MemorySaver | — | 开发环境内存存储 |
| **依赖管理** | uv | — | Python 包管理 |
| **前端** | 原生 HTML/CSS/JS | — | 聊天界面（marked.js + highlight.js） |
| **文档处理** | pypdf, docx2python, openpyxl, python-pptx | — | 教学资源解析 |
| **图像处理** | opencv-python, Pillow | — | 板书/图片处理 |
| **日志追踪** | cozeloop | ≥0.1.25 | 分布式追踪与日志 |

---

## 目录结构

```
projects/                              # 技术项目根目录
├── .coze                              # 子项目配置（sub_id, name, project_type）
├── pyproject.toml                     # Python 项目配置 + 依赖声明
├── uv.lock                            # uv 依赖锁文件
├── AGENTS.md                          # Agent 认知文档
│
├── config/                            # 配置文件目录
│   ├── agent_llm_config.json          # LLM 配置（模型、温度、System Prompt）
│   └── prompts/                       # 提示词模板目录
│
├── src/                               # 源代码目录
│   ├── main.py                        # ★ 主入口：FastAPI 应用 + GraphService
│   │
│   ├── graphs/                        # LangGraph 工作流定义
│   │   ├── __init__.py                # Graph 包装器（路由到不同工作流）
│   │   ├── graph.py                   # 图入口（供框架发现）
│   │   ├── state.py                   # ★ 全局状态定义（TeachingState 等）
│   │   ├── lesson_prep.py             # ★ 智能备课工作流（11节点）
│   │   ├── teaching_simulation.py     # 教学推演工作流（12节点）
│   │   ├── growth_analysis.py         # 成长分析工作流（12节点）
│   │   └── nodes/                     # 可复用节点函数
│   │
│   ├── agents/                        # LangGraph Agent 定义
│   │   └── agent.py                   # ★ 教思主控 Agent（5个教学Tool）
│   │
│   ├── tools/                         # 工具基础设施
│   │   └── utility_tools.py           # RAG检索、变量管理、提示词加载
│   │
│   ├── storage/                       # 存储层
│   │   ├── database/
│   │   │   ├── db.py                  # ★ 数据库引擎（PG + SQLite降级）
│   │   │   └── shared/model.py        # ORM 模型定义
│   │   └── memory/
│   │       └── memory_saver.py        # ★ 状态检查点（PG + Memory降级）
│   │
│   └── utils/                         # 工具模块
│       ├── helper.py                  # 框架辅助（导出 graph_helper）
│       └── log/
│           ├── __init__.py
│           └── loop_trace.py          # 运行配置初始化
│
├── scripts/                           # 运行脚本
│   ├── setup.sh                       # ★ 依赖安装（uv sync）
│   └── http_run.sh                    # ★ HTTP 服务启动
│
└── assets/                            # 静态资源
    └── index.html                     # ★ 前端聊天界面
```

> 工作区根目录 `/workspace/projects/` 下的 `.coze` 是平台读取的唯一入口，通过 `[subprojects]` 注册子项目路径。

---

## 核心模块详解

### 1. 主入口 `main.py`

**职责**：FastAPI 应用初始化、路由注册、GraphService 核心调度、JSON→Markdown 格式化。

#### 关键组件

| 组件 | 说明 |
|------|------|
| `GraphService` | 核心调度类，封装 LangGraph 工作流的执行、流式输出、取消 |
| `format_teaching_content()` | JSON→Markdown 格式化函数（规则引擎，零延迟） |
| `openai_chat_completions()` | OpenAI 兼容接口 `/v1/chat/completions` |
| `lifespan()` | FastAPI 生命周期管理（数据库初始化、静态文件挂载） |

#### 路由表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 前端聊天界面（`assets/index.html`） |
| `GET` | `/health` | 健康检查 |
| `POST` | `/v1/chat/completions` | OpenAI 兼容对话接口 |
| `POST` | `/run` | 同步执行工作流 |
| `POST` | `/stream_run` | SSE 流式执行工作流 |
| `POST` | `/async_run` | 异步任务执行 |
| `GET` | `/task/{task_id}` | 查询异步任务状态 |
| `GET` | `/graph_parameter` | 获取图参数信息 |

#### 超时配置

```python
TIMEOUT_SECONDS = 900  # 15分钟（工作流可能涉及多步 LLM 调用）
```

---

### 2. 图入口 `graphs/graph.py`

**职责**：为 `coze_coding_utils` 框架提供已编译的 `CompiledStateGraph` 实例。

```python
from graphs import Graph as _GraphWrapper

_wrapper = _GraphWrapper(workflow="lesson_prep")
graph: CompiledStateGraph = _wrapper.builder.compile()
```

框架通过 `graph_helper.get_graph_instance("graphs.graph")` 发现并加载此模块。

---

### 3. 状态定义 `graphs/state.py`

**职责**：定义所有工作流共享的状态结构。

#### 全局状态 `TeachingState`（10个会话变量）

| 字段 | 类型 | 说明 |
|------|------|------|
| `subject` | str | 当前科目 |
| `grade` / `grade_level` | str | 学段/年级 |
| `teaching_style` | TeachingStyle | 7维风格向量 |
| `current_lesson_topic` | str | 当前课题 |
| `lesson_plan_draft` | str | 教案全文 |
| `simulation_result` | SimulationResult | 推演结果摘要 |
| `workflow_mode` | str | 当前工作流模式 |
| `kb_results` | KnowledgeBaseResults | RAG 检索缓存 |
| `validation_errors` / `validation_passed` | list/bool | 质量校验 |

#### 工作流专用 State

| State | 节点数 | 说明 |
|-------|--------|------|
| `LessonPrepState` | 11 | 智能备课：需求→KB→风格→目标→重难点→过程→板书→练习→作业→校验→格式化 |
| `SimulationState` | 12 | 教学推演：3路并行学生模拟 + 瓶颈分析 + 应急预案 |
| `GrowthAnalysisState` | 12 | 成长分析：五维能力雷达图 + 趋势 + 归因 + 建议 |

#### 7维教学风格向量

```
compactness (紧凑度)  interactivity (互动度)  depth (深度)
interest (趣味性)     rigor (严谨度)         innovation (创新度)
warmth (温度)
```

---

### 4. 智能备课工作流 `graphs/lesson_prep.py`

**职责**：11节点 StateGraph，从用户输入到完整教案的全流程自动化。

#### 工作流节点

```
用户输入
   │
   ▼
┌─────────────────┐
│ 节点1: 需求解析   │  LLM 提取：学科、课题、年级、课时、课型、风格偏好
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点2: KB检索    │  并行检索 4 个知识库（课标/教材/教学法/个人）
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点3: 风格建模   │  提取教师 7 维教学风格向量
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点4: 目标生成   │  三层教学目标（基础/进阶/挑战）+ 核心素养链接
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点5: 重难点设计 │  1个重点 + 2个难点 + 突破策略 + 常见误区
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点6: 教学过程   │  5环节编排（导入→新授→练习→拓展→总结）
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点7: 板书设计   │  结构化板书内容
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点8: 分层练习   │  基础/进阶/挑战三层练习
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点9: 作业设计   │  必做/选做/挑战三层作业
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点10: 质量校验  │  最多 3 次重试，检查结构完整性
└────────┬────────┘
         ▼
┌─────────────────┐
│ 节点11: 格式化输出│  LLM 将 JSON 数据转为 Markdown 教案
└─────────────────┘
```

#### 每个节点的 LLM 调用参数

| 节点 | 模型 | temperature | max_tokens |
|------|------|-------------|------------|
| 需求解析 | doubao-seed-2-0-pro | 0.3 | 2000 |
| KB检索 | doubao-seed-2-0-pro | 0.5 | 6000 |
| 风格建模 | doubao-seed-2-0-pro | 0.5 | 4000 |
| 目标生成 | doubao-seed-2-0-pro | 0.5 | 4000 |
| 重难点 | doubao-seed-2-0-pro | 0.5 | 4000 |
| 教学过程 | doubao-seed-2-0-pro | 0.7 | 8000 |
| 板书设计 | doubao-seed-2-0-pro | 0.5 | 3000 |
| 分层练习 | doubao-seed-2-0-pro | 0.5 | 4000 |
| 作业设计 | doubao-seed-2-0-pro | 0.5 | 3000 |
| 质量校验 | doubao-seed-2-0-pro | 0.3 | 3000 |
| 格式化输出 | doubao-seed-2-0-pro | 0.3 | 无限制 |

---

### 5. 教思主控 Agent `agents/agent.py`

**职责**：基于 LangChain Agent 的主控路由，通过意图识别将用户请求分发到 5 个教学专用 Tool。

#### 5 个教学 Tool

| Tool | 功能 | 适用场景 |
|------|------|---------|
| `generate_lesson_plan` | 生成完整备课教案 | "帮我备一节数学课" |
| `analyze_learning_situation` | 学情诊断 + 错因分析 | "分析一下班级成绩" |
| `simulate_teaching` | 虚拟课堂推演 | "推演一下这个教案" |
| `classroom_assistant` | 课堂实时辅助 | "学生回答后该问什么" |
| `generate_growth_report` | 教师成长分析 | "看看我的教学成长" |

#### Agent 模式 vs Graph 模式

| 模式 | 触发条件 | 路由方式 |
|------|---------|---------|
| Agent 模式 | `graph_helper.is_agent_proj() == True` | 主控 Agent 意图识别 → Tool 调用 |
| Graph 模式 | `graph_helper.is_agent_proj() == False` | 直接进入 StateGraph 工作流 |

当前项目默认使用 **Graph 模式**（`is_agent_proj() == False`）。

---

### 6. 工具基础设施 `tools/utility_tools.py`

**职责**：提供工作流节点共用的基础设施。

| 功能 | 说明 |
|------|------|
| RAG 检索 | 从 4 个知识库检索教学资源 |
| 变量管理 | 会话变量读写 + 用户变量持久化 |
| 提示词加载 | 从 `config/prompts/` 加载提示词模板 |
| 格式化输出 | JSON→Markdown 转换辅助 |

---

### 7. 存储层 `storage/`

#### 数据库 `storage/database/db.py`

```
生产环境: PostgreSQL (PGDATABASE_URL)
开发环境: SQLite (/tmp/vibe_coding_dev.db)  ← DEV_MODE=1 时自动降级
```

#### 状态检查点 `storage/memory/memory_saver.py`

```
生产环境: PostgresSaver (PGDATABASE_URL)
开发环境: MemorySaver (内存，重启丢失)      ← DEV_MODE=1 时自动降级
```

---

### 8. 前端页面 `assets/index.html`

**职责**：纯原生 HTML/CSS/JS 聊天界面，零框架依赖。

#### 功能特性

| 功能 | 实现 |
|------|------|
| 暗色主题 UI | CSS 变量 + 玻璃拟态效果 |
| Markdown 渲染 | marked.js 解析 |
| 代码高亮 | highlight.js + 一键复制 |
| 打字机动画 | 逐字显示 AI 回复 |
| 会话管理 | 侧边栏会话列表 + 新建会话 |
| 快捷操作 | 智能备课、学情分析、课堂模拟、成长分析 |
| 响应式 | 桌面端侧边栏 + 移动端自适应 |

#### 数据流

```
用户输入 → POST /v1/chat/completions (stream: false)
         → 后端 format_teaching_content() 格式化
         → 返回 Markdown 文本
         → 前端 marked.js 渲染 + 打字机动画
```

---

## API 接口

### OpenAI 兼容接口

```bash
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "test",
  "messages": [
    {"role": "user", "content": "帮我备一节数学课"}
  ],
  "stream": false,
  "session_id": "optional-session-id"
}
```

**响应**：
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "test",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "# 数学教案\n\n## 课题信息\n..."
      },
      "finish_reason": "stop"
    }
  ]
}
```

### 内部 API

| 接口 | 说明 |
|------|------|
| `POST /run` | 同步执行工作流，返回完整结果 |
| `POST /stream_run` | SSE 流式执行，实时返回节点输出 |
| `POST /async_run` | 异步执行，返回 task_id 后轮询 |
| `GET /task/{task_id}` | 查询异步任务状态和结果 |
| `GET /health` | 健康检查 `{"status": "ok"}` |
| `GET /graph_parameter` | 获取工作流参数定义 |

---

## 数据流

### 完整请求链路（以智能备课为例）

```
1. 用户输入 "帮我备一节数学课"
         │
2. POST /v1/chat/completions
         │
3. OpenAIChatHandler.handle()
   ├── 构建 payload: {messages: [...]}
   ├── 调用 graph.stream(stream_mode="messages")
   │   ├── 节点1: 需求解析 → {"subject": "数学", ...}
   │   ├── 节点2: KB检索 → 课标/教材/教学法上下文
   │   ├── 节点3: 风格建模 → 7维风格向量
   │   ├── 节点4: 目标生成 → 三层教学目标
   │   ├── 节点5: 重难点 → 重点+难点+策略
   │   ├── 节点6: 教学过程 → 5环节编排
   │   ├── 节点7: 板书设计
   │   ├── 节点8: 分层练习
   │   ├── 节点9: 作业设计
   │   ├── 节点10: 质量校验（最多3次重试）
   │   └── 节点11: 格式化输出 → Markdown 教案
   └── collect_langgraph_to_response() 收集所有 AI 消息
         │
4. format_teaching_content(content)
   ├── 检测 JSON 块 → 解析为 dict/list
   ├── 递归转为 Markdown（标题、列表、表格）
   ├── 键名翻译（subject→学科, topic→课题...）
   └── 返回纯 Markdown 文本
         │
5. JSONResponse → 前端
         │
6. 前端 marked.js 渲染 + 打字机动画
```

---

## 运行与部署

### 本地开发

```bash
# 1. 安装依赖
cd projects
bash scripts/setup.sh

# 2. 启动服务（开发模式）
export DEV_MODE=1
export PYTHONPATH="src:$PYTHONPATH"
source .venv/bin/activate
python src/main.py -m http -p 5000

# 3. 访问
# 前端界面: http://localhost:5000/
# API 文档: http://localhost:5000/docs
# 健康检查: http://localhost:5000/health
```

### 预览模式（扣子平台）

点击平台「预览」按钮，自动执行：
```toml
[dev]
build = ["bash", "projects/scripts/setup.sh"]
run   = ["bash", "projects/scripts/http_run.sh"]
```

### 生产部署

需要配置以下环境变量：

| 变量 | 说明 | 必填 |
|------|------|------|
| `PGDATABASE_URL` | PostgreSQL 连接串 | 生产必填 |
| `DEV_MODE` | 设为 `1` 启用开发降级 | 开发用 |

---

## 配置说明

### `.coze` 双文件体系

| 文件 | 位置 | 职责 |
|------|------|------|
| 根 `.coze` | `/workspace/projects/.coze` | 平台唯一入口，含 `[dev]`/`[deploy]`/`[subprojects]` |
| 子项目 `.coze` | `/workspace/projects/projects/.coze` | 子项目自身配置（`sub_id`, `name`, `project_type`） |

### LLM 配置 `config/agent_llm_config.json`

```json
{
  "config": {
    "model": "doubao-seed-2-0-pro-260215",
    "temperature": 0.7,
    "timeout": 600,
    "thinking": "disabled"
  },
  "sp": "你是教思AI教学助手..."
}
```

### 可用模型（扣子平台免费额度）

| 模型 | 特点 |
|------|------|
| `doubao-seed-2-0-pro-260215` | 旗舰级，复杂推理（默认） |
| `doubao-seed-2-0-lite-260215` | 均衡型，格式化用 |
| `doubao-seed-2-0-mini-260215` | 低延迟，简单任务 |
| `deepseek-v3-2-251201` | 平衡推理与输出长度 |
| `kimi-k2-5-260127` | 多模态，Agent 能力强 |

---

## 开发模式降级方案

当 `DEV_MODE=1` 时，系统自动启用以下降级：

| 组件 | 生产环境 | 开发降级 | 影响 |
|------|---------|---------|------|
| 数据库 | PostgreSQL | SQLite (`/tmp/vibe_coding_dev.db`) | 数据不跨会话持久化 |
| 状态检查点 | PostgresSaver | MemorySaver | 重启后状态丢失 |
| LLM 调用 | 扣子平台 API | 同生产（免费额度） | 无影响 |

---

## 常见问题

### Q: 预览显示 `{"detail":"Not Found"}`
**A**: 服务已启动但根路径未定义。检查 `main.py` 中是否有 `@app.get("/")` 路由和静态文件挂载。

### Q: 对话接口超时
**A**: 智能备课工作流涉及 11 个节点的 LLM 调用，总耗时约 60-120 秒。前端超时设置为 300 秒，请耐心等待。

### Q: 输出是 JSON 而不是 Markdown
**A**: 检查 `format_teaching_content()` 是否在 `openai_chat_completions` 中被调用。确保前端发送 `stream: false`。

### Q: `PGDATABASE_URL is not set`
**A**: 设置 `DEV_MODE=1` 环境变量启用 SQLite 降级，或配置真实的 PostgreSQL 连接串。

### Q: `ModuleNotFoundError: No module named 'xxx'`
**A**: 运行 `bash scripts/setup.sh` 重新安装依赖。如果遇到 `pycairo` 等系统库编译失败，这些是 GUI 依赖，后端服务不需要，可从 `pyproject.toml` 中移除。

### Q: 如何切换工作流？
**A**: 修改 `graphs/graph.py` 中的 `workflow` 参数：
```python
_wrapper = _GraphWrapper(workflow="simulation")  # 切换到教学推演
_wrapper = _GraphWrapper(workflow="growth")      # 切换到成长分析
```
