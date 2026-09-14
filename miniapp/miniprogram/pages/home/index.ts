 import { ROUTES } from "../../constants/routes";
import {
  getProductActionLabel,
  getProductAddToastLabel,
  getProductAvailabilityLabel,
  getProductCardTip,
  getProductImageClass,
  getProductPriceText,
  isProductPurchasable
} from "../../utils/bakery";
import { addCartItem, getCartItems } from "../../utils/cart";
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
  imageFailed: boolean;
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
        title: "12年匠心手作 · 北京单店",
        subtitle: "每日现制 / 动物奶油 / 提前1天预订",
        eyebrow: "芸熙烘焙",
        badges: ["北京单店", "提前预订", "闪送专送"],
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
  imageFailed: boolean;
  imageClass: string;
  badgeText: string;
  deliveryTip?: string;
  isUnavailable: boolean;
  isDisplayOnly: boolean;
  actionText: string;
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

// 装修配置的历史模型仍可能携带 iconText；顾客端统一按语义键渲染，禁止把文字塞进图标底座。
function resolveQuickLinkIconKey(link: QuickLinksProps["items"][number]): string {
  const configuredKey = String(link.iconKey || "").trim();
  if (/^(points|recharge|link)$/.test(configuredKey)) {
    return configuredKey;
  }
  const identity = [link.id, link.linkTarget, link.title].join(" ").toLowerCase();
  if (identity.includes("points") || identity.includes("积分")) {
    return "points";
  }
  if (identity.includes("recharge") || identity.includes("充值")) {
    return "recharge";
  }
  return "link";
}

function buildQuickLinks(block: PageBlock): HomeBlockView {
  const props = normalizeQuickLinksProps(block.props);
  return {
    ...block,
    quickLinkItems: props.items.map((link) => ({
      ...link,
      iconKey: resolveQuickLinkIconKey(link),
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
      imageFailed: false,
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
    ["productShelf", 20],
    ["noticeBar", 30],
    ["heroCarousel", 80],
    ["quickLinks", 90],
    ["membershipBanner", 100],
    ["noticeList", 110]
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
      // source=auto 时按精选+limit 拉取；manual 时按显式 ID 列表拉取
      let sourceProducts = props.source === "auto"
        ? await listProducts({ featured: true, limit: (props.limit as number) || 6 })
        : await listProducts({ ids: props.productIds ?? [] });
      if (props.source === "auto" && sourceProducts.length === 0) {
        sourceProducts = await listProducts({ limit: (props.limit as number) || 6 });
      }
      const products = sourceProducts.map((product) => ({
        ...product,
        priceText: getProductPriceText(product, `自提价 ${formatFen(product.priceFen)}`),
        imageClass: getProductImageClass(product),
        imageFailed: false,
        badgeText: getProductAvailabilityLabel(product),
        deliveryTip: getProductCardTip(product),
        isUnavailable: product.isPurchasable === false || !product.isActive || product.stock <= 0,
        isDisplayOnly: !isProductPurchasable(product),
        actionText: getProductActionLabel(product)
      }));
      return { ...block, products };
    }
    return block;
  }));
}

Page({
  data: {
    blocks: [] as HomeBlockView[],
    cartItemCount: 0,
    cartTotalText: "¥0.00",
    cartSummaryText: "还没有选择商品",
    cartBarVisible: false,
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
    this.refreshCartSummary();
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
  onHeroImageError(event: WechatMiniprogram.TouchEvent) {
    // 轮播图运行时加载失败：按轮播项定位并切换降级背景，避免首页首屏出现破图
    const slideId = event.currentTarget.dataset.slideId as string;
    if (!slideId) {
      return;
    }
    const updates: Record<string, boolean> = {};
    this.data.blocks.forEach((block, blockIndex) => {
      (block.heroItems || []).forEach((slide, slideIndex) => {
        if (slide.id === slideId && !slide.imageFailed) {
          updates[`blocks[${blockIndex}].heroItems[${slideIndex}].imageFailed`] = true;
        }
      });
    });
    if (Object.keys(updates).length > 0) {
      this.setData(updates);
    }
  },
  onHomeProductImageError(event: WechatMiniprogram.TouchEvent) {
    // 商品图运行时加载失败：按商品定位全部货架命中项并切换占位，保持卡片尺寸稳定
    const productId = event.currentTarget.dataset.id as string;
    if (!productId) {
      return;
    }
    const updates: Record<string, boolean> = {};
    this.data.blocks.forEach((block, blockIndex) => {
      (block.products || []).forEach((product, productIndex) => {
        if (product.id === productId && !product.imageFailed) {
          updates[`blocks[${blockIndex}].products[${productIndex}].imageFailed`] = true;
        }
      });
    });
    if (Object.keys(updates).length > 0) {
      this.setData(updates);
    }
  },
  refreshCartSummary() {
    const cartItems = getCartItems();
    const cartItemCount = cartItems.reduce((sum, item) => sum + item.quantity, 0);
    const cartTotalFen = cartItems.reduce((sum, item) => sum + item.priceFen * item.quantity, 0);
    this.setData({
      cartItemCount,
      cartTotalText: formatFen(cartTotalFen),
      cartSummaryText: cartItemCount > 0 ? cartItemCount + " 件已选 · 闪送费下单前确认" : "还没有选择商品",
      cartBarVisible: cartItemCount > 0
    });
  },
  quickAddHomeProduct(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
    const product = this.data.blocks
      .flatMap((block) => block.products || [])
      .find((item) => item.id === productId);
    if (!productId || !product) {
      return;
    }
    if (product.isUnavailable) {
      wx.navigateTo({ url: `${ROUTES.productDetail}?id=${productId}` });
      return;
    }
    const currentQuantity = getCartItems()
      .filter((item) => item.productId === productId)
      .reduce((sum, item) => sum + item.quantity, 0);
    if (currentQuantity >= product.stock) {
      wx.showToast({ title: "库存仅余 " + product.stock + " 件", icon: "none" });
      return;
    }
    addCartItem({
      productId: product.id,
      title: product.title,
      imageUrl: product.imageUrl,
      priceFen: product.priceFen,
      quantity: 1,
      stock: product.stock
    });
    this.refreshCartSummary();
    wx.showToast({ title: getProductAddToastLabel(product), icon: "success" });
  },
  goToCart() {
    wx.switchTab({ url: ROUTES.cart });
  },
  goCheckout() {
    if (!getCartItems().length) {
      wx.showToast({ title: "请先选择商品", icon: "none" });
      return;
    }
    wx.navigateTo({ url: ROUTES.checkout });
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
