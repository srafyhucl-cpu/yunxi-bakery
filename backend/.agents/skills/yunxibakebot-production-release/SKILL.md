---
name: yunxibakebot-production-release
description: Use when a YunxiBakeBot change must be pushed or deployed to production. Covers the current server layout, dual-remote push, Git Bundle deployment, systemd verification, and production HTTP proof.
---

# YunxiBakeBot Production Release

## Scope

Use this skill for `D:\Project\YunxiBakeBot` production changes. Do not use it for MiniApp-only code, historical evidence review, or database snapshot work that does not alter the deployed application.

Read [docs/release/server-layout.md](../../docs/release/server-layout.md) before executing a release. The active YunxiBakeBot worktree is `/opt/apps/yunxibakebot`; `/opt/backups/yunxibakebot` is archive-only.

## Release Procedure

1. Confirm the target commit, version, local verification, and repository state.
2. Run pre-deploy evidence commands required by the change class. Quote report paths that contain `{timestamp}`.
3. Push both Git remotes. A push is not a deployment.
4. Run `bash scripts/deploy.sh`. It sends a Git bundle to `/opt/apps/yunxibakebot`, checks production startup configuration, restarts `yunxibakebot`, and waits for loopback `/health` and `/ready`.
5. Verify `systemctl is-active yunxibakebot`, `https://yunxifood.cn/health`, and `https://yunxifood.cn/ready`.
6. Run an applicable callback or positive-path production probe. Record report locations without adding `reports/` artifacts to Git.

## Guardrails

- Do not use `git push` as proof that the service was deployed.
- Do not deploy into `/opt/backups/yunxibakebot`, `/opt/git-repos`, or `/www/wwwroot`.
- Do not print `.env` values, tokens, private keys, or business data.
- Do not use recursive cleanup. Release scripts may only remove files they created at explicit paths.
- Stop and report a mismatch between the expected commit and the production worktree before restarting the service.

## Minimum Evidence

- The target commit is present on both remotes.
- `/opt/apps/yunxibakebot` is the active worktree at the expected commit.
- `yunxibakebot` is active after the release.
- `/health` and `/ready` return the expected ready state.
- Feature-specific proof is recorded when required.
