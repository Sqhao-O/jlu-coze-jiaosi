## 项目概述
- **名称**: vibe-coding
- **类型**: Python 后端服务（FastAPI HTTP 服务）
- **描述**: Coze Vibe Coding 项目，提供 HTTP API 服务

## 技术栈
- **语言**: Python 3.12
- **框架**: FastAPI + uvicorn
- **AI 集成**: LangChain, LangGraph
- **数据库**: PostgreSQL (SQLAlchemy + Alembic)
- **依赖管理**: uv

## 目录结构
```
/workspace/projects/
├── .coze                    # 根配置（工作区入口）
└── projects/                 # 技术项目根目录
    ├── .coze                # 子项目配置
    ├── src/main.py          # 主入口
    ├── scripts/             # 运行脚本
    │   ├── setup.sh        # 依赖安装
    │   ├── http_run.sh     # HTTP 服务启动
    │   └── ...
    ├── pyproject.toml
    └── uv.lock
```

## 关键入口 / 核心模块
- **HTTP 入口**: `src/main.py`
- **启动命令**: `bash scripts/http_run.sh -m http -p 5000`
- **依赖安装**: `bash scripts/setup.sh`

## 运行与预览
- **端口**: 5000
- **预览能力**: 不支持（后端服务项目）
- **部署方式**: HTTP 服务部署

## 用户偏好与长期约束
1. Python 项目使用 `uv` 管理依赖
2. 子项目位于 `projects/` 子目录
3. 工作区根目录 `.coze` 是平台读取的唯一入口

## 常见问题和预防
1. 根 `.coze` 必须存在且配置正确
2. 子项目 `.coze` 必须包含 `sub_id` 字段
3. `project_type` 和 `preview_enable` 必须在根和子项目 `.coze` 中保持一致
