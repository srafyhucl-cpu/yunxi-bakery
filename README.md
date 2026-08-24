# 芸熙烘焙智能经营平台

一个基于 AI 的烘焙店智能客服与经营系统。

## 项目结构

- **backend/** - FastAPI 后端服务（Python 3.11+）
- **miniapp/** - 微信小程序前端（TypeScript）
- **docs/** - 统一文档中心
- **scripts/** - 跨项目脚本和工具

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Git

### 后端开发

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 7001 --reload
```

访问：http://127.0.0.1:7001/docs

### 小程序开发

```bash
cd miniapp
npm install
# 用微信开发者工具打开 miniapp 目录
```

## 文档导航

- [架构说明](docs/architecture/) - 系统架构和设计决策
- [API 契约](docs/api-contracts/) - 前后端接口规范
- [开发规范](AGENTS.md) - AI 协作和编码规范
- [变更日志](LOGBOOK.md) - 项目演进记录
- [进度清单](项目进度与配置清单.md) - 当前版本和待办事项

## 重要文档

- [项目重构与推进计划书](项目重构与推进计划书.md) - 战略规划和路线图
- [执行指南](EXECUTION-GUIDE.md) - Monorepo 整合说明

## 部署

生产部署见 [scripts/deploy.sh](scripts/deploy.sh)

## 技术栈

**后端**：
- FastAPI - Web 框架
- SQLite - 数据库
- LangChain - AI 应用框架
- Pydantic - 数据验证

**前端**：
- 微信小程序原生框架
- TypeScript
- 微信开放能力

## 项目状态

- 当前版本：v0.1.0（MVP 开发阶段）
- 目标上线：2027 年 6 月
- 商业状态：单店铺试用，未来可能扩展多租户

## Monorepo 整合说明

本仓库由以下两个项目合并而成：
- YunxiBakeBot（后端 Platform）
- YunxiBakeMiniApp（小程序 Storefront）

整合日期：2026-08-17
