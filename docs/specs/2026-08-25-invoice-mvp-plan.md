# 发票承接方案（MVP 轻量版）

- trace_id: 20260825-p1-invoice-mvp-plan
- 状态: approved（项目负责人 2026-08-25 拍板"按你说的办"）
- 来源: 有赞功能对标表（docs/specs/youzan-feature-benchmark.md）判定——全表唯一真缺口
 
---

## 一、决策（一句话）

**不做电子发票直开，采用"知识库话术 + 转人工 + 后台人工登记"三步承接。**

## 二、依据

- 旧知识库 #9566（企业服务规则）已有完整开票口径：支持增值税电子普通发票；顾客提供企业抬头、税号、接收邮箱；交易完成后 1-3 个工作日开出——**话术底稿现成，已在 24 条迁移知识中**
- 有赞侧无发票事件流（非交易环节能力），企业团购场景低频但真实
- MVP 原则：内容能兜、动作能记、上限不加力

## 三、范围（P2 试运行前完成，半天工作量）

| # | 工作项 | 说明 | 实现 |
|---|--------|------|------|
| 1 | 客服话术确认 | 核对迁移后的 #9566 条目仍在库并在 BM25 命中范围（"发票/开票/抬头/税号"关键词） | 只读验证 |
| 2 | 后台人工登记 | 新表 `invoice_requests` + admin API + admin 页面连登记 | 见下 |

**表结构（最小）**：
```
invoice_requests(
  id INTEGER PK,
  order_no TEXT NULL,            -- 关联订单号（可选）
  customer_name TEXT NOT NULL,   -- 客户称呼
  company_title TEXT NOT NULL,   -- 企业抬头
  tax_no TEXT NOT NULL,          -- 税号
  email TEXT NOT NULL,           -- 接收邮箱
  amount_fen INTEGER NULL,       -- 发票金额（可选）
  status TEXT NOT NULL DEFAULT 'applied',  -- applied / issued / cancelled
  issue_note TEXT NULL,          -- 开票备注（发票号码等）
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
```

**admin API（最小）**：POST /api/v1/admin/invoices（登记）、GET /api/v1/admin/invoices（列表）、POST /api/v1/admin/invoices/{id}/mark-issued（标记已开）

**admin 页面（最小）**：发票管理页——登记表单 + 列表 + 状态流转按钮

## 四、验收

1. 顾客侧问"能开发票吗" → AI 命中 #9566 话术（抬头/税号/邮箱/1-3 工作日）
2. 复杂情况转人工 → 人工在 admin 登记记录
3. 后台列表可见、状态流转 applied→issued、query 无回归

## 五、明确不做（边界）

- ❌ 电子发票平台直连/自动开票
- ❌ 小程序端发票申请入口（保持 C 端零新增）
- ❌ 开票状态通知顾客（人工口头/邮箱确认即可）

## 六、执行时机

P2 试运行前完成；本轮仅定稿规划，不执行——主线（Phase C 全链路 + #9/#10）先行。
