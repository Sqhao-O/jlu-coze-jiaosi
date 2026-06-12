## 项目概述
- **名称**: vibe-coding
- **类型**: Web 服务（FastAPI HTTP 服务 + 前端页面）
- **描述**: 教思 AI 教学助手——课堂沙盘推演器，提供教案生成、课堂预演、盲区检测、学情推演、互动设计、智能命题、知识库问答等「替老师思考」能力

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
    │       └── lesson_prep.py   # 多节点流水线（router → 功能节点 → format）
    ├── src/knowledge/
    │   │   ├── __init__.py
    │   │   ├── vector_store.py   # 向量存储抽象层（内存降级）
    │   │   ├── parser.py         # 文档解析（PDF/Word/Excel/PPT/TXT）
    │   │   ├── chunker.py        # 文本分块（段落感知+滑动窗口）
    │   │   ├── embedder.py       # 向量化 + 检索（EmbeddingClient）
    │   │   └── store.py          # 知识库元数据 CRUD
    │   ├── src/api/
    │   │   ├── __init__.py
    │   │   └── knowledge.py      # 知识库管理 API 路由
    ├── src/utils/
    │   ├── json_parser.py     # LLM 输出 JSON 解析
    │   └── ppt_client.py      # Coze Doc Maker 工作流调用客户端（已停用，保留备用）
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
  - `GET /api/teacher-config` — 教师配置选项（学科/年级/教学目标/重点/难点/时长/风格/功能模式）
  - `GET /api/knowledge-bases` — 知识库列表
  - `POST /api/knowledge-bases` — 创建知识库
  - `DELETE /api/knowledge-bases/{kb_id}` — 删除知识库
  - `GET /api/knowledge-bases/{kb_id}/documents` — 知识库文档列表
  - `POST /api/knowledge-bases/{kb_id}/upload` — 上传文档（解析→分块→向量化）
  - `DELETE /api/knowledge-bases/{kb_id}/documents/{doc_id}` — 删除文档
  - `POST /api/knowledge-bases/{kb_id}/search` — 语义检索
  - `GET /` — 前端页面
  - `GET /health` — 健康检查

## 运行与预览
- **端口**: 5000
- **预览能力**: 支持（Web 服务，`/` 返回前端页面）
- **部署方式**: HTTP 服务部署（`deploy.profile.kind=service, flavor=web`）
- **预览判定依据**: FastAPI HTTP 服务 + 前端页面，核心交互需通过浏览器验证，属于 Web 预览型项目
- **预览链路**: `[dev].build` → `setup.sh`（uv sync 安装依赖）→ `[dev].run` → `http_run.sh`（清理端口 → 激活 .venv → 启动 uvicorn）
- **.coze 映射**: 根 `.coze`（`/workspace/projects/.coze`）通过 `projects/scripts/` 相对路径调度子项目脚本；子项目 `.coze`（`projects/.coze`）使用 `scripts/` 相对路径；两边 `[dev]`/`[deploy]` 命令实际指向同一套脚本，仅路径前缀不同
- **沙箱重置注意**: 每次新会话 `.venv` 会被清除，预览启动时 `[dev].build` 会自动重新安装依赖，无需手动处理

## 架构设计

### 3 节点流水线 + 多模式路由 + RAG 通用增强
```
intent_router → rag_enrich → [chat] → chat_reply → format_output
                          → [lesson_prep] → generate_lesson_plan → format_output
                          → [classroom_sim] → simulate_classroom → format_output
                          → [blind_spot] → detect_blindspots → format_output
                          → [student_sim] → simulate_student_profiles → format_output
                          → [interaction_design] → design_interactions → format_output
                          → [exam_gen] → generate_exam → format_output
                          → [ppt_gen] → generate_ppt → format_output
```
- **intent_router**: 根据 `mode` 字段路由到对应功能节点，`mode` 由前端显式传入
- **rag_enrich**: RAG 上下文增强层，位于 router 和功能节点之间；`knowledge_base_id` 非空时检索知识库，将相关片段写入 `_knowledge_context`；为空时直接透传，不检索、不注入
- **各功能节点**: 独立 prompt + 单次 LLM 调用；自动从 `_knowledge_context` 读取检索结果注入 System Prompt（无知识库时不注入）
- **format_output**: 按 `mode` 选择不同格式化模板，统一 Markdown 输出；有 RAG 上下文时追加 `📖 参考了知识库中 N 条相关内容`
- **State 预留 `modes` 列表字段**：为后续 subagent 模式（多功能并行）预留，当前单功能模式下 `modes = [mode]`

### 功能模式
| mode | 节点 | 描述 |
|------|------|------|
| `lesson_prep` | generate_lesson_plan | 生成完整结构化教案 |
| `classroom_sim` | simulate_classroom | 预判课堂意外情境与应对策略 |
| `blind_spot` | detect_blindspots | 发现教案中的逻辑漏洞与认知跳步 |
| `student_sim` | simulate_student_profiles | 模拟优/中/困三层学生思维路径 |
| `interaction_design` | design_interactions | 设计师生互动方案和话术 |
| `exam_gen` | generate_exam | 一键生成结构化试题（多题型+分层难度+答案评分标准） |
| `ppt_gen` | generate_ppt | 一键生成 PPT 课件大纲 |
| `chat` | chat_reply | 自由对话 |

### RAG 通用增强
- **位置**: `rag_enrich` 节点，位于 `intent_router` 和所有功能节点之间
- **触发条件**: `knowledge_base_id` 非空时检索，为空时直接透传
- **检索策略**: 用用户 query + 课题组合检索，top-3 chunks，余弦相似度
- **注入方式**: 各功能节点和 chat_reply 的 System Prompt 末尾追加 `KNOWLEDGE_CONTEXT_TEMPLATE`
- **输出标注**: `format_output` 中有 RAG 上下文时追加 `📖 参考了知识库中 N 条相关内容`
- **前端交互**: 知识库面板始终显示（左侧面板下方），不限于特定 mode

### 流式输出架构
- 使用 `stream_mode=["messages", "updates"]` 双模式消费 LangGraph 流
- `messages` 模式：只放行 `chat_reply` 的 LLM token 流
- `updates` 模式：推送 `node_progress` 自定义 SSE 事件 + `format_output` 的完整教案 Markdown
- `text_sent_via_messages` 去重标记防止闲聊场景重复推送

### 前端参数化输入
- 左侧面板：7 个核心参数（学科、年级、教学目标、重点、难点、课时时长、教学风格）
- 每个参数支持「下拉选择 + 自定义输入」两种模式，点击切换按钮即可切换
- 顶部功能选择器：7 种功能模式一键切换（教案生成/课堂预演/盲区检测/学情推演/互动设计/智能命题/PPT大纲）
- 知识库面板始终显示在左侧面板下方，选择知识库后所有模式自动启用 RAG 上下文增强
- 功能模式通过 `extra_body.mode` 显式传入后端，后端根据 mode 路由
- 各功能模式下输入框变为"课题"输入，无需手写提示词

### 聊天记录与上下文
- **localStorage 持久化**：所有聊天记录按会话 ID 存储，刷新页面不丢失
- **上下文联动**：发送消息时携带完整历史 messages，LLM 可理解前文内容
- **会话管理**：左侧边栏显示历史会话列表，可切换、可删除单条、可一键清除全部
- **清除全部按钮**：位于"新建对话"按钮旁，点击后确认清除所有历史记录

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
6. **沙箱重置自愈**：`setup.sh` 和 `http_run.sh` 均内置 `ensure_uv` 函数，沙箱重置后 uv 和 .venv 被清除时自动重装 uv 并重新安装依赖，无需手动干预
7. **闲聊场景 format_output**：`node_format_output` 在 `mode == "chat"` 时直接透传 `chat_reply` 的消息，不生成其他模板
8. **mode 路由**：功能模式由前端 `extra_body.mode` 显式传入，`intent_router` 直接读取 `state.mode` 做路由，不依赖关键词猜测
9. **subagent 扩展预留**：State 中预留 `modes: list[str]` 字段，当前单功能模式下 `modes = [mode]`，后续 subagent 模式可传入多个 mode 并行执行
10. **教师信息注入**：前端通过 `extra_body` 传递备课参数（学科/年级/教学目标/重点/难点/课时时长/教学风格），后端在 `stream_input` 中注入，`generate_lesson_plan` 节点从 state 中读取并嵌入 prompt
11. **教案生成耗时**：单次 LLM 调用约 10-30 秒完成完整教案，远快于原 11 节点串行方案的 2-5 分钟
12. **知识库 RAG 架构**：`rag_enrich` 节点统一检索，位于 `intent_router` 和所有功能节点之间；`knowledge_base_id` 非空时检索知识库相关内容注入 `_knowledge_context`，为空时跳过；各功能节点和 chat_reply 自动从 `_knowledge_context` 读取并注入 System Prompt；检索使用 `coze-coding-dev-sdk.EmbeddingClient` 向量化 + 内存向量库（InMemoryVectorStore）余弦相似度检索；元数据用 JSON 文件持久化（`.knowledge_meta/`）；向量数据内存存储（`.knowledge_vectors/` 缓存）
13. **EmbeddingClient 限制**：`embed_texts` 批量接口只返回单个向量，必须逐个调用 `embed_text`；向量维度 2048
14. **python-multipart 依赖**：知识库文件上传需要 `python-multipart`，已加入 `pyproject.toml`
15. **前端知识库面板样式统一**：知识库面板与备课参数面板使用一致的暗色主题（标题 13px/sidebar-muted/uppercase、select 暗色背景 rgba、按钮暗色、边框 rgba(255,255,255,0.08)），不再使用浅色 CSS 变量
16. **前端 MODES 与后端同步**：前端 JS 默认 MODES 数组包含全部 8 种模式（含 ppt_gen），与后端 TEACHER_CONFIG.modes 一致
17. **知识库面板可折叠**：标题区域可点击折叠/展开，节省侧边栏空间
18. **RAG 启用提示**：选中知识库后显示绿色提示条「已启用知识库增强」，取消选择后自动隐藏
19. **新建知识库弹窗暗色适配**：弹窗背景、输入框、按钮均使用暗色主题，与侧边栏风格统一
20. **部署环境只读文件系统**：veFaaS 部署环境文件系统为只读，`http_run.sh` 通过 `is_deploy_env()` 检测（`PIP_TARGET` 已设置 或 项目目录不可写），跳过 `.venv` 创建，直接使用构建阶段通过 `PIP_TARGET` 安装到系统路径的依赖；`DEV_MODE` 也不在部署环境设置
