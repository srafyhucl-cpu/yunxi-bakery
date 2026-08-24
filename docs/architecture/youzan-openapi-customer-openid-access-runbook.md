# 有赞开放平台接入：客户小程序 openid 预导入（接管前置）

> trace_id: `20260812-youzan-openapi-customer-openid-access`
> 状态: 已完成（本地 + 生产全量预导入，命中率 73.87%，10,011 条链接、重复 openid=0）；待同 appid 替换后真实识别验证
> 关联: customer master v1 正式导入（E-20260811-002）、有赞小程序同 appid 替换接管

## 背景与目标

- 商家现有有赞小程序：**主体是商家**，有赞仅为第三方授权 → 接管走「同 appid 替换」。
- 老客户 CSV 导出**无 openid/unionid 字段**（已全表扫描确认），老客户识别只能靠手机号或 openid 预导入。
- 目标：替换前通过有赞开放平台 API 按手机号批量拉取老客户**微信小程序 openid**，预导入 `customer_identity_links`，替换后老客户打开小程序即自动识别，无需重新绑定。

## 结论先行

- 能做什么：`youzan.users.info.query` 支持按 `mobile` 查询，`result_type_list=[2]`（微信小程序）返回 `platform_info.weixin_open_id`（小程序 openid）与 `wechat_info.union_id`。
- 覆盖范围：仅覆盖有手机号客户 **13,551 条**；无手机号 **11,175 条**查不了（需 yz_open_id，CSV 未含）。
- 前提：openid 必须对应商家那个小程序 appid（同 appid 替换成立）；unionid 依赖公众号/小程序在同一开放平台（有赞代注册虚拟开放平台，商家未解绑即可用）。
- 商家侧条件：**已确认具备**「微信粉丝查询 / 店铺客户信息同步 / 微信粉丝关联有赞用户」三个能力包。

## 一、商家侧配合清单

1. 登录有赞开放平台 `open.youzanyun.com` 控制台，创建**自用型应用**（无容器）。
2. 获取 `client_id` / `client_secret`。
3. 获取店铺 `kdt_id`（店铺 id，开放平台后台/店铺设置可查）。
4. 完成**店铺授权**给该自用型应用（一个店铺只能授权一个自用型应用）。
5. 确认能力包（已具备）：微信粉丝查询、店铺客户信息同步、微信粉丝关联有赞用户。
6. 确认 API **计费**与免费额度（`youzan.users.info.query` 标注“是否计费：是”）。
7. 将 `client_id` / `client_secret` / `kdt_id` 交给开发者；凭证走环境变量，**不入库、不入仓、日志脱敏**。
8. 在应用中心控制台配置 **IP 白名单**（调用方公网 IP，含本机/生产服务器）。白名单未配置时：不带 `kdt_id` 的调用会被网关**静默返回空 `user_list`**，带 `kdt_id` 的调用返回 `4007 源IP地址非法调用`。

## 二、技术接入步骤

### 1. 获取 access_token（自用型无容器）

```
POST https://open.youzanyun.com/auth/token
Content-Type: application/json
{
  "client_id": "<client_id>",
  "client_secret": "<client_secret>",
  "authorize_type": "silent",
  "grant_id": "<kdt_id>",
  "refresh": false
}
```

- 返回 `data.access_token`（有效 7 天）+ `expires`（毫秒时间戳）。
- 需缓存并按店铺区分；失效时重取，`refresh=true` 可刷新；**不能频繁调用**（限流）。

### 2. 批量查询客户 openid

```
POST https://open.youzanyun.com/api/youzan.users.info.query/1.0.0?access_token=<token>
```

- 入参（按手机号查）：`mobile=138xxxx`、`result_type_list=[2]`。
- **`result_type_list` 必须传 JSON 数组**（如 `[2]`），传字符串 `"[2]"` 或逗号串会导致空结果/系统异常。
- 实测小程序账号条目：`platform_info.weixin_open_id`（`o` 开头 28 位）+ `wechat_info.union_id`，`wechat_info.wechat_type=2`，`primitive_info.platform_type` 为商家小程序平台值（如 505362，非文档示例 2）。
- 出参（关键字段）：
  - `user_list[].platform_info.weixin_open_id` → 微信 openid（28 位，`o` 开头）
  - `user_list[].wechat_info.union_id` → 微信 unionid
  - `user_list[].wechat_info.wechat_type` → 1 公众号 / 2 小程序
  - `user_list[].mobile_info.mobile` → 手机号
  - `user_list[].primitive_info.yz_open_id` → 有赞用户 id
- 查询优先级：`yz_open_id > mobile > weixin_union_id > weixin_open_id`。
- 反查示例：`youzan.scrm.customer.detail.get`（doc 1433）按 `yz_open_id`/手机号查客户详情，返回 `yz_open_id`（有赞统一 ID，非微信 openid），可作辅助。

### 3. 预导入 customer_identity_links

- `identity_type=miniapp_openid`，`identity_value=<openid>`，`source_system=youzan`，`verification_status=verified`，`confidence_score` 高。
- `unionid` 可另存 `identity_type=wecom_union` 类型（表已支持）。
- 以 `primary_phone` 与 `customer_master` 对账，挂到对应 `customer_id`。
- 幂等：同一 `(tenant_id, identity_type, identity_value)` 唯一，先查后插。

### 4. 对账与校验

- 统计：查询成功数 / 命中 openid 数 / 导入数 / 未命中数。
- 校验：重复 openid = 0；openid 与手机号归属一致（抽样）。
- 替换后验证：客户打开小程序 `wx.login` → 后端按 openid 命中主档 → 识别成功。

## 三、官方文档链接

| 用途 | 链接 |
| --- | --- |
| 账号体系说明（openid/unionid/yz_open_id 规则） | https://doc.youzanyun.com/v2/doc/cloud/token/NVrywaFqSiaE1Okiv1hchpyonpe |
| `youzan.users.info.query`（用户查询，返回 openid/unionid） | https://doc.youzanyun.com/detail/API/0/2193 |
| `youzan.scrm.customer.detail.get`（客户详情，返回 yz_open_id） | https://doc.youzanyun.com/detail/API/0/1433 |
| access_token 获取（自用型无容器） | https://doc.youzanyun.com/resource/doc/3031 |
| 如何查看 client_id / client_secret | https://doc.youzanyun.com/resource/doc/3886/3888 |

## 四、注意事项与风险

- **计费**：接口按调用计费，13,551 条量级需确认成本与免费额度；建议分批 + 失败退避。
- **IP 白名单**：调用方公网 IP 必须加入应用白名单，否则网关静默返回空结果或 `4007`（详见商家侧清单第 8 条）。
- **`result_type_list` 传参**：必须是 JSON 数组 `[2]`，字符串形式不生效。
- **限流**：access_token 必须缓存，避免频繁换取；批量查询控制并发。
- **隐私**：openid/unionid/手机号属个人信息，仅用于身份关联；日志脱敏，凭证入 `.env`。
- **yz_open_id 不稳定**：会随账号合并变化，不做稳定主键。
- **openid 与 appid 强绑定**：必须确认返回的 openid 属于商家那个有赞小程序 appid，否则同 appid 替换后无效。
- **覆盖局限**：无手机号客户（11,175 条）本次覆盖不到。**已决策不做对话报号绑定**（聊天自报手机号可冒报他人号码，身份安全风险）。未识别客户一律按新用户处理；认证/资质到位后可选用微信官方手机号授权组件（getPhoneNumber，微信验证真手机号，冒充不了）补强。

## 五、验收标准

1. 能换取 access_token 并成功调用 `youzan.users.info.query`。
2. 13,551 条有手机号客户查询完成，命中率与导入数有统计。
3. openid 预导入 `customer_identity_links`，与主档手机号一致，重复 openid = 0。
4. 测试环境用真实 openid 登录验证命中主档（待商家完成同 appid 替换后执行）。

## 开放问题

- ~~商家是否有有赞开放平台开发者资质~~ → **已确认**：自用型应用已建好，三个能力包已具备，API 有免费额度。
- API 计费成本与额度确认。
- ~~无手机号客户是否通过客服工单向有赞申请 yz_open_id 导出~~ → **已决策**：不申请，未识别客户按新客处理。
