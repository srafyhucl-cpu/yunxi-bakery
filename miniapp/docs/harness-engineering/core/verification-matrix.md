# Verification Matrix

本文件用于减少收口时的随机性。每次变更完成后，先按变更类型选择最低验证；涉及登录、支付、订单、客服、审核发布等高风险路径时，再执行加强验证。

## 通用基线

| 场景 | 最低验证 |
|---|---|
| 查看工作区 | `git status --short` |
| 文件清单 | `rg --files` |
| JSON 配置 | `Get-Content <json> -Raw \| ConvertFrom-Json \| Out-Null` |
| TypeScript | `npm run typecheck` |
| API 契约影响 | 检查 `docs/api-contract.md` 是否先更新 |
| 文档 | `Test-Path <path>` 并检查无明显占位 |
| 项目管理文档 | 检查 `README.md` / `AGENTS.md` / Harness 入口 / LOGBOOK / evidence 是否同步 |

执行 npm 命令前，如需安装依赖，必须设置 D 盘缓存：

```powershell
$env:npm_config_cache="D:\Project\.npm-cache"
npm install
```

## 按变更类型选择

| 变更类型 | 最低验证 | 加强验证 |
|---|---|---|
| 页面 WXML/WXSS | `npm run check:miniapp` + 微信开发者工具打开对应页面；自定义组件必须使用显式双标签，不能写成 XML 自闭合 | 多机型预览截图，真机预览包编译通过 |
| 页面 TS 逻辑 | `npm run check:miniapp` + `npm run typecheck` | 微信开发者工具手工验证主要交互 |
| `miniprogram/services/` | `npm run typecheck` + 对照 `docs/api-contract.md` | 使用后端测试环境或 mock 数据验证成功/失败态 |
| MiniApp 可观测合约 | `npm run check:observability-contract` | 与 Platform 客户机器人可观测合约和发布验收清单互相对照 |
| 页面/API 覆盖合约 | `npm run check:page-api-coverage` | 与 `YunxiBakeBot` 的 Platform 页面 API 覆盖合约互相对照 |
| miniprogram-ci 发布准备 | `npm run check:miniprogram-ci-readiness` | 配置真实上传密钥后生成体验版二维码，并登记版本号、二维码和真机截图 |
| `miniprogram/utils/` | `npm run typecheck` | 补充最小单元测试或手工用例记录 |
| `app.json` / `project.config.json` | JSON 解析通过 | 微信开发者工具重新编译 |
| API 契约 | 文档字段完整 | 与 `YunxiBakeBot` 后端实现互相对照 |
| 微信登录 | 类型检查 + 手工流程记录 | 真机测试 openid/session 绑定 |
| 下单/支付 | 类型检查 + 流程说明 | 沙箱或测试商户完整链路证据 |
| AI 客服 | 类型检查 + 发送/接收手工验证 | 与后端会话 ID、转人工状态联调 |
| 客户群登记 | `npm run check:miniapp` + `npm run typecheck` + 对照 `docs/api-contract.md` | 体验版或真机从群内/二维码打开登记页，提交记录可在 Platform 后台查看 |
| 订单查询 | 类型检查 + 空态/列表态验证 | 与真实测试订单联调 |
| 发布/审核 | `npm run release:readiness` + `npm run devtools:preview-check` + `npm run check:miniprogram-ci-readiness` + 检查隐私协议、服务类目、合法域名 | 体验版二维码、真机截图、真实支付联调、审核提交记录、回滚说明 |
| Harness 文档 | `Test-Path docs/harness-engineering/...` + `rg` 检查关键口径 | 检查 `LOGBOOK.md`、证据索引、README/AGENTS、发布清单是否同步 |
| 根项目文档 | `Test-Path README.md AGENTS.md LOGBOOK.md` + 搜索旧口径 | 检查入口文档是否指向最新 Harness、路线图、发布清单和 API 契约 |

## 管理文档专项门槛

当任务目标是“更新项目文档 / 项目管理体系 / Harness / 发布流程 / 交接流程”时，最低收口证据必须包含：

- `rg --files docs` 确认文档全集。
- `Test-Path` 覆盖本轮变更的管理文档。
- `rg` 搜索关键旧口径，例如过期端口、过期支付默认值、旧页面数量、缺失入口。
- `git diff --check` 通过。
- `LOGBOOK.md` 和 `docs/harness-engineering/core/evidence-index.md` 有本轮记录。

如果只改文档且不改运行时代码，可以不跑 `npm run typecheck` / `npm run check:miniapp`，但必须在收口中写明原因。

## 首页视觉变更专项门槛

首页视觉、首屏布局、顶部安全区、轮播、商品双列、底部 CTA 等改动，不得只用浏览器 HTML 预览或静态检查作为完成证据。最低收口证据必须包含：

- `npm run check:miniapp` 通过。
- `npm run typecheck` 通过。
- `npm run devtools:open-check` 或 `npm run devtools:preview-check` 生成可用结果；若返回 `needs_manual_confirmation`，必须把报告路径写入收口说明，且不得声称“真机已验证”。
- 至少一张微信开发者工具模拟器截图或真机截图，用于确认顶部安全区、胶囊避让、商品双列和底部 tabBar 不被遮挡。

HTML 预览截图只能作为设计辅助，不能替代微信开发者工具或真机视觉证据。

## 验证结果记录格式

```markdown
- `npm run typecheck` 通过
- 微信开发者工具打开 `pages/products/index`，商品列表/空态/错误态通过
- 未运行真机测试：本轮仅调整文档，无页面行为变更
```

没有运行的验证要明确写原因，不能写成“已验证”。
