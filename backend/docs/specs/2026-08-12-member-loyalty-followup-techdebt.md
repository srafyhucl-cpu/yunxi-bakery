# 后续工作包 FP-5：技术债承接

- status: pending
- parent_trace_id: `20260812-member-loyalty-storedvalue`
- 执行时须生成独立 trace_id（如 `2026MMDD-member-loyalty-techdebt`），不得复用父计划 trace
- 所属计划：[2026-08-12-member-loyalty-storedvalue-plan.md](./2026-08-12-member-loyalty-storedvalue-plan.md)
- 拆分来源：2026-08-14 深度复核——原拆分未承接全部已知技术债

## 背景

会员账务域评审与执行中累积的技术债未全部被 FP-1 / FP-3 承接。复核后明确归属：券 `BACK` 退款接入 → FP-3；真实券字段 / 非数值折扣解析 → FP-1；以下两项由本工作包承接。

## 承接范围

1. **类型注解精确化**（M4 评审遗留 #5）：`app/service/coupon/inventory.py` 的 `CouponInventoryService.consume_once` / `refund_once` 注解为 `-> dict | None`，但实际返回 `CouponInventoryEntry`（经由 `app/repository/coupon_inventory_repo.py` 的 `consume` / `refund` 返回 `CouponInventoryEntry`）。目标：统一注解为 `-> CouponInventoryEntry | None`（或显式 dict 化），增加失败测试（运行期类型断言 / isinstance 校验），通过 `scripts/mypy_nonblocking.py` 渐进式扫描，不新增豁免项。
2. **tests/scripts 覆盖率 flaky（WinError 32）**：`tests/scripts` 在 Windows 下偶发 `WinError 32`（SQLite 句柄未释放即被删除 / 占用），已记录于 M4 评审 #6。目标：修复句柄释放时序（连接显式 close / 上下文管理），消除 `WinError 32`，恢复稳定覆盖率基线并建立连续运行断言。

## 任务清单

1. 将 `CouponInventoryService.consume_once` / `refund_once` 注解统一为 `-> CouponInventoryEntry | None`（或显式 dict 化），并增加失败测试（运行期类型断言 / isinstance 校验），`mypy_nonblocking.py` 通过。
2. 修复 SQLite 句柄释放时序（连接显式 close / 上下文管理），消除 `WinError 32`，恢复 `tests/scripts` 稳定覆盖率基线。
3. 建立覆盖率稳定性断言，连续 N 次运行无抖动。
4. LOGBOOK / 证据索引收口，使用独立 trace_id。

## 验收标准

- `consume_once` / `refund_once` 注解与实现一致（`CouponInventoryEntry`），运行期类型断言通过，mypy 无新增豁免。
- `tests/scripts` 连续运行无 `WinError 32`，覆盖率稳定通过。
- 无运行时行为变更（纯类型与测试工程）。

## 边界

- 本工作包不引入业务行为变更；若发现类型注解缺口暴露运行时缺陷，转入对应功能工作包处理。
