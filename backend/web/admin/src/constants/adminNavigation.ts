import type { Component } from "vue";
import {
  ChatDotRound,
  DataAnalysis,
  Document,
  Goods,
  Location,
  MagicStick,
  Odometer,
  Service,
  Setting,
  Ticket,
  Tickets,
  UserFilled,
} from "@element-plus/icons-vue";

export interface AdminNavItem {
  label: string;
  shortLabel: string;
  to: string;
  key: string;
  icon: Component;
  mobilePrimary: boolean;
}

export const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  { label: "概览", shortLabel: "概览", to: "/overview", key: "overview", icon: Odometer, mobilePrimary: true },
  { label: "AI 对话", shortLabel: "AI", to: "/ai-dialog", key: "ai-dialog", icon: ChatDotRound, mobilePrimary: false },
  { label: "商品管理", shortLabel: "商品", to: "/products", key: "products", icon: Goods, mobilePrimary: true },
  { label: "优惠券", shortLabel: "券", to: "/coupons", key: "coupons", icon: Ticket, mobilePrimary: false },
  { label: "店铺装修", shortLabel: "装修", to: "/decoration", key: "decoration", icon: MagicStick, mobilePrimary: false },
  { label: "订单管理", shortLabel: "订单", to: "/orders", key: "orders", icon: Tickets, mobilePrimary: true },
  { label: "顾客地址", shortLabel: "地址", to: "/addresses", key: "addresses", icon: Location, mobilePrimary: false },
  { label: "客户群运营", shortLabel: "群", to: "/customer-groups", key: "customer-groups", icon: UserFilled, mobilePrimary: false },
  { label: "知识配置", shortLabel: "知识", to: "/knowledge", key: "knowledge", icon: Document, mobilePrimary: false },
  {
    label: "知识报表",
    shortLabel: "报表",
    to: "/knowledge-retrieval-report",
    key: "knowledge-report",
    icon: DataAnalysis,
    mobilePrimary: false,
  },
  {
    label: "数据观察台",
    shortLabel: "观察",
    to: "/observability/sessions",
    key: "observability",
    icon: DataAnalysis,
    mobilePrimary: false,
  },
  { label: "转人工", shortLabel: "客服", to: "/transfers", key: "transfers", icon: Service, mobilePrimary: true },
  { label: "系统配置", shortLabel: "设置", to: "/settings/shop", key: "settings", icon: Setting, mobilePrimary: true },
];

export const MOBILE_ADMIN_NAV_ITEMS = ADMIN_NAV_ITEMS.filter((item) => item.mobilePrimary);
