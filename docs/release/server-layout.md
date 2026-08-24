# Production Server Layout

This document is the active operational map for the current production host. It describes current paths only; historical `LOGBOOK.md`, specs, and evidence records retain the paths that were valid when they were written.

## Application Roots

| Service | Current path | Runtime boundary |
|---|---|---|
| YunxiBakeBot | `/opt/apps/yunxibakebot` | systemd service `yunxibakebot`; code, `data/bot.db`, and `venv` |
| Burudushu | `/opt/apps/burudushu` | systemd-managed backend, `frontend/dist`, `venv`, and application logs |

## Deployment And Operations

| Responsibility | Current path | Notes |
|---|---|---|
| Burudushu deployment Git remote | `/opt/git-repos/burudushu.git` | Bare repository with its deployment hook |
| YunxiBakeBot archives | `/opt/backups/yunxibakebot` | Deployment, Git-history, and legacy-test archives; not an application worktree |
| Server monitoring | `/opt/tools/server-monitor` | `server_health_checker.py` and `state.json` |

## Nginx Static Roots

| Site | Current path |
|---|---|
| `burudushu.hclstudio.cn` | `/www/wwwroot/burudushu.hclstudio.cn` -> `/opt/apps/burudushu/frontend/dist` |
| Yunxi static entry | `/www/wwwroot/yunxi.hclstudio.cn` |
| Yueyou | `/www/wwwroot/yueyou` |
| Main site | `/www/wwwroot/hclstudio.cn` |
| Official site | `/www/wwwroot/www.hclstudio.cn` |

## YunxiBakeBot Release Sequence

1. Complete the relevant local checks and record the target commit.
2. Push `origin` and `server`; this only synchronizes Git references.
3. Run `bash scripts/deploy.sh`, which transfers a Git bundle to `/opt/apps/yunxibakebot` and invokes the server-side preflight, restart, and loopback checks.
4. Verify `systemctl is-active yunxibakebot`, then `https://yunxifood.cn/health` and `https://yunxifood.cn/ready`.
5. Run the feature-specific production proof when the change affects behavior beyond service availability.

Do not use `/opt/backups/yunxibakebot` as a deployment target. Do not infer a completed deployment from a successful `git push`.
