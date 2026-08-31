# Harness 交付物模板

> 所有 Harness 评审、验收、门禁和交接交付物均使用本模板的中文人类可读字段；机器字段保持稳定 ASCII。

## 基本信息

- `trace_id`：
- `run_id`：
- `parent_run_id`：无 /
- `task_id`：
- `as_of_commit`：
- `version`：
- `owner`：
- `status`：
- `status_label`：中文状态（机器码）

## 结论四分法

- 结果正确：是 / 否 / 未验证
- 策略合规：是 / 否 / 未验证
- 证据完整：是 / 否 / 未验证
- 可回放：是 / 否 / 未验证

## 验证与证据

- 验证命令及退出码：
- 定向测试或全量测试范围：
- 证据路径：
- `repository_origin`：`monorepo` / `legacy:<仓库>` / `external_unverified`
- 敏感数据处理：

## 未验证范围与后续

- 失败分类：
- 人工介入或批准：
- 未验证范围：
- 残余风险：
- 下一步和责任人：
