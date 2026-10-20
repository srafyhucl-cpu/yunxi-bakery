# Stage 2.5–4 交付验收报告

- 日期：2026-10-20
- 分支：`artful-quokka`
- 代码快照：`d6e37136588e77e48513c740ee84e9a8b5f4827b`
- 版本：`0.133.0-p2trial.3`（以 `backend/VERSION` 为准）
- 结论：**可试运行代码 + 合成验收 + 上线 runbook 已完成；不是生产上线，当前仍为 No-Go。**

## 一、本轮目标与非目标

### 目标

在不接触真实会员数据、真实微信支付、真实打印机的前提下，把仓库从 Stage 2 代码级状态推进到可试运行：

- 有赞储值迁移管线、本金/赠送金账本、退款结构、对账与回滚；
- 定制蛋糕/日常现烤双轨、每日现烤库存、蛋糕时段容量；
- 云小票机打印作业、支付成功自动入队、后台补打；
- 店员账号、储值直扣、微信分享待付、手机端快捷开单；
- 只读 AI 导购、结构化定制需求卡、生产 FAQ 30 条、本地一键联调；
- preflight fail-closed 与最小商用红线、CI 前端 typecheck。

### 非目标

- 不向真实用户开放，不接真实微信支付/退款，不接真实飞鹅打印机；
- 不做完整历史订单迁移（只做最近 10 笔回显）；
- 不做易联云（先飞鹅 + 抽象接口）；
- 不做代付（分享卡仅订单归属客户本人）；
- 不做真实门店生产库导入/生产部署。

项目红线仍以根 `AGENTS.md` 与 `PROJECT-STATE.md` 为准：**2027-05-31 前小程序仅用于开发、调试和测试**；真实上线必须由项目负责人另行批准。

## 二、交付内容

### Stage 2.5：迁移、账务与产能

| 能力 | 交付 | 关键提交 |
|---|---|---|
| 本金/赠送金账本 | `v040` 流水拆分、退款按原结构恢复、不变量测试 | `afe1be1` |
| 有赞储值导入 | `v041` 批次/明细、dry-run/apply、对账、回滚、合成夹具 | `b058d75` |
| 会员认领历史订单 | 手机号 + 有赞 openid 双标识，最近 10 笔 | `3350b6b` |
| 每日现烤库存 | `v042` 每日库存、原子预占/释放、后台录入、订单集成 | `028cb87`、`441b9ac` |
| 蛋糕时段容量 | `v043` 原子 slot 预占/释放，替换 count-then-act | `3f16e56` |

### Stage 3：打印与快捷开单

| 能力 | 交付 | 关键提交 |
|---|---|---|
| 打印作业骨架 | `v044` `order_print_jobs`、两联排版、Mock/飞鹅网关 | `f8cf055` |
| 支付后自动入队 | `v045` 游标、已支付订单扫描、5 秒调度器 | `558a6be` |
| 打印 worker 与补打 API | PENDING 消费、后台列表/重试/人工确认/补打 | `5ee3c4d`、`1a5c30c` |
| 店员账号与查询 | `v046` 店员表/审计、PIN/JWT、手机号查会员、商品搜索 | `32eaa70` |
| 快捷开单 | `v047` 请求幂等、储值直扣、分享待付、事务回滚 | `0ee3de8` |
| 快捷开单页面 | 手机端登录、会员、购物车、定制勾选、回执/分享 | `077278a` |

### Stage 4：只读 AI、FAQ 与联调

| 能力 | 交付 | 关键提交 |
|---|---|---|
| 结构化定制卡 | 只读 `CustomizationCardService`、AI 工具、小程序 API | `36acc8e` |
| 聊天页定制卡 | 表单、摘要复制、`open-type="contact"` | `b0d1672` |
| 30 条 FAQ | 生产只读取样 + 可重复导入 seed、dry-run/apply | `bf15eab` |
| 本地联调 | `.env.example`、`scripts/setup.ps1`、试点 runbook | `8aa056a` |
| 登录并发修复 | 登录审计先提交，避免限流清理与请求连接互锁 | `70d6bce` |
| preflight/CI | fail-closed、内联最小红线、前端 typecheck job | `d6e3713` |

## 三、验证结果

### 后端

```text
python -m pytest backend/tests/api backend/tests/service backend/tests/repository \
  backend/tests/middleware backend/tests/migrations \
  backend/tests/scripts/test_preflight_production.py -q
```

- 根 CI 同款目录：**1460 项收集、全部通过**；
- preflight 守卫：**45 项通过**；
- 合计约 **1505 项通过**；
- 仅有一条既有 Starlette/httpx 弃用警告，无失败。

### 前端

```text
cd backend/web/admin && npm run typecheck   # vue-tsc 通过
cd miniapp && npm run typecheck             # tsc 通过
cd miniapp && npm run check:miniapp         # 15 pages / 15 routes 通过
```

### 合成链路

4C 验证已实测：

- `/health` 200、`/ready` 503（本地未配置生产依赖属预期）、`/docs` 200；
- 后台登录、每日库存录入、会员认领、手机号查会员；
- 快捷开单储值直扣：订单已支付、余额从 22000 分扣到 18400 分；
- 微信分享待付：返回 `sharePath` / `shareText`，不扣余额；
- 打印作业落 `MOCKED`（`PRINT_PROVIDER=mock`），后台打印队列可见。

## 四、仍存在的限制与上线前必须做的事

### 代码/工程限制

1. **SQLite 单写者**：当前生产编排仍是单进程 + SQLite；多实例/多 worker 不是即插即用。
2. **飞鹅只到 SUBMITTED**：云端返回成功不代表出纸；`PRINTED` 目前只能由人工确认或后续回执写入。
3. **CLAIMED 卡死回收未实现**：进程在领取后崩溃，作业可能停在 `CLAIMED`，需要后台超时回收或人工处理。
4. **preflight 内联红线是“最小集”**：只覆盖 `SELECT *`、分层越界、SQL f-string、静默异常、print、Optional/Union、根 API 兼容文件等；已归档的业务合约检查（RAG golden cases、知识治理、可观测、MiniApp 页面 API 覆盖等）未恢复，detail 用 `mode=inline_minimal` 明确区分。
5. **存量多行 `except ...: pass`**：内联规则只判同行形式，存量仍有若干处，需单独批次补日志。
6. **FAQ 一条非生产来源**：`repo_storefront_claim`（储值认领）来自本仓实现，不是生产 FAQ；上线前需运营确认口径。
7. **分享卡仅订单归属客户本人**：不做代付；付款人 openid 必须是订单归属客户。
8. **快捷开单仅到店自提**：配送/闪送快捷开单未做。
9. **预约时间**：快捷开单/需求卡会受营业时间、17:00 截单、蛋糕提前 4 小时规则约束；超时会 400，需店员改时间或转人工。

### 真实上线前必须另做

- 有赞真实储值/积分/历史订单导出、逐会员对账、差异处理、回滚演练；
- 真实微信支付商户号、支付/退款回调、对账与退款验证；
- 真实飞鹅打印机采购、绑定、纸宽/编码/离线/补打试点；
- 微信小程序正式 AppID、微信客服开通、`open-type="contact"` 真机验证；
- 食品经营许可证、ICP备案、小程序类目、微信支付商户资质；
- 店员账号初始化、PIN 分发/轮换、收银培训与权限审计；
- 真机/体验版、微信审核、生产部署与备份恢复演练；
- 项目负责人书面批准真实上线与真实用户开放。

## 五、如何复现本轮验收

1. 按 [local-trial-runbook.md](local-trial-runbook.md) 执行 `scripts/setup.ps1`；
2. 启动后端与后台，按 runbook 创建店员、导入 30 条 FAQ、导入合成储值；
3. 用 `/admin/daily-stock` 录入当天库存，用 `/admin/quick-order` 开单；
4. 用 `/admin/print-jobs` 查看 `MOCKED` 作业并人工确认/补打；
5. 跑本文第三节命令。

## 六、结论

本轮交付满足“可试运行代码 + 合成验收 + 上线 runbook”的终点：

- 业务闭环已覆盖迁移、储值、双轨、库存、时段、打印、快捷开单、只读 AI、FAQ；
- 所有验证均基于合成数据与 Mock，不构成生产验收；
- 真实门店试点/上线仍需完成第四节“真实上线前必须另做”并取得负责人批准。
