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
        id: "home-hero",
        type: "heroCarousel",
        enabled: true,
        props: {
          items: [
            {
              id: "hero-1",
              imageUrl: "",
              title: "匠心与艺术的结晶",
              subtitle: "每日现制 / 手作奶油 / 礼赠场景",
              eyebrow: "YUNXI BAKE",
              badges: ["当日现做", "精选奶油", "生日礼赠"],
              linkType: "product",
              linkTarget: "p_001"
            },
            {
              id: "hero-2",
              imageUrl: "",
              title: "主推上新",
              subtitle: "生日 / 节日 / 定制",
              eyebrow: "PROMOTION",
              badges: ["新品主推", "限时预订", "到店自提"],
              linkType: "product",
              linkTarget: "p_002"
            },
            {
              id: "hero-3",
              imageUrl: "",
              title: "门店宣传位",
              subtitle: "支持多图主推",
              eyebrow: "CAMPAIGN",
              badges: ["多图轮播", "后台装修", "品牌宣传"],
              linkType: "none",
              linkTarget: ""
            }
          ],
          autoplay: true,
          intervalMs: 3500
        }
      },
      { id: "home-notice", type: "noticeBar", enabled: true, props: { text: SHOP_CONFIG.defaultNotice } },
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
        id: "home-featured",
        type: "productShelf",
        enabled: true,
        props: { title: "今日推荐", subtitle: "按需预订，新鲜制作", source: "manual", productIds: ["p_001", "p_002"] }
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
