import { ROUTES } from "./routes";

export const TAB_BAR_ITEMS = [
  { key: "home", pagePath: ROUTES.home, text: "首页", iconText: "H" },
  { key: "products", pagePath: ROUTES.products, text: "商品", iconText: "P" },
  { key: "cart", pagePath: ROUTES.cart, text: "购物车", iconText: "B" },
  { key: "chat", pagePath: ROUTES.chat, text: "客服", iconText: "S" },
  { key: "profile", pagePath: ROUTES.profile, text: "我的", iconText: "M" }
] as const;
