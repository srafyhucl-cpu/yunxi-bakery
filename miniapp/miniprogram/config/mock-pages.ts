import { SHOP_CONFIG, THEME_TOKENS } from "./shop";
import type { ShopPageConfig } from "../types/page-config";

export const MOCK_PAGE_CONFIGS: Record<string, ShopPageConfig> = {
  home: {
    pageId: "home",
    version: 1,
    status: "published",
    updatedAt: "2026-06-16T00:00:00+08:00",
    theme: THEME_TOKENS,
    blocks: [
      { id: "home-search", type: "searchBar", enabled: true, props: { placeholder: "搜索商品" } },
      {
        id: "home-featured",
        type: "productShelf",
        enabled: true,
        props: { title: "今日推荐", subtitle: "提前预订，新鲜制作", source: "manual", productIds: ["p_001", "p_002"] }
      },
      { id: "home-notice", type: "noticeBar", enabled: true, props: { text: SHOP_CONFIG.defaultNotice } },
      {
        id: "home-hero",
        type: "heroCarousel",
        enabled: true,
        props: {
          items: [
            {
              id: "hero-1",
              imageUrl: "",
              title: "北京单店，12年手作烘焙",
              subtitle: "蛋糕建议提前一天预订，当天订单请先咨询客服",
              eyebrow: "芸熙烘焙",
              badges: ["门店自提", "北京闪送", "新鲜制作"],
              linkType: "product",
              linkTarget: "p_001"
            },
            {
              id: "hero-2",
              imageUrl: "",
              title: "生日、节日与定制蛋糕",
              subtitle: "自提价公开，闪送运费按收货地址下单前确认",
              eyebrow: "预订服务",
              badges: ["当日咨询", "次日履约", "按距计费"],
              linkType: "product",
              linkTarget: "p_002"
            },
            {
              id: "hero-3",
              imageUrl: "",
              title: "每日 09:00-19:30 发货",
              subtitle: "当天订单通常 17:00 截止，制作与配送以客服确认为准",
              eyebrow: "履约时间",
              badges: ["北京范围", "闪送配送", "到店自提"],
              linkType: "none",
              linkTarget: ""
            }
          ],
          autoplay: true,
          intervalMs: 3500
        }
      },
      {
        id: "home-categories",
        type: "categoryGrid",
        enabled: true,
        props: { categoryIds: ["birthday-cake", "dessert-bread", "cookies", "tea-food"] }
      },
      {
        id: "home-links",
        type: "quickLinks",
        enabled: true,
        props: {
          items: [
            { id: "points", title: "积分商城", subtitle: "查看积分", iconText: "积分", linkType: "page", linkTarget: "profile" },
            { id: "recharge", title: "充值中心", subtitle: "查看余额", iconText: "充值", linkType: "page", linkTarget: "profile" }
          ]
        }
      },
      {
        id: "home-member-banner",
        type: "membershipBanner",
        enabled: true,
        props: { title: "注册芸熙烘焙会员", subtitle: "更多会员权益等你解锁", actionText: "立即注册" }
      },
      {
        id: "home-notice-list",
        type: "noticeList",
        enabled: true,
        props: {
          items: [
            { id: "cake-notice", title: "蛋糕订购须知", actionText: "点击查看", linkType: "none", linkTarget: "" },
            { id: "bread-notice", title: "面包订购须知", actionText: "点击查看", linkType: "none", linkTarget: "" },
            { id: "delivery-notice", title: "配送订购须知", actionText: "点击查看", linkType: "none", linkTarget: "" }
          ]
        }
      },
      {
        id: "home-member",
        type: "memberSummary",
        enabled: true,
        props: {
          greeting: "Hello",
          name: "大海",
          levelText: "会员",
          cardSubtitle: "单笔充值 1000 元升级",
          cardValidity: "永久有效",
          points: 160,
          coupons: 0,
          balanceFen: 0,
          benefitCardCount: 0
        }
      }
    ]
  },
  products: {
    pageId: "products",
    version: 1,
    status: "published",
    updatedAt: "2026-06-16T00:00:00+08:00",
    theme: THEME_TOKENS,
    blocks: [
      {
        id: "tips",
        type: "richText",
        enabled: true,
        props: {
          title: "芸熙暖心小提示",
          paragraphs: ["原材料变动、配送小细节、食用色素说明、配送时效等请下单前确认。"]
        }
      },
      { id: "material", type: "productShelf", enabled: true, props: { title: "原材料展示", source: "manual", productIds: ["p_006"] } },
      { id: "classic", type: "productShelf", enabled: true, props: { title: "12年招牌必吃榜", source: "manual", productIds: ["p_003", "p_002"] } },
      { id: "small-cake", type: "productShelf", enabled: true, props: { title: "四寸小蛋糕", source: "manual", productIds: ["p_005", "p_001"] } },
      { id: "birthday", type: "productShelf", enabled: true, props: { title: "生日蜡烛/餐具", source: "manual", productIds: ["p_004"] } }
    ]
  },
  profile: {
    pageId: "profile",
    version: 1,
    status: "published",
    updatedAt: "2026-06-16T00:00:00+08:00",
    theme: THEME_TOKENS,
    blocks: [
      {
        id: "profile-member",
        type: "memberSummary",
        enabled: true,
        props: {
          greeting: "HI",
          name: "大海",
          levelText: "注册会员",
          cardSubtitle: "单笔充值 1000 元升级",
          cardValidity: "永久有效",
          points: 160,
          coupons: 0,
          balanceFen: 0,
          benefitCardCount: 0
        }
      },
      {
        id: "profile-services",
        type: "serviceGrid",
        enabled: true,
        props: {
          title: "我的服务",
          items: [
            { id: "orders", title: "订单中心", iconText: "订单", linkType: "page", linkTarget: "orders" },
            { id: "cart", title: "购物车", iconText: "购物", linkType: "page", linkTarget: "cart" },
            { id: "address", title: "收货地址", iconText: "地址", linkType: "page", linkTarget: "address" },
            { id: "profile", title: "个人信息", iconText: "信息", linkType: "none", linkTarget: "" },
            { id: "settings", title: "账号设置", iconText: "设置", linkType: "none", linkTarget: "" },
            { id: "gift", title: "兑换礼品卡", iconText: "礼品", linkType: "none", linkTarget: "" }
          ]
        }
      }
    ]
  }
};
