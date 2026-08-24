export type ShopPageStatus = "draft" | "published";

export type ShopPageBlockType =
  | "searchBar"
  | "heroCarousel"
  | "noticeBar"
  | "categoryGrid"
  | "quickLinks"
  | "membershipBanner"
  | "noticeList"
  | "productShelf"
  | "memberSummary"
  | "serviceGrid"
  | "richText";

export interface ShopPageTheme {
  primaryColor: string;
  accentColor: string;
  backgroundColor: string;
}

export interface ShopPageBlock {
  id: string;
  type: ShopPageBlockType;
  enabled: boolean;
  props: Record<string, unknown>;
}

export interface ShopPageConfig {
  pageId: string;
  version: number;
  status: ShopPageStatus;
  updatedAt: string;
  theme: ShopPageTheme;
  blocks: ShopPageBlock[];
}

export interface ShopPageAdminPayload {
  pageId: string;
  draft: ShopPageConfig;
  published: ShopPageConfig;
}

export interface EditableBlockSummary {
  id: string;
  label: string;
  type: ShopPageBlockType;
}

