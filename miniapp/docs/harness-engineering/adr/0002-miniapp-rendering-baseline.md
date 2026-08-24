# ADR-0002 MVP 阶段采用默认 WebView 渲染基线

- status: accepted
- date: 2026-06-17
- decision_owner: YunxiBakeMiniApp
- trace_id: 20260617-miniapp-rendering-baseline
- related_docs:
  - AGENTS.md
  - README.md
  - docs/project-management.md
  - docs/harness-engineering/core/verification-matrix.md
  - docs/release/manual-acceptance-checklist.md
- review_trigger: Skyline 页面级试点、基础库升级、真机布局问题复发或发布前视觉门槛变化时回看

## 背景

首页真机预览暴露出开发者工具和真机渲染差异：顶部搜索入口靠近状态栏和微信胶囊区域，商品双列在真机上退化成单列。项目此前全局启用了 `renderer: "skyline"`、`componentFramework: "glass-easel"`，并使用 `libVersion: "latest"`，导致渲染引擎、基础库和真机环境同时变化，问题定位成本较高。

项目当前优先目标是完成自研小程序 MVP，稳定首页、商品、购物车、订单、客服和我的主链路，而不是提前承担新渲染引擎迁移风险。

## 决策

MVP 阶段采用默认 WebView 渲染作为全局基线：

- 固定微信基础库为 `3.16.0`，不使用 `latest`。
- 从 `app.json` 移除全局 `renderer: "skyline"`、`rendererOptions.skyline` 和 `componentFramework: "glass-easel"`。
- 继续使用微信原生小程序、TypeScript、原生 tabBar，不引入第三方 UI 组件库。
- `navigationStyle: "custom"` 暂时保留，但必须通过统一布局基座处理状态栏、胶囊和底部安全区，不允许页面自行猜测安全距离。
- 关键双列和多列布局优先使用真机更稳的 flex wrap 与明确宽度，避免把核心页面布局建立在 `grid` 差异表现上。
- Skyline 作为后续性能专项保留，不作为 MVP 的默认技术基线。

## 后果

正向影响：

- 降低开发者工具和真机渲染不一致的风险。
- 让首页和核心交易页面优先稳定，减少 UI 细节被渲染引擎差异反复打断。
- 基础库固定后，问题更容易复现和回归。

代价：

- 暂时放弃 Skyline 在长列表、动画、手势和复杂滚动上的潜在性能收益。
- 后续若要迁移 Skyline，需要按页面专项评估并补充真机截图证据。
- 保留 custom navigation 仍然需要维护安全区基座。

## 替代方案

1. 继续全局 Skyline：理论性能更好，但当前已在真机暴露布局差异，不适合 MVP 阶段继续扩大风险。
2. 局部 Skyline：未来可用于商品长列表、沉浸式详情、复杂动效页面，但需要每页单独验收。
3. 改用第三方跨端框架：会引入额外抽象层，不符合当前“微信原生能力优先”和可控发布的目标。

## 验证与回看

- 本决策落地后运行 `npm run check:miniapp` 和 `npm run typecheck`。
- 使用微信开发者工具固定基础库 `3.16.0` 重新编译首页。
- 需要用户真机复拍首页，重点确认顶部搜索入口不再进入系统状态栏/胶囊区域，今日推荐商品恢复两列。
- 当核心 MVP 链路稳定后，可单独创建 Skyline 评估任务，优先评估商品列表页。
