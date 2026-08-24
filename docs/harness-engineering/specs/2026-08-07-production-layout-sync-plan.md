# Production Layout Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align reusable release guidance and executable production checks with the current `/opt` and `/www/wwwroot` server layout.

**Architecture:** Treat `docs/release/server-layout.md` as the active topology reference. The production-release skill and current scripts reference it; historical LOGBOOK and evidence records retain their original paths as audit facts.

**Tech Stack:** Bash, Python, Node.js, GitHub Actions, systemd, Nginx, Markdown.

## Global Constraints

- Do not use recursive or bulk delete commands.
- Do not print secrets, tokens, database content, or private keys.
- `git push` updates references only; production deployment uses `bash scripts/deploy.sh`.
- Preserve historical deployment records without mass path replacement.

---

### Task 1: Publish the active server layout

**Files:**
- Create: `docs/release/server-layout.md`
- Modify: `docs/harness-engineering/README.md`

- [x] Document application, bare-Git, backup, monitoring, and Nginx static paths.
- [x] Link the topology from the Harness entrypoint.

### Task 2: Make the release workflow discoverable

**Files:**
- Create: `.agents/skills/yunxibakebot-production-release/SKILL.md`
- Modify: `docs/AGENTS/skill-reference.md`

- [x] Add the current deployment sequence and verification gates.
- [x] Reference the project-local skill from the skill index.

### Task 3: Protect executable path consumers

**Files:**
- Modify: `tests/scripts/test_deploy_server_contract.py`
- Modify: `D:\Project\YunxiBakeMiniApp\scripts\run-production-admin-browser-smoke.mjs`

- [x] Assert bundle deployment scripts target `/opt/apps/yunxibakebot`.
- [x] Read production admin credentials from the current backend `.env` path.

### Task 4: Verify and record the change

**Files:**
- Modify: `LOGBOOK.md`
- Modify: `docs/harness-engineering/core/evidence-index.md`
- Modify: `D:\Project\YunxiBakeMiniApp\LOGBOOK.md`
- Modify: `D:\Project\YunxiBakeMiniApp\docs\harness-engineering\core\evidence-index.md`

- [x] Run targeted deployment tests, syntax checks, MiniApp static/type checks, and diff validation.
- [x] Record local-only evidence and explicitly retain production verification as out of scope.
