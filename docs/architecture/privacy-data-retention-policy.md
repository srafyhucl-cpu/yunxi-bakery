# 隐私数据保留与主体权利策略

> 适用范围：YunxiBakeBot 本地 SQLite 业务库、离线任务和备份资产。
> 关联 trace：`20260711-global-risk-remediation`

## 保留期限

| 数据 | 默认期限 | 自动动作 | 例外 |
|---|---:|---|---|
| `messages` | 90 天 | `scripts/apply_privacy_retention.py` 删除 | 法定争议由人工冻结并登记 |
| `customer_profiles` | 365 天 | 按 `updated_at` 删除 | consent revoke 立即删除 |
| `knowledge_retrieval_logs` | 30 天 | 删除哈希/分类日志 | 不恢复原始 query |
| `miniapp_address_audit` | 365 天 | 删除审计快照 | 法定争议由人工冻结并登记 |
| 已完成/已取消 `orders` | 2555 天 | 按 `updated_at` 删除 | 履约、支付和法定留存优先 |
| `/mnt/backup/yunxibakebot/bot_backup_*.ybak` | 30 天 | AES-256-GCM 加密；只报告，不由应用批量删除 | 运维逐个审核单文件清理 |

未列入表中的数据不得因为“看起来像日志”而自动删除；新增含个人数据的表必须先补充主体导出、删除和保留期合同测试。

## 主体权利链

认证后的前台主体可调用：

- `GET /api/v1/miniapp/privacy/consent`
- `POST /api/v1/miniapp/privacy/consent/grant`
- `POST /api/v1/miniapp/privacy/consent/revoke`
- `GET /api/v1/miniapp/privacy/subject/export`
- `DELETE /api/v1/miniapp/privacy/subject`

删除会清理会话、消息、摘要、转接、订单、地址、地址审计、群登记、分析事件、有赞订单、画像和客户主档关联数据，并保留 `customer_consent_ledger.status=revoked` 作为撤回事实。共享客户主档仍有其他身份链接时只清空主体字段，不删除其他主体数据。

## 检索日志

检索日志的 `query` 永远为空；系统只保存脱敏 query 的 SHA-256、低敏 `query_category`、检索模式和结果统计。任何报表不得重新展示 query 原文。

## 运维边界

```powershell
python scripts/apply_privacy_retention.py --db data/bot.db
```

该命令只清理数据库记录，不触碰备份文件。备份清理必须由运维确认单个明确路径，完成后把销毁证明登记到 Harness evidence index。
