# 芸熙烘焙自研商城 MVP 产品规格

- trace_id: 20260616-full-mvp
- status: proposed
- date: 2026-06-16
- owner: YunxiBakeMiniApp / YunxiBakeBot

> 当前状态说明：本文件保留为 MVP 初始产品规格和实施切片记录。当前权威路线图见 `docs/roadmap.md`，当前 API 字段和支付/客户群登记契约见 `docs/api-contract.md`，当前项目管理闭环见 `docs/project-management.md`。

## 目标

同步推进微信小程序 C 端和后台管理系统，交付一个可替代有赞基础购物链路的自研商城 MVP。

MVP 不追求一次性覆盖有赞所有能力，而是先完成三件事：

1. 用户能在小程序完成浏览商品、加入购物车、填写结算信息、创建订单草稿、查看订单入口。
2. 管理员能在后台管理商品、推荐位、店铺装修配置、订单与客服入口。
3. 小程序页面由同一份装修 JSON 驱动，后台后续只需发布配置，小程序无需重写页面结构。

## 系统边界

### YunxiBakeMiniApp

负责 `Storefront MiniApp` 前台渠道：

- 渲染后台发布的装修 JSON。
- 商品浏览、详情、购物车、结算、我的、客服入口。
- 本地购物车状态和轻量 UI 状态。
- 调用 `YunxiBakeBot` 提供的 miniapp API。

小程序不负责：

- 订单持久化。
- 支付回调。
- 商品同步。
- AI 客服编排。
- 后台管理权限。

### YunxiBakeBot

负责 `Platform` 主仓后端和后台：

- miniapp API。
- admin API。
- Vue 管理后台 `web/admin`。
- 商品、订单、装修配置、客服、知识库、观测与设置。
- 后续对接微信支付、有赞存量数据、企业微信客服等能力。

## MVP 模块

### 小程序 C 端

| 模块 | MVP 能力 |
|---|---|
| 首页 | 搜索入口、轮播图、分类入口、公告、会员/充值入口、订购须知、推荐商品、客服浮窗 |
| 全部蛋糕 | 按货架分组展示商品，支持进入详情和快速加购 |
| 商品详情 | 图片、标题、副标题、价格、销量/标签、规格/说明、加入购物车、立即购买 |
| 购物车 | 空态推荐、商品列表、数量调整、删除、合计、去结算 |
| 结算 | 收货/自提信息、期望时间、备注、订单草稿创建 |
| 订单 | 列表入口和空态，后续接订单详情 |
| 我的 | 会员卡、余额/积分/券码入口、订单中心、购物车、收货地址、个人信息、客服入口 |
| 客服 | 先保留入口与基础消息页，后续接 `YunxiBakeBot` 会话 |

### 后台管理系统

沿用 `D:\Project\YunxiBakeBot\web\admin` 的 Vue 3 + Element Plus 后台，不在小程序仓库重复搭建后台。

| 模块 | MVP 能力 |
|---|---|
| 概览 | 今日订单、销售额、待处理、商品状态、配置发布状态 |
| 商品管理 | 商品列表、搜索、上下架、同步状态、价格/库存展示、主推款 |
| 店铺装修 | 表单化装修编辑器、模块排序、手机预览、保存草稿、发布 |
| 订单管理 | 订单列表、订单详情、状态流转，先覆盖草稿/待支付/待制作/已完成 |
| 客服与知识库 | 沿用现有 AI 对话、知识配置、转人工能力 |
| 店铺设置 | 店名、客服电话、客服微信、营业时间、配送/自提说明、支付配置状态 |

第一版装修编辑器不做复杂拖拽。采用“模块列表 + 手机预览 + 右侧表单编辑”的方式，后续再补拖拽排序和多页面模板。

## 装修 JSON

小程序首页和主要营销区域由页面配置驱动。

```json
{
  "pageId": "home",
  "version": 1,
  "status": "published",
  "updatedAt": "2026-06-16T00:00:00+08:00",
  "theme": {
    "primaryColor": "#e94b4b",
    "accentColor": "#9bb879",
    "backgroundColor": "#f7f7f7"
  },
  "blocks": [
    {
      "id": "hero-1",
      "type": "heroCarousel",
      "enabled": true,
      "props": {
        "items": [
          {
            "imageUrl": "https://example.com/cake.jpg",
            "linkType": "product",
            "linkTarget": "p_001"
          }
        ]
      }
    },
    {
      "id": "notice-1",
      "type": "noticeBar",
      "enabled": true,
      "props": {
        "text": "定制蛋糕 + 客服微信：13240240418"
      }
    },
    {
      "id": "shelf-1",
      "type": "productShelf",
      "enabled": true,
      "props": {
        "title": "12年招牌必吃榜",
        "source": "manual",
        "productIds": ["p_001", "p_002"]
      }
    }
  ]
}
```

### MVP block 类型

| type | 用途 |
|---|---|
| `searchBar` | 搜索入口 |
| `heroCarousel` | 首页轮播图 |
| `noticeBar` | 公告条 |
| `categoryGrid` | 分类入口 |
| `quickLinks` | 积分商城、充值中心等快捷入口 |
| `membershipBanner` | 注册会员/会员权益横幅 |
| `noticeList` | 蛋糕/面包/配送订购须知 |
| `productShelf` | 商品货架 |
| `memberSummary` | 会员摘要 |
| `serviceGrid` | 我的页服务入口 |
| `richText` | 产品信息、尺寸重量规格、温馨提示 |

## 数据流

1. 后台编辑装修草稿。
2. 后台发布后写入 `YunxiBakeBot` 配置存储。
3. 小程序启动或进入页面时请求 `/api/v1/miniapp/pages/{pageId}`。
4. 小程序根据 `blocks[].type` 选择组件渲染。
5. 商品货架中的 `productIds` 通过商品 API 补全价格、图片、库存和状态。
6. 用户加购后写入本地购物车。
7. 结算页提交订单草稿到 `YunxiBakeBot`。

## API 范围

### Miniapp API

- `GET /api/v1/miniapp/pages/{pageId}`：获取已发布页面装修配置。
- `GET /api/v1/miniapp/products`：获取商品列表，支持分类和 ids 过滤。
- `GET /api/v1/miniapp/products/{productId}`：获取商品详情。
- `POST /api/v1/miniapp/orders`：创建订单草稿。
- `GET /api/v1/miniapp/orders`：获取当前用户订单列表。
- `POST /api/v1/miniapp/auth/login`：微信登录换取后端会话。
- `POST /api/v1/miniapp/chat/messages`：发送客服消息。

### Admin API

- `GET /api/v1/admin/shop-config/pages/{pageId}`：读取草稿/已发布装修配置。
- `PUT /api/v1/admin/shop-config/pages/{pageId}/draft`：保存装修草稿。
- `POST /api/v1/admin/shop-config/pages/{pageId}/publish`：发布装修配置。
- `GET /api/v1/admin/products`：商品列表。
- `POST /api/v1/admin/products/{productId}/toggle-active`：上下架。
- `POST /api/v1/admin/shop-config/featured-products`：保存主推款。
- `GET /api/v1/admin/orders`：订单列表。
- `GET /api/v1/admin/orders/{orderId}`：订单详情。

## 实施顺序

### Slice 1：配置驱动小程序壳子

- 新增小程序 `config`、`constants`、`types` 和 mock page config。
- 首页和全部蛋糕页使用装修 JSON 渲染。
- 抽商品卡、货架、公告、分类、会员摘要等复用组件。
- 购物车读取同一份 mock catalog。

### Slice 2：后台装修 MVP

- 在 `YunxiBakeBot web/admin` 新增“店铺装修”路由。
- 以表单方式编辑首页 blocks。
- 手机预览与 JSON 草稿并排。
- 保存草稿、发布按钮先接 mock/admin config service 或现有 config repo。

### Slice 3：Miniapp API 对接

- 在 `YunxiBakeBot` 新增 miniapp page config API。
- 小程序 service 优先读 API，失败时回退 mock。
- 商品 API 对齐 `youzan_products` 和知识库商品数据。

### Slice 4：购物车与订单草稿

- 小程序结算页组装订单草稿。
- 后端保存订单草稿。
- 后台订单页能看到订单。

### Slice 5：会员、客服、支付前置

- 我的页接会员摘要接口。
- 客服页接现有 AI 会话。
- 支付接口只预留状态和配置检查，不在 MVP 首轮强行上线真实支付。

## 验收标准

- 小程序可用 mock 配置跑通：首页 → 商品列表 → 详情 → 加购 → 购物车 → 结算。
- 后台可进入店铺装修页，编辑首页模块并看到手机预览。
- 小程序页面无散落的核心业务魔法值，分类/公告/货架/会员入口来自配置。
- `npm run typecheck` 在小程序仓库通过。
- `npm run build` 或 `npm run typecheck` 在 `YunxiBakeBot/web/admin` 通过。
- API 契约文档记录 miniapp 和 admin 的页面装修接口。

## 暂不纳入 MVP

- 复杂拖拽装修。
- 多店铺、多角色权限。
- 真实微信支付闭环。
- 优惠券核销、充值、积分商城的完整交易能力。
- 手机端完整装修编辑器。
- 从有赞后台自动迁移装修页面。
