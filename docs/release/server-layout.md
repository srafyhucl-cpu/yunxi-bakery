# Production Server Layout

This document is the active operational map for the current production host. It describes current paths only; historical `LOGBOOK.md`, specs, and evidence records retain the paths that were valid when they were written.

> Last verified: 2026-11-01 against the live host `47.94.102.250`.

## Application Roots

| Service | Current path | Runtime boundary |
|---|---|---|
| YunxiBakeBot (live) | `/opt/apps/yunxi-bakery/backend` | systemd service `yunxi-bakery`; code, `data/bot.db`, `data/product-images`, `data/embeddings.*` |
| YunxiBakeBot Python env | `/opt/apps/yunxi-bakery/venv` | Python 3.13; always call `venv/bin/python -m pip`, not `venv/bin/pip` (see Legacy) |
| Burudushu | `/opt/apps/burudushu` | systemd-managed backend, `frontend/dist`, `venv`, and application logs |

## Deployment And Operations

| Responsibility | Current path | Notes |
|---|---|---|
| YunxiBakeBot deployment target | `/opt/apps/yunxi-bakery/backend` | Not a Git worktree; deployed by file sync, keeps its own `data/` and `.env` |
| YunxiBakeBot archives | `/opt/backups/yunxibakebot` | Database snapshots and per-deploy `backend-<timestamp>.tar.gz`; not an application worktree |
| Nginx vhost | `/etc/nginx/sites-enabled/yunxifood.cn` -> `/etc/nginx/sites-available/yunxifood.cn` | Reverse proxies `/` and `/health` to `127.0.0.1:7001` |
| TLS certificate | `/etc/letsencrypt/live/yunxifood.cn/` | Let's Encrypt, renewed by `certbot.timer` |
| ACME webroot | `/var/www/html` | Must match `webroot_path` in `/etc/letsencrypt/renewal/yunxifood.cn.conf` |
| Server monitoring | `/opt/tools/server-monitor` | `server_health_checker.py` and `state.json` |

## Nginx Static Roots

| Site | Current path |
|---|---|
| `burudushu.hclstudio.cn` | `/www/wwwroot/burudushu.hclstudio.cn` -> `/opt/apps/burudushu/frontend/dist` |
| Yunxi static entry | `/www/wwwroot/yunxi.hclstudio.cn` |
| Yueyou | `/www/wwwroot/yueyou` |
| Main site | `/www/wwwroot/hclstudio.cn` |
| Official site | `/www/wwwroot/www.hclstudio.cn` |

The admin SPA is not an Nginx static root: it ships inside the repository at `backend/web/admin/dist` and is served by the app at `https://yunxifood.cn/admin`.

## YunxiBakeBot Release Sequence

The production host has limited resources and must not run `npm install` / `npm run build` or compile Python wheels. Build locally, ship artifacts, restart.

1. Merge the change into the deploy branch and record the target commit.
2. Build the admin frontend locally (`npm run build` in `backend/web/admin`) and commit the updated `backend/web/admin/dist`, because the server does not build it.
3. Snapshot the live app on the server before changing files:
   `tar -czf /opt/backups/yunxibakebot/backend-<stamp>.tar.gz --exclude=backend/data /opt/apps/yunxi-bakery/backend`
4. Sync the repository's `backend/` tree to `/opt/apps/yunxi-bakery/backend`, excluding `data/`, `.env`, `venv/`, `__pycache__/`, `node_modules/`, `reports/`. `data/` and `.env` must survive the sync.
5. Install dependencies with the CPU torch index first, then the lock file:
   `venv/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==<pinned>`
   `venv/bin/python -m pip install -r backend/requirements.txt`
6. `systemctl restart yunxi-bakery`, then `systemctl is-active yunxi-bakery`.
7. Verify `https://yunxifood.cn/health`, `https://yunxifood.cn/ready`, `https://yunxifood.cn/admin`, and one product API response (`orderMode` / `variants` / `options` / `imageUrl`).
8. Run the feature-specific production proof when the change affects behavior beyond service availability.

Do not use `/opt/backups/yunxibakebot` as a deployment target. Do not infer a completed deployment from a successful `git push`.

## Legacy Paths (do not use)

| Path | Why it is stale |
|---|---|
| `/opt/apps/yunxibakebot` | Old Git checkout with an old commit; unit `yunxibakebot.service` is disabled. Historical `scripts/deploy.sh` still points here and must not be run as-is |
| `/opt/yunxibakebot` | Old ACME webroot referenced by a stale certbot renewal config; caused TLS renewals to fail silently |
| `/www/server/panel/vhost/nginx/yunxifood.cn.conf` | Baota vhost copy that is not included by `/etc/nginx/nginx.conf`; editing it has no effect |

Two operational traps previously caused incidents:

- The certbot webroot drifted away from the Nginx webroot, so renewals returned 404 and the certificate expired unnoticed for two months. `certbot renew --dry-run` after any Nginx change.
- `venv/bin/pip` still carries a shebang from the pre-move `/opt/apps/yunxi-bakery-staging` path. Use `venv/bin/python -m pip` until the venv is recreated.
