# 生产合成主体删除专项设计

## 目标

在不读取、不导出、不删除真实客户数据的前提下，使用生产进程、生产 SQLite schema、真实 Bearer JWT 和真实隐私 API，验证主体导出与删除闭环。

## 安全边界

- 只允许 `http://127.0.0.1` 或 `http://localhost` 服务根地址，禁止访问公网入口。
- 必须显式提供 `--confirm-production-synthetic-subject` 才能执行。
- 每次生成带 `remediation-prod-subject-` 前缀的随机主体，只按精确主键写入合成记录。
- 报告不输出 JWT、主体 ID、导出正文、客户内容或订单明细。
- 无论验证成功或异常，`finally` 都按精确主键逐表清理合成记录，并验证零残留。

## 同构链路

1. 对生产数据库执行 `PRAGMA integrity_check`。
2. 写入 session、message、profile、consent、address、order、customer master 和 identity link 合成记录。
3. 使用生产 `StorefrontAuthService` 签发真实 Bearer JWT。
4. 调用运行中生产进程的 `GET /api/v1/miniapp/privacy/subject/export`。
5. 调用运行中生产进程的 `DELETE /api/v1/miniapp/privacy/subject`。
6. 验证七类关联记录归零、consent 为 `revoked`、数据库完整性正常。
7. 清理唯一合成 consent，确认所有合成记录零残留。

## 执行入口

```bash
cd /opt/yunxibakebot
venv/bin/python scripts/verify_production_subject_deletion.py \
  --db /opt/yunxibakebot/data/bot.db \
  --base-url http://127.0.0.1:7001 \
  --confirm-production-synthetic-subject \
  --json
```

通过标准：8 项检查全部通过，`boundaries.synthetic_residue=false`，生产 health、ready 和 systemd 状态保持正常。
