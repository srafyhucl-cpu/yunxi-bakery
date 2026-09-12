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

## [2026-08-25] - secrets baseline 受控更新
- old_sha256: f6663f1263258dfd58bac8777cf3e60a35bfadb8be1931199ff5b635b5b9be2d
- new_sha256: f13005d3750eace622e8397c7a539c1d3f9f0b6f1f0aa735875070a9fc37cbcc
- command: detect_secrets scan D:\Project\YunxiBakery\miniapp\package.json（提取标准条目合并入 results["miniapp/package.json"]，Secret Keyword line 17 为 check:secrets 脚本名误报；行尾归一化 LF）
- version: detect-secrets 1.5.0
- trace_id: 20260825-p1-walkthrough-tooling
- approved_by: 项目负责人（20260825-p1-walkthrough-tooling 收口指令授权；误报为 npm scripts 命令名含 secret 字样，非真实密钥）

## [2026-09-12] - secrets baseline 受控更新
- old_sha256: f13005d3750eace622e8397c7a539c1d3f9f0b6f1f0aa735875070a9fc37cbcc
- new_sha256: 09e9ec5d15891fe9ed6297217446044df0cdcc3dfabe87baf5a907e3fc11c57c
- command: detect-secrets scan --no-verify "docs/harness-engineering/core/evidence-index.md"（提取 3 条标准条目合并入 results["docs\harness-engineering\core\evidence-index.md"]，行尾保持 CRLF）
- version: detect-secrets 1.5.0
- trace_id: 20260908-miniapp-commerce-ux-redesign
- approved_by: 项目负责人（2026-09-12 MiniApp 货架与表单视觉收口授权；3 条命中均为历史证据文本中的企微消息 ID 与 check-secret-hygiene 脚本名，不含真实密钥）
