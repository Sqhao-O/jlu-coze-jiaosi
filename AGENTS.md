## 项目概述
- **名称**: vibe-coding
- **类型**: Web 服务（FastAPI HTTP 服务 + 前端页面）
- **描述**: Coze Vibe Coding 项目，提供 HTTP API 服务及 Web 前端页面

## 技术栈
- **语言**: Python 3.12
- **框架**: FastAPI + uvicorn
- **AI 集成**: LangChain 1.0, LangGraph 1.0
- **数据库**: PostgreSQL (SQLAlchemy + Alembic)，开发/预览环境降级为 SQLite
- **依赖管理**: uv

## 目录结构
```
/workspace/projects/
├── .coze                    # 根配置（工作区入口）
├── AGENTS.md                # 项目规范文件
└── projects/                 # 技术项目根目录
    ├── .coze                # 子项目配置
    ├── src/main.py          # 主入口
    ├── scripts/             # 运行脚本
    │   ├── setup.sh        # 依赖安装
    │   ├── http_run.sh     # HTTP 服务启动（幂等，含端口清理）
    │   └── ...
    ├── pyproject.toml
    └── uv.lock
```

## 关键入口 / 核心模块
- **HTTP 入口**: `src/main.py`
- **启动命令**: `bash scripts/http_run.sh -p 5000`
- **依赖安装**: `bash scripts/setup.sh`

## 运行与预览
- **端口**: 5000
- **预览能力**: 支持（Web 服务，`/` 返回前端页面）
- **部署方式**: HTTP 服务部署（`deploy.profile.kind=service, flavor=web`）

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
4. **数据库降级**：`db.py` 中 `get_db_url()` 在 `get_project_env_vars()` 失败时不再抛异常，而是返回空字符串，由 `_create_engine_with_retry()` 根据 `DEV_MODE` 环境变量决定是否降级为 SQLite
5. **cozeloop 兼容性**：LangChain 1.0 移除了 `langchain.callbacks` 模块，需要 `cozeloop >= 0.1.28` 才能兼容
6. **http_run.sh 幂等性**：脚本启动前会 `fuser -k` 清理端口残留进程，确保重复执行不会冲突
