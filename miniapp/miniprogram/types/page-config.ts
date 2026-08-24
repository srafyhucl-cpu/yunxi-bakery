export type PageId = "home" | "products" | "profile";

export type PageBlockType =
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

export interface PageTheme {
  primaryColor: string;
  accentColor: string;
  backgroundColor: string;
}

export interface PageBlock<TProps = Record<string, unknown>> {
  id: string;
  type: PageBlockType;
  enabled: boolean;
  props: TProps;
}

export interface ShopPageConfig {
  pageId: PageId;
  version: number;
  status: "draft" | "published";
  updatedAt: string;
  theme: PageTheme;
  blocks: PageBlock[];
}

export interface LinkTarget {
  linkType: "none" | "page" | "product" | "category" | "contact";
  linkTarget: string;
}

export interface SearchBarProps {
  placeholder: string;
}

export interface HeroCarouselProps {
  items: Array<LinkTarget & {
    id?: string;
    imageUrl: string;
    title: string;
    subtitle?: string;
    eyebrow?: string;
    badges?: string[];
  }>;
  autoplay?: boolean;
  intervalMs?: number;
}

export interface NoticeBarProps {
  text: string;
}

export interface CategoryGridProps {
  categoryIds: string[];
}

export interface QuickLinksProps {
  items: Array<LinkTarget & { id: string; title: string; subtitle: string; iconText: string }>;
}

export interface MembershipBannerProps {
  title: string;
  subtitle: string;
  actionText: string;
}

export interface NoticeListProps {
  items: Array<LinkTarget & { id: string; title: string; actionText: string }>;
}

export interface ProductShelfProps {
  title: string;
  subtitle?: string;
  source: "manual" | "category" | "featured";
  productIds?: string[];
  categoryId?: string;
}

export interface MemberSummaryProps {
  greeting: string;
  name: string;
  levelText: string;
  cardSubtitle: string;
  cardValidity: string;
  points: number;
  coupons: number;
  balanceFen: number;
  benefitCardCount: number;
}

export interface ServiceGridProps {
  title: string;
  items: Array<LinkTarget & { id: string; title: string; iconText: string }>;
}

export interface RichTextProps {
  title: string;
  paragraphs: string[];
}
