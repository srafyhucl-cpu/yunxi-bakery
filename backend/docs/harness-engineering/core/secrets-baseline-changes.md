# secrets baseline 受控更新记录

> 每次 `.secrets.baseline` 更新必须按受控流程登记：候选副本生成 → diff/哈希校验 → 人工批准 → 本文件登记 → **`git add` 记录文件与 `.secrets.baseline`（同一提交）**。
> `scripts/verify_secrets_baseline.py`（B1.6 起）会阻断：未登记、记录未随同一提交暂存（仅改工作区不算）、记录字段缺失（`old_sha256/new_sha256/command/version/trace_id/approved_by`）、哈希对不匹配本次 HEAD→index 变更，或复用历史已提交记录。
>
> 记录块格式（每个更新一条）：
> ```text
> ## [YYYY-MM-DD] - secrets baseline 受控更新
> - old_sha256: <变更前 baseline 的 SHA-256>
> - new_sha256: <变更后 baseline 的 SHA-256>
> - command: <生成候选副本的确切命令>
> - version: detect-secrets <版本>
> - trace_id: <关联 trace>
> - approved_by: <批准人，须为项目负责人>
> ```

<!-- 无历史受控更新记录 -->
