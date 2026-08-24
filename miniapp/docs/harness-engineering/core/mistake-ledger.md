# Mistake Ledger

本文件记录值得防重犯的错误。只有当错误具备复发风险、影响质量或会浪费明显时间时才记录。

## M-20260617-顶部安全区只靠padding不够

- date: 2026-06-17
- trace_id: 20260617-mobile-layout-pass
- severity: medium
- symptom: 真机页面滚动后顶部仍会被状态栏/胶囊遮挡，内容没有真正从可视区顶部开始
- root_cause: 只在页面正文上加安全区 padding，滚动容器自身没有占出顶部空间，导致 Skyline 真机下首屏仍贴顶
- missed_signal: 真机截图已经提示顶部遮挡，但我先按常规页面 padding 处理，没有先把安全区验证到滚动壳层
- new_guardrail: 页面顶部避让优先通过滚动内容内的显式 spacer 或壳层布局实现，不再只依赖正文 padding；真机视觉问题先检查滚动容器边界
- verification_added: `rg -n 'page-top-spacer|padding: calc\\(var\\(--yunxi-custom-nav-space|class="page-shell"|class="chat-page"|--yunxi-custom-nav-space' miniprogram/pages miniprogram/app.wxss miniprogram/utils/layout.ts`
- owner: miniapp agent

## M-20260618-WXML标签不配平未被静态检查拦截

- date: 2026-06-18
- trace_id: 20260618-home-wxml-compile-fix
- severity: high
- symptom: 微信开发者工具首页白屏，控制台报 `./pages/home/index.wxml expect end-tag view, near scroll-...`，`npm run check:miniapp` 此前仍显示通过
- root_cause: 首页改为“固定顶部安全区 + pinned 区 + 独立滚动区”后，保留了 `</scroll-view>` 关闭标签却漏掉 `<scroll-view class="page-scroll"...>` 开始标签；静态脚本只检查页面注册、事件绑定和 data 根引用，没有检查 WXML 基础标签栈
- missed_signal: 用户截图里的错误行已经指向 `</scroll-view>`，但前一轮验证过度相信 `check:miniapp`，没有补充标签结构防线
- new_guardrail: `scripts/check-miniapp.mjs` 新增 `checkWxmlTagBalance`，每次 `npm run check:miniapp` 都检查 WXML 关闭标签与最近未闭合标签是否匹配
- verification_added: `npm run check:miniapp` 已覆盖 11 个页面 WXML 标签配平并通过；`npm run devtools:preview-check` 已通过并生成二维码报告
- owner: miniapp agent

## M-20260707-自定义组件自闭合真机预览编译风险

- date: 2026-07-07
- trace_id: 20260707-miniapp-real-device-closing-tag-fix
- severity: high
- symptom: 真机预览控制台出现 `__wxAppCode__ is not defined`、`adapter page not exists` 或 `routeDone with a webviewId ... is not found`，页面在真机包里无法正常显示
- root_cause: 多个页面把自定义组件写成 `<session-notice ... />` XML 自闭合形式；IDE 模拟器可能宽松解析，但真机预览打包编译路径会把它变成不稳定 WXML 结构
- missed_signal: 此类写法能通过已有标签配平检查，因为脚本把 `/>` 当作合法单标签处理；此前没有把“小程序自定义组件必须显式闭合”写入项目规则
- new_guardrail: WXML 中所有自定义组件使用 `<component ...></component>` 显式双标签；页面 WXML/WXSS 验证门槛同步加入该规则，真机编译异常先排查自定义组件闭合方式
- verification_added: `rg -n '<session-notice[^>]*\\/>' miniprogram/pages` 应无命中；相关页面继续运行 `npm run check:miniapp` 和 `npm run typecheck`
- owner: miniapp agent

## 模板

```markdown
## M-YYYYMMDD-短标题

- date:
- trace_id:
- severity: low | medium | high
- symptom:
- root_cause:
- missed_signal:
- new_guardrail:
- verification_added:
- owner:
```

## 记录规则

- 不写甩锅式描述，只写可改进的系统信号和防线。
- `new_guardrail` 必须是规则、检查、文档、测试或流程中的一种。
- 如果同类问题第二次出现，优先补自动化检查或更明确的 AGENTS 规则。
- 如果错误来自项目管理文档口径过期，必须同时检查 `README.md`、`AGENTS.md`、`docs/harness-engineering/README.md`、`docs/release/manual-acceptance-checklist.md`、`LOGBOOK.md` 和证据索引是否存在同类旧口径。
