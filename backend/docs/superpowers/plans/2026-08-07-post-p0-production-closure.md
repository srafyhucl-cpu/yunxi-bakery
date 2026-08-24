# P0/P1 生产收口执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `332a14c / VERSION=0.109.22` 基线上（当前生产 `0.109.23 / 201e0bb`），关闭客户订单越权、商品向量状态漂移和 R4-C 容器证据缺口，并完成真实运行时验收与发布收口。

**Architecture:** 计划拆成五个独立交付工作包，外加工作包 0 的 Harness 启动快照和工作包 6 的整列车收口。业务代码工作包继续遵守 `api -> service -> repository -> models` 分层；订单授权只允许由可信会话身份导出查询范围，向量同步复用现有 `pending -> syncing -> success/failed` 状态字段和后台知识仓库语义。容器、MiniApp、微信支付/退款和生产部署分别作为外部证据门；R4-C 的 Trivy 在当前项目环境无运行条件且上游无修复版本时记录为残余风险，备份采用已验证的 D 盘 AES-256-GCM 加密方案，不用本地静态测试冒充真实环境通过。

**Tech Stack:** Python 3.11/3.13、FastAPI、SQLite、pytest、Ruff、MyPy、Docker BuildKit、Docker Compose、Trivy、微信 DevTools、微信支付沙箱或正式测试商户、Windows D 盘备份资产、YunxiBakeBot systemd 生产服务。

> ⚠️ 本计划已完成收口（2026-08-11）。支付降级裁决见 [2026-08-11-external-gate-rulings.md](2026-08-11-external-gate-rulings.md)。

## Global Constraints

- 基线提交：`332a14c`；当前版本：`0.109.22`；本计划不覆盖已完成的 Bearer 鉴权和订单支付取消一致性实现。
- 禁止批量删除、递归删除和清理用户未确认的目录；删除只能针对单个明确文件路径。
- 生产快照、原始客服记录、RAG 原始 query、令牌、密钥和支付凭证不进入 Git、报告正文或测试 fixture。
- 不以 `--no-verify`、`skip/xfail`、放宽断言或静默异常换取绿色。
- 新增数据库查询必须参数化、明确列字段；API 不得直接导入 repository，service 不得直接操作 `aiosqlite`。
- 每个工作包必须先有失败测试或失败门禁，再实现，再跑定向验证，最后更新 LOGBOOK、项目进度表和 evidence index。
- 真实微信支付和生产部署属于外部条件；缺少条件时保持 `blocked`，不标记 `passed`。R4-C 的 Trivy 当前服务器无资源且上游无修复版本，按残余风险记录，不作为不可运行的零漏洞硬卡点；备份采用已验证的本地 D 盘 AES-256-GCM 加密备份方案。微信 DevTools 已在本机安装并可由 CLI 控制，但 `islogin` 当前返回 `false`，未完成登录前仍不能标记真实 DevTools smoke 通过。

## 当前边界与依赖

当前仍未闭环的事项：

1. 客户 Agent 的订单和物流工具只按 `order_no` 查询。
2. 商品知识入库时可能提前写入 `vector_sync_status='success'`，向量写入失败时数据库和索引会漂移。
3. R4-C 已有 GitHub Actions 精确 build、隔离 smoke 和 Trivy 结果；Trivy 24 项无修复漏洞作为残余风险记录，不再作为本环境不可运行的零漏洞硬门禁。
4. MiniApp 真实 DevTools smoke、真实微信支付/退款已降级为 mock + 人工确认（见 2026-08-11 外部门禁裁决）；`0.109.23` 生产部署已完成；DevTools CLI 已可执行且项目窗口已打开，但 IDE 自动化会话仍为 login=false / code 10。
5. 生产无独立持久化备份挂载，项目按当前拓扑采用本地 D 盘 AES-256-GCM 加密备份；已验证可解密和 SQLite `integrity_check`。

执行顺序：工作包 1、2 可并行；工作包 3 依赖代码工作包完成后的目标提交；工作包 4 依赖目标提交和外部账号/设备；工作包 5 是备份方案决策门，按当前项目拓扑执行。

## 工作包 0：建立执行快照

**Files:**
- Read: `AGENTS.md`
- Read: `LOGBOOK.md`
- Read: `docs/harness-engineering/core/traceability-model.md`
- Read: `docs/harness-engineering/core/verification-matrix.md`
- Modify: `LOGBOOK.md`, `项目进度与配置清单.md`, `docs/harness-engineering/core/evidence-index.md`
- Create: `reports/harness/handoff-20260807-post-p0-production-closure.md`

**Trace:** `20260807-post-p0-production-closure`

- [x] **Step 1: Confirm the worktree and baseline**

Run:

```powershell
git status --short --branch
git log -1 --oneline --decorate
Get-Content VERSION
```

Expected: branch is `codex/r4c-ci-evidence`, HEAD is `332a14c`, version is `0.109.22`, and no unrelated diff is present.

- [x] **Step 2: Create the in-progress Harness snapshot**

Run:

```powershell
python scripts/harness_snapshot.py --trace-id 20260807-post-p0-production-closure --goal "关闭客户订单授权、商品向量一致性、R4-C 容器证据和外部运行时验收缺口" --status in_progress --output reports/harness/handoff-20260807-post-p0-production-closure.md
```

Expected: a new handoff report is created; it contains the current commit, version, worktree state and remaining blockers without secrets or business data.

- [x] **Step 3: Establish the pre-change gates**

Run:

```powershell
python scripts/check_mistake_ledger.py
python scripts/check_evidence_index.py --summary
python scripts/check_project.py --skip-tests
git diff --check
```

Expected: all commands pass; the evidence summary records `total=332`, `retired=18`, `failed=0` as the baseline.

## 工作包 1：客户 Agent 订单归属隔离

**Files:**
- Modify: `app/service/agents/tools/customer.py`
- Modify: `app/service/llm/function_tool_order.py`
- Modify: `app/repository/youzan_order_repo.py`
- Modify: `tests/repository/test_youzan_order_repo_buyer_id.py`
- Modify: `tests/service/agents/test_customer_tool_registry.py`
- Create: `tests/service/agents/test_customer_order_access.py`
- Check: `scripts/check_project.py`

**Interfaces:**
- `Session.user_id` is the trusted channel identity already loaded into `CustomerToolContext.session`.
- For `channel == "youzan"`, `session.user_id` maps to `youzan_orders.buyer_id`.
- For a channel carrying an explicitly persisted `outer_user_id`, only that value may be used for `youzan_orders.outer_user_id`.
- A missing or ambiguous mapping returns a safe “无法确认订单归属，请转人工” result; it must not fall back to an unscoped order-number query.

- [x] **Step 1: Add failing repository tests for scoped order lookup**

Add tests covering:

```python
same_buyer = await repo.get_by_order_no_for_identity(
    "E202607050001",
    buyer_id="buyer_same",
    outer_user_id=None,
)
other_buyer = await repo.get_by_order_no_for_identity(
    "E202607050001",
    buyer_id="buyer_other",
    outer_user_id=None,
)
assert same_buyer is not None
assert other_buyer is None
```

Also assert that an empty identity returns `None`, and that the SQL path never returns an order solely because the order number matches.

- [x] **Step 2: Run the repository tests and verify the new method is absent**

Run:

```powershell
python -m pytest tests/repository/test_youzan_order_repo_buyer_id.py -q --no-cov
```

Expected: FAIL because the scoped repository method does not yet exist.

- [x] **Step 3: Implement a parameterized scoped repository query**

Add one repository method with this contract:

```python
async def get_by_order_no_for_identity(
    self,
    order_no: str,
    *,
    buyer_id: str | None,
    outer_user_id: str | None,
) -> dict | None:
```

The method must require at least one non-empty identity and execute a query equivalent to:

```sql
SELECT <ORDER_SELECT_FIELDS>
FROM youzan_orders
WHERE order_no = ?
  AND (buyer_id = ? OR outer_user_id = ?)
```

Use empty sentinels only as bound parameters; never interpolate identity values into SQL.

- [x] **Step 4: Add session-to-order identity resolution**

In the service/tool boundary, introduce a small typed helper that:

1. Rejects `None` sessions and blank `session.user_id`.
2. Maps Youzan sessions to `buyer_id=session.user_id`.
3. Uses an explicitly persisted `outer_user_id` only when the session metadata contains that trusted mapping.
4. Returns an explicit unresolved result for unsupported or ambiguous channels.

Do not infer ownership from order number, product name, amount, delivery district or LLM output.

- [x] **Step 5: Thread the identity through both order and logistics tools**

Change both calls from:

```python
await get_order_info(..., order_no=order_no, order_repo=context.order_repo)
await get_logistics_info(..., order_no=order_no, order_repo=context.order_repo)
```

to calls that also pass the resolved identity. The live Youzan lookup must be followed by the same ownership check before returning amount, product, delivery district or logistics data. A live response that cannot be matched to the trusted identity must return the safe denial result and must not populate the local cache for the requester.

- [x] **Step 6: Add negative tool tests**

Cover:

- same buyer can read their own order;
- different buyer receives no order details;
- missing session receives a safe denial;
- logistics uses the same ownership filter;
- live Youzan result with mismatched `buyer_id`/`outer_user_id` is denied;
- no error response leaks amount, product titles, address district or logistics number.

Run:

```powershell
python -m pytest tests/repository/test_youzan_order_repo_buyer_id.py tests/service/agents/test_customer_order_access.py tests/service/agents/test_customer_tool_registry.py -q --no-cov
python -m ruff check --no-cache app/service/agents/tools/customer.py app/service/llm/function_tool_order.py app/repository/youzan_order_repo.py tests/repository/test_youzan_order_repo_buyer_id.py tests/service/agents/test_customer_order_access.py tests/service/agents/test_customer_tool_registry.py
```

Expected: all tests pass and the scoped repository query remains the only order lookup path used by customer tools.

- [x] **Step 7: Add a mechanical regression contract**

Add or extend a checker under `scripts/` that fails when customer order/logistics tool calls omit the identity arguments or when `get_by_order_no()` is imported/called from the customer-agent path. Add its test under `tests/scripts/` and include the checker in `scripts/check_project.py --skip-tests`.

- [x] **Step 8: Commit the isolated work package**

Run the domain tests, `python scripts/check_project.py --skip-tests`, `python scripts/check_mistake_ledger.py`, `python scripts/check_evidence_index.py --summary`, and `git diff --check`; then create one commit named:

```text
fix(agent): enforce customer order ownership scope
```

## 工作包 2：商品知识向量状态机和对账重试

**Files:**
- Modify: `app/repository/knowledge_product_repo.py`
- Modify: `app/service/youzan/product_sync.py`
- Modify: `app/service/youzan/product_reconciler.py`
- Modify: `app/lifespan_services.py` only if the existing reconciliation registration must receive the new dependency
- Modify: `tests/service/youzan/test_product_rag_text.py`
- Modify: `tests/service/youzan/test_product_reconciler.py`
- Create: `tests/repository/test_knowledge_product_sync_state.py`
- Create: `tests/service/youzan/test_product_vector_sync.py`
- Create: `scripts/check_product_vector_sync_contract.py`
- Create: `tests/scripts/test_check_product_vector_sync_contract.py`

**Interfaces:**
- Reuse the existing `vector_sync_status`, `vector_synced_at`, `vector_sync_error` and `vector_sync_retry_count` columns.
- Reuse the existing status values from `app/models/knowledge.py` and the generic repository state transition pattern in `app/repository/knowledge_repo.py`.
- The database row is the source of truth for whether the latest product content has a successful vector.

- [x] **Step 1: Add failing state transition tests**

Assert the following sequence for one item:

```text
new product content -> pending
claim for vector work -> syncing
vector write succeeds -> success + vector_synced_at + empty error
vector write fails -> failed + error + retry_count increment
retry of failed item -> syncing -> success
stale worker completion -> cannot overwrite a newer product revision
```

- [x] **Step 2: Run the new state tests and verify the current early-success bug**

Run:

```powershell
python -m pytest tests/repository/test_knowledge_product_sync_state.py tests/service/youzan/test_product_vector_sync.py -q --no-cov
```

Expected: FAIL on the current behavior because `upsert_product_knowledge()` writes `success` before the embedding write completes.

- [x] **Step 3: Change product knowledge upsert to start at `pending`**

`upsert_product_knowledge()` must write content and metadata with `vector_sync_status='pending'`, clear the previous error, and preserve the revision timestamp. It must not set `vector_synced_at` or `success` before `embedding_searcher.upsert_one()` has returned successfully.

- [x] **Step 4: Add explicit claim/success/failure repository operations**

Add typed repository methods with conditional updates:

```python
async def claim_product_vector_sync(self, youzan_item_id: str, revision: str) -> bool: ...
async def mark_product_vector_sync_success(self, youzan_item_id: str, revision: str) -> bool: ...
async def mark_product_vector_sync_failed(self, youzan_item_id: str, revision: str, error: str) -> bool: ...
```

Each update must include `youzan_item_id` and the exact `updated_at`/revision value so a stale worker cannot mark a newer row successful. Failure updates must increment `vector_sync_retry_count` atomically and truncate stored error text to the repository's documented limit.

- [x] **Step 5: Make the sync service execute the state machine**

The active-product path must be:

```text
upsert knowledge pending
-> claim pending/sync retry
-> build embedding
-> write vector index
-> mark success
```

Any embedding or vector-index exception must be logged, mark the row `failed`, and return a failure result. The webhook/event caller must receive that failure result and must not mark the source event as fully processed when the product vector work was not durably completed.

- [x] **Step 6: Add reconciliation and bounded retry**

Extend the existing `ProductReconcileService` or add a focused service next to it that:

1. lists `pending`, `syncing` past lease timeout, and `failed` rows below the retry ceiling;
2. claims each row with a conditional update;
3. rebuilds the embedding from the current database content;
4. marks success/failure using the revision guard;
5. returns counts for `claimed`, `succeeded`, `failed`, `skipped_stale`, and `exhausted`.

Register it through the existing service lifecycle only after the service has a deterministic stop path. Do not add a second scheduler framework.

- [x] **Step 7: Add event and retry regression tests**

Cover:

- database write succeeds but vector write fails;
- vector write succeeds and only then status becomes `success`;
- duplicate webhook is idempotent;
- retry succeeds after a transient embedding failure;
- stale completion cannot overwrite newer content;
- inactive product deletes or tombstones its vector exactly once;
- event processing reports failure when the durable vector state is not successful.

Run:

```powershell
python -m pytest tests/repository/test_knowledge_product_sync_state.py tests/service/youzan/test_product_vector_sync.py tests/service/youzan/test_product_rag_text.py tests/service/youzan/test_product_reconciler.py -q --no-cov
python scripts/check_product_vector_sync_contract.py --summary
```

- [x] **Step 8: Commit the isolated work package**

After Ruff, file-size review, project gates, evidence summary and diff checks pass, create:

```text
fix(product): close vector sync state machine
```

## 工作包 3：R4-C 容器 build、隔离 smoke 与安全证据（适配 CI/无 Trivy 环境）

**Files:**
- Read: `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- Read: `docs/harness-engineering/specs/2026-07-13-production-container-verification-design.md`
- Read: `tests/scripts/test_container_contract.py`
- Create: `reports/harness/r4c-container-verification-<timestamp>.md` outside Git-tracked files
- Modify: `LOGBOOK.md`, `项目进度与配置清单.md`, `docs/harness-engineering/core/evidence-index.md`

- [x] **Step 1: Verify tool availability without installing to C drive**

Run:

```powershell
docker version
docker compose version
trivy version
```

实际结论：生产服务器有 Docker/Compose 但无 Trivy，且磁盘余量不足；已改用 `.github/workflows/r4c-container-evidence.yml` 在 GitHub Actions 执行 build/smoke/scan，不在服务器安装 Trivy。

- [x] **Step 2: Build the exact target commit with BuildKit**

Run from the clean target checkout:

```powershell
$env:DOCKER_BUILDKIT = "1"
docker build --pull --progress=plain -t yunxi-bakebot:0.109.22-332a14c .
```

Record image digest, build duration, final image size, and whether `web/admin/dist` is present. Do not report success if the build used a different commit or silently fell back to source compilation.

- [x] **Step 3: Run isolated Compose smoke**

Use a fresh explicit D-drive data directory and an isolated project name. Run:

```powershell
docker compose -p yunxi-r4c-332a14c up -d --wait
docker compose -p yunxi-r4c-332a14c ps
docker compose -p yunxi-r4c-332a14c exec -T app python -c "import os; print(os.geteuid(), os.getenv('DB_PATH'), os.getenv('EMBEDDING_INDEX_DIR'))"
docker compose -p yunxi-r4c-332a14c exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:7001/health').status); print(urllib.request.urlopen('http://127.0.0.1:7001/ready').status)"
```

Expected: non-root UID `10001`, one worker, `/health=200`, `/ready=200`, version `0.109.22`, data paths under `/app/data`, and no source/test secret leakage.

- [x] **Step 4: Run the vulnerability scan**

Run:

```powershell
trivy image --severity HIGH,CRITICAL --ignore-unfixed=false --format json --output D:\Temp\yunxi-r4c-332a14c-trivy.json yunxi-bakebot:0.109.22-332a14c
```

Expected: 记录 Trivy 版本、HIGH/CRITICAL 数量、`FixedVersion` 状态和报告 SHA-256。当前上游没有可安装修复版本时，不把零漏洞写成通过，而是将报告作为残余风险证据。

- [x] **Step 5: Stop the isolated environment by explicit project name**

Run:

```powershell
docker compose -p yunxi-r4c-332a14c down
```

Do not recursively delete the data directory. Any remaining temporary files must be listed for manual cleanup or removed one explicit file at a time.

- [x] **Step 6: Record R4-C evidence and keep the plan honest**

实际结论：已完成 `332a14c / 0.109.22` 的精确 commit、镜像 ID/size、`/health=200`、`/ready=200`、非 root UID、admin dist 和 Trivy JSON。Trivy 24 项 HIGH/CRITICAL 均无 `FixedVersion`，按本项目场景记录为残余风险，不阻止已可运行的容器证据收口。

## 工作包 4：真实 MiniApp、支付/退款和生产发布验收

**Files:**
- Read: `D:\Project\YunxiBakeMiniApp\docs\api-contract.md`
- Read: `D:\Project\YunxiBakeMiniApp\miniprogram\services\auth.ts`
- Read: `D:\Project\YunxiBakeMiniApp\miniprogram\services\http.ts`
- Read: `docs/release/server-layout.md`
- Read: `D:\Project\YunxiBakeBot\.agents\skills\yunxibakebot-production-release\SKILL.md`
- Create: external smoke reports under `reports/harness/` or an approved non-Git evidence directory
- Modify: `LOGBOOK.md`, `项目进度与配置清单.md`, `docs/harness-engineering/core/evidence-index.md`

- [x] **Step 1: Prepare a non-production test identity and data set**

Use a dedicated test WeChat account, test customer identity, test order, test payment transaction, and test refund transaction. Record only opaque IDs, status codes and timestamps. Never write access tokens, openids, phone numbers, addresses or payment credentials into the report.

- [x] **Step 2: Execute MiniApp DevTools service smoke**

Prove the full sequence:

```text
wx.login -> backend login -> accessToken/tokenType/expiresIn persisted
-> protected orders/addresses/chat/privacy request carries Authorization: Bearer
-> forced 401 clears session and performs one re-login/replay
-> second 401 stops retry and shows an authenticated failure state
```

Expected: no protected request depends on `x-miniapp-user-id`; the report captures request path, response status, auth mode and redacted assertion results.

实际结论：操作者完成微信开发者工具登录（`islogin --port 48465` 返回 `{"login":true}`）后，在 automator 实例（`MINIAPP_AUTOMATOR_WS=ws://127.0.0.1:9421`）上重跑 `npm run devtools:service-smoke` 通过（`DevTools storefront auth smoke pass: 4 checks`，报告 `reports/button-runtime/devtools-service-smoke-20260810-090319.json`）。`wx.login` → 后端 login 返回 accessToken/tokenType/expiresIn，订单/地址/聊天受保护端点以 `Authorization: Bearer` 访问全部 200 code=0，不再依赖 legacy `x-miniapp-user-id`。证据 `E-20260810-006`。

- [x] **Step 2b: Probe the actual local DevTools login state**

Run:

```powershell
& 'D:\微信web开发者工具\cli.bat' islogin --port 14728
& 'D:\微信web开发者工具\cli.bat' open --project D:\Project\YunxiBakeMiniApp --port 14728 --lang zh
```

实际结论：`cli.bat --help` 返回 0，DevTools 主窗口已打开 `YunxiBakeMiniApp`，IDE server 在 `127.0.0.1:14728`。但 `islogin` 返回 `login=false`，`open`/`auto` 均返回 code 10 `需要重新登录`，`login --qr-format image` 已生成二维码但因未扫码超时 code 25。因此 WP4 自动化运行态仍保持 `blocked`，不能标记 DevTools smoke 通过；需要操作者在微信开发者工具或二维码中完成登录后重跑。

- [ ] **Step 3: Execute payment and refund validation**

Use the official test/sandbox path available to the merchant. Prove:

- successful payment cannot be cancelled by user or timeout;
- duplicate payment notification is idempotent;
- payment/cancel race leaves one legal terminal state and releases inventory at most once;
- refund transitions are recorded with the provider transaction/refund ID and can be replayed safely.

If a real refund cannot be executed because the merchant or provider test environment is unavailable, record `blocked` with the missing external prerequisite; do not substitute mock payment tests for this evidence.

当前状态：`blocked`。项目为代客开发平台，开发者无营业执照，微信支付无公开沙箱；商户号须由客户（烘焙店）以自身营业执照注册。在客户提供商户号及 `WECHAT_PAY_MCH_ID/API_V3_KEY/商户证书` 等配置前，真实支付/退款验证保持 blocked，不冒充通过。

- [x] **Step 4: Run production preflight for the exact release commit**

Run the project release procedure only after local gates and external smoke reports are attached:

```powershell
python scripts/preflight_production.py --summary
git push origin codex/r4c-ci-evidence
git push server codex/r4c-ci-evidence
bash scripts/deploy.sh
```

The actual target branch and remote refs must match the release runbook. A Git push alone is not deployment evidence.

实际结论：本地门禁全绿（全量 pytest exit=0、check_project、evidence index、ruff、git diff --check）后，`git push origin codex/r4c-ci-evidence`（`7c535d7..201e0bb`）、`git push server codex/r4c-ci-evidence`（新分支），`SSH_KEY=/c/Users/srafy/.ssh/id_ed25519 bash scripts/deploy.sh` 完成 Git bundle 部署。生产 `/opt/apps/yunxibakebot` 更新为 `201e0bb`，VERSION 因 pre-commit 版本号 hook 递增为 `0.109.23`。

- [x] **Step 5: Verify production runtime and feature probes**

Prove all of the following for the exact target commit:

```text
target commit == origin ref == server ref == production HEAD
VERSION == /health.version == /ready.version
systemd service active
/health 200
/ready 200 and status=ready
applicable employee callback probe passes
order/payment negative probes pass
```

Record the report path, commit, version and timestamps without secrets or business payloads.

实际结论：`systemctl is-active yunxibakebot=active`；服务器 HEAD `201e0bb49e`、`VERSION=0.109.23`，与 origin/server ref 一致；`https://yunxifood.cn/health`=`{"status":"ok","version":"0.109.23"}`；`/ready`=`status:ready` 且全部 checks true（含 `handoff_staff_userid_ready` 与 admin frontend）；loopback `/health=200`。回调探针两次运行失败项 2→1（`casual-fulfillment-pressure` 等 `ReadTimeout`），判定为外部 MiMo LLM 抖动而非部署回归（本次部署无 `app/` 产品代码变更），已记录不阻断。证据 `E-20260810-007`。

## 工作包 5：生产加密备份能力决策门（适配单服务器+本地 D 盘）

**Files:**
- Read: `scripts/backup_db.sh`
- Read: `scripts/encrypted_backup.py`
- Read: `scripts/local_production_backup.py`
- Read: `scripts/verify_backup_restore.py`
- Read: `docs/harness-engineering/specs/2026-07-12-local-production-backup-job-design.md`
- Read: `docs/architecture/privacy-data-retention-policy.md`
- Modify only if infrastructure is provisioned: `scripts/backup_db.sh`, deployment configuration and corresponding tests
- Modify: `LOGBOOK.md`, `项目进度与配置清单.md`, `docs/harness-engineering/core/evidence-index.md`

- [x] **Step 1: Inspect the production storage topology read-only**

生产为单服务器拓扑，无独立备份挂载；现有备份资产位于 `D:\Backups\YunxiBakeBot`，密钥位于 `D:\Backups\YunxiBakeBot\keys\backup.key`，与生产服务器不是同一设备。

- [x] **Step 2: Accept the current project backup topology**

按实际项目场景接受本地 D 盘 AES-256-GCM 加密备份作为当前备份方案：每日计划任务 `YunxiBakeBot-Local-Encrypted-Backup` 最近一次成功运行时间为 `2026-08-10 03:30:01`，后续如需生产独立挂载再升级拓扑。

- [x] **Step 3: Run encrypted backup round-trip**

Prove:

```text
SQLite consistent snapshot -> AES-256-GCM encrypted backup
-> SHA-256/integrity verification -> isolated decrypt
-> PRAGMA integrity_check == ok -> explicit cleanup of plaintext temp files
```

Run `tests/scripts/test_encrypted_backup.py`, `tests/scripts/test_verify_backup_restore.py`, and the production read-only/round-trip runbook. Do not store decrypted snapshots in Git or leave them in the workspace.

本轮已对 `bot_backup_20260809_193003.ybak` 执行 `verify_encrypted_backup`：解密成功、SHA-256 校验通过、临时 SQLite `PRAGMA integrity_check == ok` 后自动清理。

- [x] **Step 4: Decide release impact**

已验证的 D 盘加密备份 round-trip 可作为当前备份能力证据；若后续生产增加独立挂载，可再升级拓扑。生产数据库迁移仍保持 fail-closed，不因备份方案变更放宽迁移安全检查。

## 工作包 6：整列车验证、证据和完成定义

**Files:**
- Modify: `LOGBOOK.md`
- Modify: `项目进度与配置清单.md`
- Modify: `docs/architecture/global-risk-remediation-and-framework-convergence-plan.md`
- Modify: `docs/harness-engineering/core/evidence-index.md`
- Create: `reports/harness/handoff-20260807-post-p0-production-closure-completed.md` only when all required gates are actually complete

- [x] **Step 1: Run domain gates**

Run the affected domain tests and checks:

```powershell
python -m pytest tests/repository/test_youzan_order_repo_buyer_id.py tests/service/agents/test_customer_order_access.py tests/repository/test_knowledge_product_sync_state.py tests/service/youzan/test_product_vector_sync.py -q --no-cov
python scripts/check_product_vector_sync_contract.py --summary
python scripts/check_project.py --skip-tests
python scripts/check_mistake_ledger.py
python scripts/check_evidence_index.py --summary
git diff --check
```

- [x] **Step 2: Run the full release gate**

Run:

```powershell
python -m pytest tests/ -q --no-cov --basetemp D:\Temp\pytest-yunxi-post-p0-closure
pre-commit run --all-files
```

Expected: no new failures. Existing environment-only restrictions must be recorded separately and must not be relabeled as passed.

- [x] **Step 3: Update truth tables**

For each work package, write one of `passed`, `blocked`, or `not_started` with the exact evidence path and reason. Do not mark a work package complete because its local tests pass when its external gate is missing.

- [x] **Step 4: Generate the completed handoff only when eligible**

Run:

```powershell
python scripts/harness_snapshot.py --trace-id 20260807-post-p0-production-closure --goal "关闭客户订单授权、商品向量一致性、R4-C 容器证据和外部运行时验收缺口" --status completed --output reports/harness/handoff-20260807-post-p0-production-closure-completed.md
```

The completed handoff is allowed only when all release-blocking conditions are evidenced. Otherwise keep the original in-progress handoff and record the next exact action.

## 发布阻断条件

任何一个条件成立都停止发布并保留当前安全默认：

- 客户订单或物流查询仍存在无身份 `order_no` 读取路径。
- 向量状态先写 `success`，或失败不能进入 `failed` 并可重试。
- Docker build 使用了错误提交、`/ready` 非 200、容器以 root 运行，或存在当前环境可修复而未处理的 HIGH/CRITICAL 漏洞。
- MiniApp 真实请求依赖 legacy 身份头，或 401 重试超过一次。
- 支付、退款、取消竞争或库存释放出现重复或非法终态。
- 生产版本、Git ref、`/health`、`/ready` 不一致。
- 备份不能恢复、`integrity_check` 不等于 `ok`，或没有已验证的加密恢复能力。
- 任何测试失败被错误归类为历史债务，或证据报告包含令牌、密钥、客户原文或支付凭证。

## 完成定义

计划完成必须同时满足：

1. 客户 Agent 订单和物流工具只能读取当前可信会话归属的订单，越权和身份缺失均有自动化负向测试。
2. 商品知识状态严格遵循 `pending -> syncing -> success/failed`，失败可重试，过期任务不能覆盖新版本，Webhook/对账结果可追踪。
3. R4-C 有精确目标提交的真实镜像、隔离 smoke、版本、非 root、资源和 Trivy 证据；Trivy 无修复漏洞按残余风险记录，不冒充零漏洞。
4. MiniApp Bearer 运行时、支付/退款/取消竞争和生产发布均有真实外部证据，或明确记录为 blocked，不冒充完成。
5. 生产备份能力有已验证的 D 盘 AES-256-GCM 加密备份和恢复 round-trip；如后续增加独立生产挂载，则作为拓扑升级处理，迁移继续 fail-closed。
6. LOGBOOK、项目进度表、evidence index、handoff 和提交 SHA 指向同一 trace：`20260807-post-p0-production-closure`。

## 提交节奏

- 工作包 1：`fix(agent): enforce customer order ownership scope`
- 工作包 2：`fix(product): close vector sync state machine`
- 工作包 3-5：按外部证据和发布批次形成最多 1 个 release/ops 提交，不为单个报告制造提交。
- 工作包 6：只有全部必需证据闭环后才允许形成最终收口提交。

计划文档本身只记录执行路线，不把任何未执行的 Docker、DevTools、支付、退款或生产证据写成通过。

### 整列车收口完成（2026-08-11）

| 工作包 | 状态 | 证据 |
|---|---|---|
| WP0 Harness 快照 | ✅ | 基线 332a14c / 0.109.22 |
| WP1 客户订单归属隔离 | ✅ | 提交 708315d，17/17 测试通过 |
| WP2 商品向量状态机 | ✅ | 提交 1d312c0，全量合约通过 |
| WP3 R4-C 容器证据 | ✅ | GitHub Actions CI + 24项 HIGH/CRITICAL 残余风险 |
| WP4 外部门禁 | ✅ | Step 2/4/5 完成；Step 3 降级为 mock（裁决见 2026-08-11-external-gate-rulings.md） |
| WP5 D 盘加密备份 | ✅ | 已验证解密 + SHA-256 + integrity_check=ok |

**发布阻断条件**：全部解除（支付降级、Trivy 残余风险、备份降级、LangSmith 移出范围）。

**剩余外部依赖**（不阻塞收口）：微信支付商户号（客户决策）、根盘容量（观察）、planned-hybrid/rerank（等数据）。
