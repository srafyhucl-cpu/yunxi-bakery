# 客户群运营一期

## 背景

企业微信客户群不作为群内实时 AI @ 回复入口使用。当前一期改为：客户群触达后，引导客户进入小程序完成结构化登记，再由后台汇总登记内容并生成可复制的群内文案，复杂沟通继续通过微信客服单聊承接。

## 当前闭环

1. 后台创建或绑定客户群。
2. 为客户群创建团购或预订批次。
3. 在客户群内投放小程序登记路径。
4. 客户在 MiniApp 提交结构化登记。
5. 后台查看登记明细、批次汇总和群内文案。
6. 客服在微信客服单聊中继续承接复杂问题。

## 当前入口

- 后台页面：`/customer-groups`
- 后台 API：`/api/v1/admin/customer-groups`
- MiniApp 页面：`/pages/group-registration/index`
- MiniApp API：`/api/v1/miniapp/group-registrations`

## 后续待办

- 客户群增强待办：登记链接/二维码生成、真机群内打开验收、`opengid_to_chatid` 自动转换

## 责任边界

- `Platform.customer` 负责客户群绑定、批次、登记、汇总和状态更新。
- `Storefront MiniApp` 只负责表单录入和个人登记记录展示。
- `Platform.integrations` 只承接必要的第三方对接，不把群运营真相留在前台仓。
