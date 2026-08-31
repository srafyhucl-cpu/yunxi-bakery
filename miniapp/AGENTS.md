# YunxiBakeMiniApp Agent 工作规范

本项目是 `Bakery Commerce Platform` 的 `Storefront MiniApp` 渠道仓，独立于后端项目 `YunxiBakeBot`。

## 启动检查

每次开始任务前先阅读：

1. 本文件。
2. `LOGBOOK.md` 最新条目。
3. `docs/harness-engineering/README.md`。
4. 如果涉及接口、字段、支付、订单、客服、客户群登记或后端协作，先阅读 `docs/api-contract.md`。
5. 如果涉及发布、体验版、真机、审核、支付联调或生产验证，先阅读 `docs/release/manual-acceptance-checklist.md`。

较大任务必须分配 `trace_id`，并在收口时更新 `LOGBOOK.md`。验证和证据规则见 `docs/harness-engineering/core/verification-matrix.md` 与 `docs/harness-engineering/core/evidence-index.md`。

Harness 全面评审与外部对标统一见：`../docs/harness-engineering/HARNESS-MATURITY-REVIEW-20260830.md`。中大型任务交接必须区分 `trace_id`（任务链）与 `run_id`（一次执行），并记录策略摘要、失败分类和可回放结论。

## 项目边界

- 当前仓库只放微信小程序前台渠道代码。
- 后端能力通过 HTTP API 调用 `YunxiBakeBot`，即 `Platform` 主仓；接口契约记录在 `docs/api-contract.md`。
- 不在本项目内实现 AI 对话、订单持久化、支付回调、商品同步等后端逻辑。
- 涉及后端能力变更时，只更新本项目契约和调用代码；后端实现应回到 `YunxiBakeBot` 项目处理。

## 正式上线边界（项目级红线）

- 截至 **2027 年 5 月 31 日（含）**，本小程序仅用于开发、调试和测试，不向真实用户开放，不承接真实用户业务操作。
- **2027 年 6 月只是最早候选上线窗口，不是自动上线日期**。只有项目负责人明确批准后，才允许开放真实用户访问。
- 截至 **2026 年 8 月 14 日**，项目尚不具备受控真实微信支付 / 退款及真实有赞券测试条件。
- 未来条件具备后，如需在正式上线前开展受控真实测试，必须使用授权测试账号、小额可核对交易，事前获得项目负责人批准，并完整记录退款、对账、测试数据清理和证据。
- 编译通过、体验版上传、微信审核通过、生产接口可用或受控测试通过，均不等于已经正式上线。

## 技术栈

- 微信原生小程序
- TypeScript
- MVP 阶段采用默认 WebView 渲染；Skyline / glass-easel 作为后续性能专项按页面评估，不全局启用
- 起步阶段不引入第三方 UI 组件库

## Harness Engineering

- 入口：`docs/harness-engineering/README.md`。
- 追溯：每个较大任务使用 `YYYYMMDD-topic` 格式的 `trace_id`。
- 契约：API 字段变更先更新 `docs/api-contract.md`，再改 `miniprogram/services/` 和页面调用。
- 验证：按 `docs/harness-engineering/core/verification-matrix.md` 选择最低验证。
- 证据：页面截图、微信开发者工具验证、接口联调、审核发布记录登记到 `docs/harness-engineering/core/evidence-index.md`。
- 交接：长任务或上下文重置使用 `docs/harness-engineering/core/agent-handoff-template.md`。
- 防重犯：值得记住的错误统一写入根目录 `ERRORS.md`；旧路径仅作兼容入口，不得复制条目。
- 路线图：跨阶段范围、MVP 后续能力和客户群运营闭环记录在 `docs/roadmap.md`。
- ADR：项目边界、渲染基线、支付/订单归属、发布策略等长期决策记录在 `docs/harness-engineering/adr/`。

管理文档收口时至少检查：

- `LOGBOOK.md` 是否有本轮条目。
- `docs/harness-engineering/core/evidence-index.md` 是否登记文档、命令或报告证据。
- `docs/harness-engineering/README.md` 的入口地图是否仍能覆盖新增文档。
- 若改动影响发布、真机或支付，`docs/release/manual-acceptance-checklist.md` 是否同步。

## 文件操作红线

禁止对未知路径、业务数据、生产目录、有效报告或其他 Agent 的有效工作区执行递归或批量删除。

以下命令不得直接用于未知路径或未列入清理白名单的目录：

- `del /s`
- `rd /s`
- `rmdir /s`
- `Remove-Item -Recurse`
- `rm -rf`

需要清理临时或可重建产物时：

- 允许对本轮创建或已明确列入 `scripts/cleanup-local-artifacts.ps1` 白名单的目录递归扫描并批量删除。
- 执行前必须先运行预览模式，核对目标路径、文件数量和保护边界；复制预览输出的授权令牌，再使用 `-PreviewToken <令牌> -Execute` 执行。
- 清理入口必须校验目标位于当前工作区或项目临时目录，且不得触碰 `backend/data/`、`backend/reports/`、`miniapp/reports/`、`.env*`、`.git/`、生产目录或其他 Agent 的有效工件。
- 自定义临时目录只有在本轮创建、可重新生成、无审计/用户数据且已记录在任务 manifest 中时才可递归清理；不符合条件的目录保留并上报。
- 清理完成后记录范围、文件数量、失败项和剩余目录状态；失败不得静默。

## 下载、安装与临时文件规则

- 不要把下载物、安装包、依赖缓存、构建产物或大体积工具安装到 C 盘。
- 需要安装 npm 依赖时，优先设置缓存目录到非 C 盘，例如：

```powershell
$env:npm_config_cache="D:\Project\.npm-cache"
npm install
```

- 临时文件必须随用随清。
- 清理临时文件优先使用 `scripts/cleanup-local-artifacts.ps1` 的白名单递归批量清理，不再要求 Agent 手工逐个删除。
- 未列入白名单的目录仍按删除红线处理，不得因为“看起来像缓存”就直接递归清理。

## 开发约定

- 页面优先保持小而清晰，业务请求放在 `miniprogram/services/`。
- 通用格式化、购物车本地状态等工具放在 `miniprogram/utils/`。
- API 字段变更先更新 `docs/api-contract.md`，再改页面调用。
- 不把真实 AppID、密钥、支付商户配置写入仓库。
