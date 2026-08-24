# miniprogram-ci 发布准备合约

> trace_id: `20260707-miniapp-miniprogram-ci-readiness`

本文件用于承接 GitHub 参考计划中“MiniApp 补 miniprogram-ci 预览 / 上传脚本”的方向。当前先冻结安全边界和准备度检查，不在本地自动上传体验版，不提交任何微信平台密钥。

## 当前边界

- `YunxiBakeMiniApp` 只负责小程序前台渠道，不保存支付、订单、会员或客户主档业务真相。
- `miniprogram-ci` 只用于未来生成预览包、体验版或上传产物，不改变页面运行时代码。
- 没有微信平台上传私钥时，检查结果允许是 `needs_configuration`，但不能伪装成体验版已上传。
- 任何私钥、证书、机器人上传凭据都不得进入 Git 跟踪，也不得写入仓库内配置文件。

## 自动检查

运行：

```powershell
npm run check:miniprogram-ci-readiness
```

该命令会生成：

```text
reports/miniprogram-ci/latest.json
reports/miniprogram-ci/miniprogram-ci-readiness-<timestamp>.json
```

检查内容：

| 检查 | 说明 |
|---|---|
| project config | `project.config.json` 必须是小程序项目、`miniprogramRoot=miniprogram/`、AppID 不是 `touristappid` |
| dependency | 检查 `package.json` 是否声明 `miniprogram-ci`，以及本地是否已安装 |
| private key hygiene | 检查 Git 是否跟踪 `.pem`、`.p12`、`.pfx`、`.key` 或 `private_key` 文件 |
| private key path | 如配置 `MINIPROGRAM_CI_PRIVATE_KEY_PATH`，必须指向仓库外的明确文件 |
| upload env | 检查 `MINIPROGRAM_CI_ROBOT`、`MINIPROGRAM_CI_VERSION`、`MINIPROGRAM_CI_DESC` 是否已准备 |

## 环境变量

| 变量 | 用途 | 要求 |
|---|---|---|
| `MINIPROGRAM_CI_PRIVATE_KEY_PATH` | 微信小程序上传私钥路径 | 必须是仓库外文件；不得提交到 Git |
| `MINIPROGRAM_CI_ROBOT` | 微信上传机器人编号 | 1 到 30 的整数 |
| `MINIPROGRAM_CI_VERSION` | 上传版本号 | 体验版 / 上传前必须配置 |
| `MINIPROGRAM_CI_DESC` | 上传说明 | 体验版 / 上传前必须配置 |

AppID 当前从 `project.config.json` 读取。若后续 CI 需要多环境 AppID，应先补发布脚本参数和检查规则，再接入上传。

## 接入发布门槛

`npm run release:readiness` 已纳入 `miniprogram-ci readiness contract`。当前无密钥或未安装 `miniprogram-ci` 时，该检查会通过命令退出但报告 `needs_configuration`，表示“没有发现安全失败，但还不能上传体验版”。

只有出现以下情况才应失败：

- 小程序项目配置错误。
- 上传私钥路径指向仓库内部。
- Git 跟踪了疑似私钥或证书文件。
- 上传机器人编号非法。

## 真实上传前置条件

真实上传体验版前必须补齐：

1. 微信公众平台上传密钥已创建并放在仓库外或 CI 临时目录。
2. `miniprogram-ci` 依赖已安装；安装时 npm cache 必须指向 D 盘或 CI 临时目录。
3. `MINIPROGRAM_CI_PRIVATE_KEY_PATH`、`MINIPROGRAM_CI_ROBOT`、`MINIPROGRAM_CI_VERSION`、`MINIPROGRAM_CI_DESC` 均已配置。
4. `npm run check:secrets` 通过。
5. `npm run release:readiness` 除外部 DevTools / 真机门槛外无新增失败。
6. 上传结果、二维码、版本号和真机截图登记到 `docs/harness-engineering/core/evidence-index.md`。

## 不替代项

本合约不替代：

- 微信开发者工具编译和按钮触达扫描。
- 体验版二维码真机扫码。
- iOS / Android 真机截图或录屏。
- 真实微信登录。
- 真实微信支付商户联调。
- 微信公众平台合法域名、隐私协议、服务类目和审核提交记录。
