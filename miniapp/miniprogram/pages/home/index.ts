 import { ROUTES } from "../../constants/routes";
import { getProductImageClass } from "../../utils/bakery";
import { API_BASE_URL } from "../../services/config";
import { getMiniappSession } from "../../services/auth";
import { getPublishedPageConfig } from "../../services/page-config";
import { listProducts } from "../../services/products";
import { getShopSettings } from "../../services/shop-settings";
import { formatFen } from "../../utils/money";
import { navigateByLink } from "../../utils/navigation";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { syncCustomTabBar } from "../../utils/tab-bar";
import { getEnabledBlocks } from "../../utils/page-config";
import { buildMiniappSessionView, isMiniappLoggedIn } from "../../utils/session";
import type { CatalogProduct } from "../../types/catalog";
import type {
  HeroCarouselProps,
  LinkTarget,
  NoticeListProps,
  PageBlock,
  QuickLinksProps,
  ShopPageConfig
} from "../../types/page-config";

type HeroItemView = LinkTarget & {
  id: string;
  imageUrl: string;
  title: string;
  subtitle: string;
  eyebrow: string;
  badges: string[];
};

const HOME_HERO_BLOCK: PageBlock = {
  id: "home-local-hero",
  type: "heroCarousel",
  enabled: true,
  props: {
    items: [
      {
        id: "local-hero-1",
        imageUrl: "",
        title: "匠心与艺术的结晶",
        subtitle: "每日现制 / 手作奶油 / 礼赠场景",
        eyebrow: "YUNXI BAKE",
        badges: ["当日现做", "节日礼赠", "门店主推"],
        linkType: "none",
        linkTarget: ""
      }
    ],
    autoplay: true,
    intervalMs: 3500
  }
};

interface ProductCardView extends CatalogProduct {
  priceText: string;
  imageClass: string;
  badgeText: string;
}

interface HomeBlockView extends PageBlock {
  heroItems?: HeroItemView[];
  heroAutoplay?: boolean;
  heroIntervalMs?: number;
  products?: ProductCardView[];
  balanceText?: string;
  quickLinkItems?: Array<QuickLinksProps["items"][number] & { titleText: string }>;
  noticeItems?: NoticeListProps["items"];
}

function normalizeQuickLinksProps(props: PageBlock["props"]): QuickLinksProps {
  const maybeProps = props as Partial<QuickLinksProps>;
  return {
    items: Array.isArray(maybeProps.items) ? maybeProps.items : [],
  };
}

function buildQuickLinks(block: PageBlock): HomeBlockView {
  const props = normalizeQuickLinksProps(block.props);
  return {
    ...block,
    quickLinkItems: props.items.map((link) => ({
      ...link,
      titleText: `${link.title} >`,
    })),
  };
}

function normalizeNoticeListProps(props: PageBlock["props"]): NoticeListProps {
  const maybeProps = props as Partial<NoticeListProps>;
  return {
    items: Array.isArray(maybeProps.items) ? maybeProps.items : []
  };
}

function buildNoticeList(block: PageBlock): HomeBlockView {
  return {
    ...block,
    noticeItems: normalizeNoticeListProps(block.props).items.map((item) => ({
      ...item,
      linkType: item.linkType === "none" ? "contact" : item.linkType,
      actionText: item.linkType === "none" ? "咨询客服" : item.actionText
    }))
  };
}

function normalizeImageUrl(imageUrl: string): string {
  if (!imageUrl || imageUrl.startsWith("http://") || imageUrl.startsWith("https://")) {
    return imageUrl;
  }
  return `${API_BASE_URL}${imageUrl.startsWith("/") ? "" : "/"}${imageUrl}`;
}

function normalizeHeroProps(props: PageBlock["props"]): HeroCarouselProps {
  const maybeProps = props as Partial<HeroCarouselProps>;
  return {
    items: Array.isArray(maybeProps.items) ? maybeProps.items : [],
    autoplay: maybeProps.autoplay !== false,
    intervalMs: typeof maybeProps.intervalMs === "number" ? maybeProps.intervalMs : 3500
  };
}

function buildHeroCarousel(block: PageBlock): HomeBlockView {
  const props = normalizeHeroProps(block.props);
  const fallbackProps = normalizeHeroProps(HOME_HERO_BLOCK.props);
  const heroItems = props.items.length > 0 ? props.items : fallbackProps.items;
  return {
    ...block,
    heroItems: heroItems.map((item, index) => ({
      id: item.id || `${block.id}-${index}`,
      imageUrl: normalizeImageUrl(item.imageUrl || ""),
      title: item.title || "芸熙烘焙",
      subtitle: item.subtitle || "每日现制 / 手作奶油 / 礼赠场景",
      eyebrow: item.eyebrow || "YUNXI BAKE",
      badges: Array.isArray(item.badges) ? item.badges.map((badge) => String(badge)).filter(Boolean).slice(0, 3) : [],
      linkType: item.linkType || "none",
      linkTarget: item.linkTarget || ""
    })),
    heroAutoplay: props.autoplay !== false,
    heroIntervalMs: props.intervalMs || 3500
  };
}

function ensureHomeVisualBlocks(blocks: PageBlock[]): PageBlock[] {
  const visibleBlocks = blocks.filter(
    (block) => block.type !== "searchBar" && block.type !== "categoryGrid" && block.type !== "memberSummary"
  );
  const hasHero = visibleBlocks.some((block) => block.type === "heroCarousel");
  const visualBlocks = [
    ...(!hasHero ? [HOME_HERO_BLOCK] : [])
  ];
  const withFallbacks = [...visibleBlocks, ...visualBlocks];
  const order = new Map([
    ["heroCarousel", 20],
    ["noticeBar", 30],
    ["quickLinks", 50],
    ["membershipBanner", 60],
    ["noticeList", 70],
    ["productShelf", 80]
  ]);

  return withFallbacks
    .map((block, index) => ({ block, index }))
    .sort((left, right) => {
      const leftOrder = order.get(left.block.type) ?? 999;
      const rightOrder = order.get(right.block.type) ?? 999;
      return leftOrder === rightOrder ? left.index - right.index : leftOrder - rightOrder;
    })
    .map(({ block }) => block);
}

async function buildHomeBlocks(config: ShopPageConfig): Promise<HomeBlockView[]> {
  const blocks = ensureHomeVisualBlocks(getEnabledBlocks(config));
  const shopSettings = await getShopSettings();
  return Promise.all(blocks.map(async (block) => {
    if (block.type === "noticeBar") {
      return {
        ...block,
        props: {
          ...block.props,
          text: `${shopSettings.shopName} | ${shopSettings.businessHours} | 客服微信 ${shopSettings.customerWechat}`,
        },
      };
    }
    if (block.type === "heroCarousel") {
      return buildHeroCarousel(block);
    }
    if (block.type === "quickLinks") {
      return buildQuickLinks(block);
    }
    if (block.type === "noticeList") {
      return buildNoticeList(block);
    }
    if (block.type === "productShelf") {
      const props = block.props as {
        source?: string;
        productIds?: string[];
        limit?: number;
      };
      const featuredClasses = ["cake-choco", "cake-yellow"];
      // source=auto 时按精选+limit 拉取；manual 时按显式 ID 列表拉取
      const products = (
        await (props.source === "auto"
          ? listProducts({ featured: true, limit: (props.limit as number) || 6 })
          : listProducts({ ids: props.productIds ?? [] }))
      ).map((product, index) => ({
        ...product,
        priceText: formatFen(product.priceFen),
        imageClass: featuredClasses[index] || getProductImageClass(product),
        badgeText: index === 0 ? "编辑推荐" : "新品热卖"
      }));
      return { ...block, products };
    }
    return block;
  }));
}

Page({
  data: {
    blocks: [] as HomeBlockView[],
    sessionView: buildMiniappSessionView(getMiniappSession()),
    canUseAccountFlows: false,
    loginNoticeText: "登录后会员、订单和客服记录会归属到当前微信身份",
    loginNoticeActionText: "去登录",
    loaded: false,
    loading: false,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onLoad() {
    void this.loadHome();
  },
  onShow() {
    syncCustomTabBar(ROUTES.home);
  },
  async loadHome() {
    if (this.data.loaded || this.data.loading) {
      return;
    }
    const session = getMiniappSession();
    this.setData({ loading: true });
    try {
      const config = await getPublishedPageConfig("home");
      this.setData({
        blocks: await buildHomeBlocks(config),
        sessionView: buildMiniappSessionView(session),
        canUseAccountFlows: isMiniappLoggedIn(session),
        loginNoticeText: isMiniappLoggedIn(session)
          ? "已使用真实微信身份，可继续查看会员、订单和客服记录"
          : "登录后会员、订单和客服记录会归属到当前微信身份",
        loginNoticeActionText: isMiniappLoggedIn(session) ? "会员中心" : "去登录",
        loaded: true
      });
    } finally {
      this.setData({ loading: false });
    }
  },
  navigateToProducts() {
    wx.switchTab({
      url: ROUTES.products
    });
  },
  navigateToChat() {
    wx.switchTab({
      url: ROUTES.chat
    });
  },
  navigateToProfile() {
    wx.switchTab({
      url: ROUTES.profile
    });
  },
  openProduct(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
    wx.navigateTo({
      url: `${ROUTES.productDetail}?id=${productId}`
    });
  },
  handleBlockAction(event: WechatMiniprogram.TouchEvent) {
    const linkType = event.currentTarget.dataset.linkType as string;
    const linkTarget = event.currentTarget.dataset.linkTarget as string;
    navigateByLink({ linkType, linkTarget });
  },
  handleHeroTap(event: WechatMiniprogram.TouchEvent) {
    const linkType = event.currentTarget.dataset.linkType as string;
    const linkTarget = event.currentTarget.dataset.linkTarget as string;
    navigateByLink({ linkType, linkTarget });
  }
});
