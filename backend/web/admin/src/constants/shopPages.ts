export const SHOP_PAGE_OPTIONS = [
  {
    value: "home",
    label: "首页",
    description: "承接首屏、公告、分类和主推商品",
  },
  {
    value: "products",
    label: "商品页",
    description: "管理商品列表页的筛选入口和货架内容",
  },
  {
    value: "profile",
    label: "我的",
    description: "配置会员摘要、服务入口和订购说明",
  },
] as const;

export type ShopPageId = (typeof SHOP_PAGE_OPTIONS)[number]["value"];
