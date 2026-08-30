# 芸熙烘焙智能经营平台（YunxiBakery Monorepo）

自研烘焙电商 + AI 客服平台（替代有赞）：FastAPI 后端 + 微信原生小程序（TypeScript）。

## 迷路先看这里

- [PROJECT-STATE.md](PROJECT-STATE.md) — **唯一状态入口**：项目定位、时间线（P0 整合 ✅ → P0.5 资产迁移 ✅ → P1 承接验证技术完成、阶段关闭待负责人确认 → ▶ P2 试运行准备 → P3 上线准备）、资产地图、范围修正与遗留事项。
- [docs/待办优先级清单_20260829.md](docs/待办优先级清单_20260829.md) — P0/P1/P2/P3 待办与依赖关系。
- 版本以 `backend/VERSION` 为准；目标上线 2027-06（最早候选窗口，不是自动上线日期）。
- 项目红线：截至 2027-05-31（含）小程序仅用于开发、调试和测试，不向真实用户开放；P2 实测启动、真实微信支付、真实数据导入均需项目负责人明确批准。详见 [PROJECT-STATE.md](PROJECT-STATE.md) 与 [AGENTS.md](AGENTS.md)。

## 项目结构

- **backend/** - FastAPI 后端服务（Python 3.11+，16 服务域，canonical 路径 `backend/app/api/channels/storefront/` 等）
- **miniapp/** - 微信小程序前端（TypeScript，15 页面 M1-M5）
- **docs/** - 统一文档中心（含归档区 `docs/archive/`）
- **scripts/** - monorepo 级脚本；后端脚本在 `backend/scripts/`
- 根目录：`AGENTS.md`（AI 协作规范）、`LOGBOOK.md`（演进编年史）、`PROJECT-STATE.md`（状态入口）、`项目进度与配置清单.md`（版本与生产同步记录）

## 快速开始

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

- [docs/README.md](docs/README.md) — 文档中心导航（含 `docs/archive/` 归档区说明）
- [AGENTS.md](AGENTS.md) — AI 协作与编码规范
- [docs/AGENTS/multi-agent-coordination.md](docs/AGENTS/multi-agent-coordination.md) — 多 Agent 权威源、状态快照和并行边界
- [LOGBOOK.md](LOGBOOK.md) — 项目演进唯一真实编年史
- [docs/harness-engineering/README.md](docs/harness-engineering/README.md) — Harness Engineering 总入口（追溯、验证矩阵、防重犯、交接）
- [docs/AGENT-HANDOFF-20260829.md](docs/AGENT-HANDOFF-20260829.md) — 最新结构化交接文档
- [项目重构与推进计划书.md](项目重构与推进计划书.md) — v1.0 战略文档（历史；附录D 载有 v1.2 范围修正）
- [docs/archive/](docs/archive/) — 已废弃方向与已执行完毕文档的归档区

## 部署

生产部署入口与服务器布局见 [docs/release/server-layout.md](docs/release/server-layout.md)。

## 技术栈

- **后端**：FastAPI、SQLite、LangChain + LangGraph（AI 应用层编排）、Pydantic；检索为 BM25 关键词路径（向量路径战略禁用）
- **前端**：微信原生小程序、TypeScript、微信开放能力
- **质量门禁**：`.pre-commit-config.yaml`（密钥扫描、红线自测、核心测试等 7 钩子）；全量验证入口见 `docs/AGENTS/quick-reference.md`

## Monorepo 整合说明

本仓库于 2026-08-17 由 YunxiBakeBot（后端 Platform）与 YunxiBakeMiniApp（小程序 Storefront）合并而成；整合执行记录归档于 [docs/archive/p0-monorepo-20260817/](docs/archive/p0-monorepo-20260817/)。旧仓 `D:\Project\YunxiBakeBot`（冻结，只读，永不删）与过期副本 `D:\Project\YunxiBakeMiniApp`（停用）不再作为任何工作的执行依据。
