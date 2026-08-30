# 项目状态活页（PROJECT STATE）

> **这是唯一的项目状态入口**。每周收口时由 AI 员工更新，架构师复核。
> 迷路时先看这里，不要去翻计划书和历史文档。
> 中文优先：人类可读内容使用中文；`task_id`、`trace_id`、`status`、`owner`、`branch`、`as_of_commit`、`version` 和路径保持稳定机器字段。
> 最小阅读集：所有 Agent 先读 `AGENTS.md` 与本文件；执行具体任务时再读对应 `docs/tasks/*.md`，按需读取专业契约。

**最后更新**：2026-08-30（as_of_commit: `4ee06c8`；version: `0.133.0-p2trial.3`）

> 当前状态口径：P1 承接验证技术工作已完成，阶段关闭待项目负责人确认；P2 准备段已完成，真人执行段尚未启动。版本号以 `backend/VERSION` 为准，代码快照以当前 `git rev-parse HEAD` 为准。

<!-- PROJECT_STATE_MACHINE_START -->
## 机器快照（当前事实）

```yaml
updated_at: 2026-08-30
as_of_commit: 4ee06c8
version: 0.133.0-p2trial.3
current_branch: main
workspace_state: dirty
state_owner: 项目负责人＋AI 员工
```

`workspace_state: dirty` 表示当前工作区包含尚未提交的治理文档、归档移动和任务文件；不得据此宣称已提交或已推送。

## 主线任务总表（唯一动态明细源）

| task_id | 任务 | status | 优先级 | owner | branch | as_of_commit | 依赖 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|---|
| T-P0-MONOREPO | Monorepo 整合与架构收口 | completed | P0 | 项目负责人＋AI 员工 | main | 1c2a3ea | — | LOGBOOK: 20260817 | 保持主线基线可复现 |
| T-P05-ASSET-MIGRATION | 凭证、知识和商品资产迁移 | completed | P0 | AI 员工 | main | 4ee06c8 | T-P0-MONOREPO | PROJECT-STATE 状态记录 | 仅按正式流程处理客户数据 |
| T-P1-ACCEPTANCE | P1 全模块承接验证 | pending | P0 | 项目负责人 | main | 4ee06c8 | T-P05-ASSET-MIGRATION | LOGBOOK: 20260825-p1-wrap | 等负责人确认阶段关闭 |
| T-P2-PREP | P2 试运行准备段 | completed | P0 | AI 员工 | main | 4ee06c8 | T-P1-ACCEPTANCE | LOGBOOK: 20260826-p2trial-sim-fixes | 维持真人执行前门禁 |
| T-P2-RUN | P2 真人执行段（B/C/D/E） | blocked | P0 | 项目负责人＋AI 员工 | main | 4ee06c8 | T-P1-ACCEPTANCE,T-P2-PREP | docs/specs/2026-08-25-p2-manual.md | 获负责人批准后按手册执行 |
| T-P1-4-KNOWLEDGE | 知识缺口枚举与回填 | pending | P1 | AI 员工＋项目负责人 | main | 4ee06c8 | T-P2-RUN | docs/tasks/20260829-P1-4-知识缺口回填-指令.md | 先枚举并提交口径确认 |
| T-P1-5-INVOICE | 发票承接专用测试与 E2E 验收 | pending | P1 | AI 员工 | main | 4ee06c8 | T-P2-PREP | docs/tasks/20260829-P1-5-发票承接验收-指令.md | 补测试并记录 E1-E4 |
| T-P1-6-SIMULATOR | 模拟器 B/C/D/E 走查 | blocked | P1 | AI 员工＋项目负责人 | main | 4ee06c8 | T-P2-RUN | docs/tasks/20260829-P1-6-模拟器BCDE走查-指令.md | 等真人授权和测试号条件 |
| T-P1-7-FAQ | FAQ 10 条店家事实回收 | blocked | P1 | AI 员工＋店家 | main | 4ee06c8 | T-P2-RUN | docs/tasks/20260829-P1-7-FAQ回收-指令.md | 发出填写版并等待店家答复 |
| T-P3-SEARCH | 商品搜索入口增强 | deferred | P3 | 项目负责人 | main | 4ee06c8 | T-P2-RUN | PROJECT-STATE 风险记录 | P2 稳定后重新排期 |
| T-D1-REVIEW | D1 账务核心独立审阅轨道 | deferred | P3 | 项目负责人 | external:D:\Project\YunxiBakeBot | 7afd44b | T-P0-MONOREPO | docs/archive/ 与旧仓记录 | 仅获批准时审阅，不合入主线 |
| T-P0-1-CHAT-TIMEOUT | 小程序 AI 聊天超时守卫 | historical | P0 | AI 员工 | main | 4ee06c8 | T-P2-PREP | docs/tasks/20260829-P0-1-指令.md | 仅供复盘，不得重执行 |
| T-HARNESS-REGISTER | 中文优先 Harness 与开发总表 | completed | P0 | 项目负责人＋AI 员工 | main | 4ee06c8 | T-P0-1-CHAT-TIMEOUT | 本轮 trace: 20260829-project-development-register-and-chinese-governance；开发总表守卫与边界测试 EXIT=0 | 保持总表守卫随任务状态同步 |
| T-HARNESS-EVIDENCE-INDEX | 历史证据索引来源与统计口径收敛 | completed | P0 | AI 员工 | main | 4ee06c8 | T-HARNESS-REGISTER | trace: 20260830-evidence-index-origin-and-summary；来源冲突回归已修复；摘要 total=363、failed=0 | 后续新证据显式声明 repository_origin；历史条目按来源只读核验 |
| T-HARNESS-RUNTIME-CLEANUP | 质量门禁临时目录与跨 PowerShell 清理收口 | completed | P0 | AI 员工 | main | 4ee06c8 | T-HARNESS-EVIDENCE-INDEX | 本轮 trace: 20260830-harness-runtime-cleanup-and-closeout；E-20260830-002；专项测试与双 PowerShell 预览 EXIT=0 | 后续新增质量门禁继续复用 D 盘一次性临时目录 |

## 状态视图（只引用主表 task_id）

### 已完成（completed）

`T-P0-MONOREPO`、`T-P05-ASSET-MIGRATION`、`T-P2-PREP`、`T-HARNESS-REGISTER`、`T-HARNESS-EVIDENCE-INDEX`、`T-HARNESS-RUNTIME-CLEANUP`

### 进行中（active）

暂无。

### 未完成（pending / blocked / deferred）

`T-P1-ACCEPTANCE`（pending，待负责人确认）、`T-P2-RUN`（blocked，待负责人批准）、`T-P1-4-KNOWLEDGE`（pending，先枚举）、`T-P1-5-INVOICE`（pending，补测试）、`T-P1-6-SIMULATOR`（blocked，真人授权/测试号）、`T-P1-7-FAQ`（blocked，店家答复）、`T-P3-SEARCH`（deferred，P2 后排期）、`T-D1-REVIEW`（deferred，外部冻结轨道）。

### 历史（historical）

`T-P0-1-CHAT-TIMEOUT`：已完成任务指令快照，不能作为当前执行入口。

## 分支与开发轨道登记

| branch_or_track | 类型 | 状态 | 用途 | 基线 | owner | 绑定任务 |
|---|---|---|---|---|---|---|
| main | 本仓 Git 分支 | 当前 | Monorepo 唯一开发主线 | 4ee06c8 | 项目负责人 | 全部主线任务 |
| D:\Project\YunxiBakeBot | 外部历史轨道（非 Git 分支） | 冻结 | D1 审阅与历史证据 | 7afd44b | 项目负责人 | T-D1-REVIEW |
| D:\Project\YunxiBakeMiniApp | 外部过期副本（非 Git 分支） | 停用 | 迁移前参考，不得开发 | 历史快照 | 项目负责人 | — |

不存在的本地或远端分支不登记为事实；候选分支只能在任务说明中描述，不能放入本表。
<!-- PROJECT_STATE_MACHINE_END -->

---

## 一句话定位

**自研烘焙电商 + AI 客服平台（有赞替代）：完整承接已建成的全部模块，2027 年 6 月为最早候选上线窗口，非自动上线日期。**

小程序当前跑在有赞上，本项目是替代方案——电商、会员、积分、券、储值、AI 客服**全部在范围内，不可砍**。

---

## 当前位置（时间线）

```
P0 整合 ✅ → P0.5 资产迁移 ✅ → P1 承接验证 ✅（技术完成；阶段关闭待负责人确认）
                                    ↓
▶ P2 试运行准备完成（准备段完成 ✅ / 等待项目负责人组织真人执行段（未确认前不启动实测）后方可启动 P2 实测）
                                    ↓
   P3 上线准备 → 2027-06 最早候选上线窗口（须负责人批准，非自动上线）
```

> **【关键】未获项目负责人确认前，不得擅自启动 P2 实测。**

---

## 资产地图（东西都在哪）

| 资产 | 位置 | 状态 |
|------|------|------|
| **代码主线（唯一开发场所）** | `D:\Project\YunxiBakery` | ✅ 后端 16 服务域 + 小程序 15 页面，**M1-M5 全部模块已在基线中** |
| 旧仓全量历史 + D1 存档 | `D:\Project\YunxiBakeBot` | 🔒 冻结，只读，永不删 |
| 凭证（有赞/企微/AI 全套） | 旧仓 `.env` → 复制到新仓 `backend/.env`（本地，不入库） | ✅ 已迁移并实测连通（有赞 token 刷新+商品拉取、企微 token 刷新均通过） |
| 业务知识（638 条，含 24 条人工沉淀） | 旧仓 `bot.db` → 新仓 24 条人工沉淀已迁入 | ✅ 迁移完成，BM25 检索命中验证通过 |
| 客户数据（2.4 万条） | 仅存在于旧仓 bot.db | ⛔ 永不复制进新仓，未来走正式导入流程 |
| 商品快照（614 条） | 旧库 | ✅ **已真实同步 309 条在售**（2026-08-25；旧 614 为历史快照含已下架，309 为当前在售真实口径，与有赞后台一致） |

---

## 范围修正记录（v1.2，2026-08-24）

- **撤回** v1.0 计划书中"小程序端推迟/积分/储值/优惠券推迟 v2.0"——这些是有赞替代核心，必须完全承接
- **继续推迟**：D1 账务核心（留在旧仓审阅分支独立轨道）、真实微信支付（按既有门禁）、客户群运营增强
- P1 从"开发三大功能"改为"**全模块承接验证**"——验证已有模块，不开发新功能

## 优先级调整记录（v1.3，2026-08-25，项目负责人决策）

- **主线调整为 MiniApp 承接优先**：P1 的 Phase C（跨端链路）提前为当前焦点；微信开发者工具安装 + 真机走查 + 数据接通作为关键路径
- **知识缺口回填降级**：5 条 production 缺口（knowledge_gaps）+ FAQ 补充均**不阻塞**——转人工链路已验证可用（Phase A），缺口全部由转人工兜底，回填排入 P2 试运行前
- **依据**：知识缺口=内容问题（低风险，可兜底）；MiniApp=替代有赞的核心（高风险，不可拖）

## 状态校准记录（v1.4，2026-08-25，项目负责人三条件核实）

| 原状态 | 校准后 | 说明 |
|--------|--------|------|
| ⛔ 微信开发者工具 BLOCKED（Phase B 误判：仅探测 Program Files 目录） | ✅ **工具已安装并登录**（本机长期存在） | Phase B 实机走查 + Phase C 阻塞**全部解除**；此为探测方法缺陷，记入任务包问题区 #7 并补充探测范围 |
| 数据策略未定（A mock / B 真实待选） | ✅ **B：真实有赞数据**，本机出口 IP `10.161.106.143` 已加有赞白名单 | 商品同步走真实链路；如同步时遇 60020，回读实际出口 IP 与白名单核对（`10.x` 为内网段，需确认 NAT 后出口 IP） |
| 微信支付商户号未知 | 📅 **暂无，申请流程流转中** | 支付环节以 mock 为准（ALLOW_MOCK_PAYMENT 本地开启）；商户号通过后真实支付/退款按既有受控门禁执行（授权测试账号+小额+对账+清理） |

---

## 已完成

- [x] Monorepo 整合 + 架构评审修正（2026-08-17）
- [x] 基线冒烟 4 项实证（2026-08-24）
- [x] BM25 关键词检索落地，向量路径战略禁用
- [x] 7 钩子 pre-commit + push 回读规范
- [x] 旧库资产盘点 + MVP 范围修正 v1.2（小程序/会员模块回归范围）
- [x] 有赞真实商品同步：309/309 在售全量入柜（2026-08-25，无 IP 拦截）
- [x] 有赞功能对标表·证据版（2026-08-25）：核心链路全满足，唯一真缺口=发票（已定方案，见下），负证据判定 4 项不承接（评价/会员等级/营销/物流卡片）
- [x] 发票承接实现落地（commit `e2639d4`）：知识话术+转人工+后台人工登记；专用测试与端到端验收待完成
- [x] Phase C 第三步跨端全链路闭环（2026-08-25）：真实商品下单/支付/详情/取消拦截；发票 #9566 命中（验收第 1 条过）；#9 iOS 日期修复（单测 5/5）；#10 诊断完成（limit 未透传恒 50 + 分类语义混用 + 分类表 0 条，修复方案待产品决策）

## 进行中 / 阻塞

| 事项 | 状态 | 等谁 |
|------|------|------|
| 资产迁移（凭证+知识） | ✅ 完成（2026-08-24） | — |
| P1 Phase A 后端 API 冒烟 + 数据隔离 | ✅ 完成（2026-08-25） | — |
| P1 Phase B 静态检查（四项全过） | ✅ 完成；实机走查误报已解除 | — |
| ▶ **P2 准备段：真人执行前置** | 准备段完成；真人执行段待负责人批准，测试号体验版能力仍阻塞 | AI 员工 + 项目负责人 |
| 商品真实同步（有赞在售商品） | ✅ 完成 309/309（2026-08-25，真实凭证无 IP 拦截，双轨落库 youzan_products + knowledge_base product 各 309） | — |
| 知识缺口回填（5 条 + FAQ 补充） | ⏸ **降级不阻塞**——转人工兜底已验证，排 P2 试运行前 | — |
| 发票承接（后台人工登记） | ✅ 代码已落地（`e2639d4`）；专用测试与 E2E 验收待完成 | AI 员工 |
| 商品搜索入口 | 📋 P3 增强（309 SKU 无搜索，后端参数现成） | — |
| ▶ **P1 阶段收尾（T-P1-WRAP-01）** | 🔄 四个小项已全部执行完（①limit 500 常量+回归 311 ②#13 API 不可行+兜底落地 ③口径核对 ④收口登记） | AI 员工 |
| **P1 阶段关闭** | ⏳ **待项目负责人确认**（确认后进入 P2 试运行准备） | 项目负责人 |

## 下一步顺序

1. ✅ 商品真实数据同步（309/309）
2. ✅ Phase B 实机走查（15/15 页面导航渲染成功，95 页走查报告入库；发现 P2×2：#9 日期 iOS 兼容 / #10 商品可见范围）
3. ✅ **Phase C 第三步：跨端全链路闭环**（真实商品 + mock 支付）——下单/支付/详情/取消拦截闭环；发票 #9566 命中（验收第 1 条过）；#9 已修复（单测 5/5）；#10 诊断完成（limit 未透传恒 50 为主因 + 分类语义混用 + 分类表 0 条因同步未采集，修复方案待产品决策）
4. ✅ **Phase D 修复三连**（limit 透传 / 分类语义 / 分类采集）+ 结算三分支补证
5. ▶ **P1 收尾四小项**（①limit 魔法数字 ②#13 分类关联兜底 ③商品口径核对 ④收口登记）——已执行完成，**P1 关闭待项目负责人确认**
6. 阶段评审 → P2 试运行前：知识缺口回填 + 发票专用测试/E2E 验收

## 状态记录（v16，2026-08-25，P1 收尾请求确认）

- P1 四小项（T-P1-WRAP-01）已全部执行并有独立可复现证据（命令输出/DB 查询）：①`GET /products?limit=500` → 311 条（default 仍 50）；②#13 有赞 item.get/onsale 无 classification 字段（深度遍历零命中）+ 兜底文案已落地（"该分类暂无商品/查看全部"）；③库 311 vs 有赞在售 310（差集仅 5811485729 已下架残留，0 缺）——"309 全量"为首次同步快照口径；④LOGBOOK trace 20260825-p1-wrap。
- **P1 阶段关闭：待确认**——负责人确认后标注关闭并进入 P2 试运行准备。

## 状态记录（v19，2026-08-26，P2 模拟器首测 4 缺陷修复收口）

- P2 模拟器首测（A 项商品浏览）发现 4 缺陷，由架构师现场修复（授权偏差，即时排障，已在 LOGBOOK trace 20260826-p2trial-sim-fixes 如实记录）；AI 员工独立复核 + 分 4 commit 收口（C1 621753c / C2 12cc895 / C3 ec1e9d5 / C4 23f0c4e），当前 VERSION=0.133.0-p2trial.3（后续 77f9346 完成超时守卫收口）。
- 4 缺陷：① 首页 wx:for-item 缺失（变量遮蔽→商品卡全空、点击空 id 报"商品不存在"）② 开发版 API 默认连远程线上配置（本地修复不可见）③ featured 空配置返回空属特性但占位模板 manual 占位 ID 永不命中→空白货架 ④ 图片 http 被 3.x 基础库拒 + 代理端点 500（fetch 异常未保护）。
- P2 模拟器 **A 项完成**；B/C/D/E 待走查。
- **体验版状态拆分**：3a DevTools `Empty file` 瞬时竞态已解除；3b 测试号不支持体验版，仍等 mp 后台/正式 AppID 条件（不向真实用户开放、不提审）。
- **部署遗留项（上线前必须）**：生产库上线前须配置 `shop_config.featured_products` 精选 6 款（当前仅本地库直写，无 DB 迁移/发布配置覆盖 home-featured 默认值）。
- 遗留观察：模拟器 Console Error: timeout 未定位（Launch Time 偏慢），非阻断。

## 状态记录（v20，2026-08-26，新仓全量 pytest 首次基线清零）

- 上轮（T-COMMIT-P2TRIAL-FIXES-01）将 5-6 个失败统称"gbk 解码/环境问题"定性不准；本轮回溯给出三类真实根因（trace 20260826-test-baseline-zero）：①lifespan 桩缺 app.api.admin.invoices（e2639d4 发票承接真实回归）②进度清单头未随 VERSION bump 同步③backup C 盘守卫 Windows 开发机不兼容（skipif win32 跳过，守卫不改）。
- 偏差追加：第 4 个 test_cli_help 同样因 Windows gbk 子进程解码失败，同属 Windows 不兼容，已如实披露加第 4 跳过。
- **新仓全量 pytest 首次基线清零**：`pytest --no-cov -q` rc=0；miniapp `npm run typecheck` rc=0。
- 教训沉淀（commit-workflow.md 已写入）：VERSION 变更必须与根目录 + backend/ 两份 `项目进度与配置清单.md` 表头同步，否则 `test_repository_progress_header_matches_version_file` 会红；报告失败必须给根因证据而非归类标签。
- 约束遵守：只动指定测试/文档文件；未改生产代码守卫；当前 VERSION=0.133.0-p2trial.3；未动冻结旧仓。
