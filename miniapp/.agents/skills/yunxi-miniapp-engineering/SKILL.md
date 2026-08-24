---
name: yunxi-miniapp-engineering
description: Use this skill whenever working in YunxiBakeMiniApp, the self-developed WeChat Mini Program replacing Youzan storefront flows. Trigger for any miniapp feature, page, component, API contract, checkout, WeChat login, WeChat Pay, order, customer-service chat, release-readiness, Harness Engineering, LOGBOOK, ADR, evidence, or handoff work. Also use when the user mentions 有赞迁移, 自研小程序, 微信小程序, Skyline, glass-easel, pages, services, api-contract, or wants to know what to do next in this project.
---

# Storefront MiniApp Engineering

This skill keeps YunxiBakeMiniApp work aligned with the Storefront MiniApp Harness before code, during implementation, and at handoff.

## Project Identity

YunxiBakeMiniApp is the current repository path for the `Storefront MiniApp` channel of `Bakery Commerce Platform`. `YunxiBakeBot` is the current repository path for the `Platform` main repo.

- This repo owns miniapp pages, components, interaction, WeChat capabilities, API clients, login state, local cart state, and lightweight cache.
- `YunxiBakeBot` owns customer master data, product and order rules of truth, AI chat logic, order persistence, payment callbacks, product sync, shop configuration truth, third-party integrations, databases, and backend APIs.
- The two projects communicate through the contract in `docs/api-contract.md`.
- `Yunxi` is the first landed instance / tenant name, not the product name.

## Startup Checklist

At the start of every task:

1. Read `AGENTS.md`.
2. Read the latest entry in `LOGBOOK.md`.
3. Read `docs/harness-engineering/README.md`.
4. If the task touches backend calls or data fields, read `docs/api-contract.md`.
5. Check `git status --short --branch`.
6. Assign a `trace_id` for non-trivial work using `YYYYMMDD-topic`.

If the user asks only for status or explanation, report based on the files above and do not edit.

## Scope Rules

Stay inside the miniapp boundary:

- Put page behavior in `miniprogram/pages/<page>/`.
- Put backend requests in `miniprogram/services/`.
- Put shared formatting and local state helpers in `miniprogram/utils/`.
- Update `docs/api-contract.md` before changing service fields or request/response assumptions.
- Do not implement backend persistence, payment callbacks, AI orchestration, or product sync in this repo.
- Do not add customer master logic, product rules of truth, order rules of truth, CRM logic, third-party sync truth, or a backend configuration system in this repo.

When backend work is required, state the required `YunxiBakeBot` contract/change explicitly and keep this repo to contract/client updates.

## Technical Direction

Use the current project direction unless the user changes it:

- WeChat native Mini Program.
- TypeScript.
- Default WebView rendering for MVP stability; evaluate Skyline / glass-easel later as page-level performance work, not as the global baseline.
- No third-party UI component library at the initial stage.
- Keep pages small and operationally clear.

Prefer practical WeChat-native patterns over adding framework layers. This project is replacing Youzan constraints, so optimize for controllable checkout, orders, customer service, and release evidence.

## Reuse and Configuration Rules

Treat shared behavior as a first-class asset, not an afterthought.

- Prefer shared config, constants, and typed models over page-local literals.
- Do not scatter magic values for tab ids, route paths, status codes, labels, phone numbers, prices, or repeated copy.
- If the same UI pattern or state logic appears in two places, extract it into a component or utility before adding more copies.
- Keep page files as thin orchestrators that compose shared data, not as the source of truth for business labels or layout rules.
- Put reusable catalog, navigation, empty-state, and display configuration in one shared location and reuse it from every page.
- When a value might change by environment, campaign, or store, expose it through config instead of hard-coding it in the page.

## Harness Workflow

For feature work:

```text
read Harness entry
→ define trace_id
→ update API contract/design if needed
→ implement narrowly
→ run verification matrix checks
→ record evidence if useful
→ update LOGBOOK
→ handoff if the task is incomplete
```

Use these files:

- Trace model: `docs/harness-engineering/core/traceability-model.md`
- Verification matrix: `docs/harness-engineering/core/verification-matrix.md`
- Evidence index: `docs/harness-engineering/core/evidence-index.md`
- Mistake ledger: `docs/harness-engineering/core/mistake-ledger.md`
- Handoff template: `docs/harness-engineering/core/agent-handoff-template.md`
- ADR index: `docs/harness-engineering/adr/README.md`

Write an ADR for long-lived decisions: tech stack changes, payment ownership, API boundary changes, release strategy, or migration strategy.

## Verification Guidance

Pick checks from `docs/harness-engineering/core/verification-matrix.md`.

Common checks:

- `git status --short --branch`
- JSON parsing for `app.json`, `project.config.json`, `sitemap.json`
- `npm run check:miniapp` for page registration, route constants, tabBar navigation, and WXML event bindings
- `npm run typecheck` after dependencies are installed
- WeChat DevTools manual verification for UI and page interaction
- Evidence entry for screenshots, release records, API联调, payment/order/customer-service flows

If dependencies are missing, do not blindly install. Follow project rules:

```powershell
$env:npm_config_cache="D:\Project\.npm-cache"
npm install
```

Never put downloads, build caches, or bulky tools on C drive unless the user explicitly approves after being told why it is unavoidable.

## File Safety Rules

Follow project deletion restrictions strictly.

Do not use:

- `del /s`
- `rd /s`
- `rmdir /s`
- `Remove-Item -Recurse`
- `rm -rf`

If deletion is needed, remove one explicit file path at a time. If many files or directories need cleanup, stop and ask the user to handle or approve a manual cleanup approach.

## Response Pattern

When reporting progress or final status, include:

- What changed.
- What was verified.
- What remains risky or unverified.
- Any backend contract or `YunxiBakeBot` follow-up needed.

Keep the answer concise and grounded in file paths.
