## 项目概述
- **名称**: vibe-coding
- **类型**: Web 服务（FastAPI HTTP 服务 + 前端页面）
- **描述**: 教思 AI 教学助手——课堂沙盘推演器，提供教案生成、课堂预演、盲区检测、学情推演、互动设计等「替老师思考」能力

## 技术栈
- **语言**: Python 3.12
- **框架**: FastAPI + uvicorn
- **AI 集成**: LangChain 1.0, LangGraph 1.0
- **依赖管理**: uv

## 目录结构
```
/workspace/projects/
├── .coze                    # 根配置（工作区入口）
├── AGENTS.md                # 项目规范文件
└── projects/                 # 技术项目根目录
    ├── .coze                # 子项目配置
    ├── src/
    │   ├── main.py          # 主入口（FastAPI app + 流式API + 教师配置API）
    │   ├── config/
    │   │   ├── __init__.py
    │   │   └── llm_config.py    # LLM 参数配置（3 种预设模板）
    │   └── graphs/
    │       ├── __init__.py
    │       ├── graph.py         # 图编译入口
    │       ├── state.py         # 简化 State 定义
    │       └── lesson_prep.py   # 3 节点流水线（router → generate → format）
    ├── assets/index.html     # 前端单页（教师面板 + 任务选择 + 流式渲染）
    ├── scripts/
    │   ├── setup.sh          # 依赖安装
    │   └── http_run.sh       # HTTP 服务启动（幂等，含端口清理）
    ├── pyproject.toml
    └── uv.lock
```

## 关键入口 / 核心模块
- **HTTP 入口**: `src/main.py`
- **启动命令**: `bash scripts/http_run.sh -p 5000`
- **依赖安装**: `bash scripts/setup.sh`
- **API 端点**:
  - `POST /v1/chat/completions` — OpenAI 兼容流式接口
  - `GET /api/teacher-config` — 教师配置选项（学科/年级/教学目标/重点/难点/时长/风格）
  - `GET /` — 前端页面
  - `GET /health` — 健康检查

## 运行与预览
- **端口**: 5000
- **预览能力**: 支持（Web 服务，`/` 返回前端页面）
- **部署方式**: HTTP 服务部署（`deploy.profile.kind=service, flavor=web`）

## 架构设计

### 3 节点流水线 + 多模式路由
```
intent_router → [chat] → chat_reply → format_output
             → [lesson_prep] → generate_lesson_plan → format_output
             → [classroom_sim] → simulate_classroom → format_output
             → [blind_spot] → detect_blindspots → format_output
             → [student_sim] → simulate_student_profiles → format_output
             → [interaction_design] → design_interactions → format_output
```
- **intent_router**: 根据 `mode` 字段路由到对应功能节点，`mode` 由前端显式传入
- **各功能节点**: 独立 prompt + 单次 LLM 调用，各节点互不依赖（为后续 subagent 并行扩展预留）
- **format_output**: 按 `mode` 选择不同格式化模板，统一 Markdown 输出
- **State 预留 `modes` 列表字段**：为后续 subagent 模式（多功能并行）预留，当前单功能模式下 `modes = [mode]`

### 功能模式
| mode | 节点 | 描述 |
|------|------|------|
| `lesson_prep` | generate_lesson_plan | 生成完整结构化教案 |
| `classroom_sim` | simulate_classroom | 预判课堂意外情境与应对策略 |
| `blind_spot` | detect_blindspots | 发现教案中的逻辑漏洞与认知跳步 |
| `student_sim` | simulate_student_profiles | 模拟优/中/困三层学生思维路径 |
| `interaction_design` | design_interactions | 设计师生互动方案和话术 |
| `chat` | chat_reply | 自由对话 |

### 流式输出架构
- 使用 `stream_mode=["messages", "updates"]` 双模式消费 LangGraph 流
- `messages` 模式：只放行 `chat_reply` 的 LLM token 流
- `updates` 模式：推送 `node_progress` 自定义 SSE 事件 + `format_output` 的完整教案 Markdown
- `text_sent_via_messages` 去重标记防止闲聊场景重复推送

### 前端参数化输入
- 左侧面板：7 个核心参数（学科、年级、教学目标、重点、难点、课时时长、教学风格）
- 每个参数支持「下拉选择 + 自定义输入」两种模式，点击切换按钮即可切换
- 顶部功能选择器：6 种功能模式一键切换（教案生成/课堂预演/盲区检测/学情推演/互动设计/自由对话）
- 功能模式通过 `extra_body.mode` 显式传入后端，后端根据 mode 路由
- 各功能模式下输入框变为"课题"输入，无需手写提示词

### LLM 参数配置
- `precise` (temp=0.3): 解析、校验等精确任务
- `creative` (temp=0.7): 教案生成、闲聊回复
- `chat` (temp=0.7, max_tokens=300): 简短闲聊

## 用户偏好与长期约束
1. Python 项目使用 `uv` 管理依赖
2. 子项目位于 `projects/` 子目录
3. 工作区根目录 `.coze` 是平台读取的唯一入口
4. `project_type = "web"`，`preview_enable = "enabled"`，根和子项目 `.coze` 必须一致
5. `cozeloop` 版本需 >= 0.1.28 以兼容 LangChain 1.0+

## 常见问题和预防
1. 根 `.coze` 必须存在且配置正确
2. 子项目 `.coze` 必须包含 `sub_id` 字段
3. `project_type` 和 `preview_enable` 必须在根和子项目 `.coze` 中保持一致
4. **cozeloop 兼容性**：LangChain 1.0 移除了 `langchain.callbacks` 模块，需要 `cozeloop >= 0.1.28` 才能兼容
5. **http_run.sh 幂等性**：脚本启动前会 `fuser -k` 清理端口残留进程，确保重复执行不会冲突
6. **闲聊场景 format_output**：`node_format_output` 在 `mode == "chat"` 时直接透传 `chat_reply` 的消息，不生成其他模板
7. **mode 路由**：功能模式由前端 `extra_body.mode` 显式传入，`intent_router` 直接读取 `state.mode` 做路由，不依赖关键词猜测
8. **subagent 扩展预留**：State 中预留 `modes: list[str]` 字段，当前单功能模式下 `modes = [mode]`，后续 subagent 模式可传入多个 mode 并行执行
7. **教师信息注入**：前端通过 `extra_body` 传递备课参数（学科/年级/教学目标/重点/难点/课时时长/教学风格），后端在 `stream_input` 中注入，`generate_lesson_plan` 节点从 state 中读取并嵌入 prompt
8. **教案生成耗时**：单次 LLM 调用约 10-30 秒完成完整教案，远快于原 11 节点串行方案的 2-5 分钟
