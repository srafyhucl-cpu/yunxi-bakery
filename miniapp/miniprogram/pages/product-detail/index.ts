import { addCartItem } from "../../utils/cart";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { formatFen } from "../../utils/money";
import {
  getDescriptionBlocks,
  getDisplaySpecs,
  getDisplayTags,
  type DescriptionBlock
} from "../../utils/bakery";
import { ROUTES } from "../../constants/routes";
import { getProductDetail, listProducts } from "../../services/products";
import type { CatalogProduct } from "../../types/catalog";

interface RelatedProductView {
  id: string;
  title: string;
  imageUrl: string;
  priceText: string;
  imageFailed: boolean;
}

// 搭配推荐位数量：横滑一条刚好铺满又不喧宾夺主
const RELATED_PRODUCT_LIMIT = 4;

interface ProductDetailView extends CatalogProduct {
  priceText: string;
  imageFailed: boolean;
  displaySubtitle: string;
  specChips: string[];
  tagChips: string[];
  descriptionBlocks: DescriptionBlock[];
}

function canPurchaseProduct(product: CatalogProduct | null): boolean {
  return Boolean(product?.isActive && product.stock > 0);
}

function getUnavailableText(product: CatalogProduct | null): string {
  if (!product) {
    return "商品加载中";
  }
  if (!product.isActive) {
    return "暂不可售";
  }
  if (product.stock <= 0) {
    return "暂时售罄";
  }
  return "";
}

function isJunkSubtitle(subtitle: string, product: CatalogProduct): boolean {
  // 后端 subtitle 可能混入同步原文：与标题重复或含库存链接等非展示信息时直接隐藏
  const text = subtitle.trim();
  if (!text || text === product.title.trim()) {
    return true;
  }
  return (
    text.includes("商品名称") ||
    text.includes("在售状态") ||
    text.includes("实时库存") ||
    text.includes("下单链接") ||
    text.includes("h5.youzan.com") ||
    text.includes("[UMP")
  );
}

function getDisplaySubtitle(product: CatalogProduct): string {
  const subtitle = (product.subtitle || "").trim();
  return isJunkSubtitle(subtitle, product) ? "" : subtitle;
}

Page({
  data: {
    product: null as ProductDetailView | null,
    loading: true,
    loadFailed: false,
    lastProductId: "",
    purchaseQty: 1,
    relatedProducts: [] as RelatedProductView[],
    addingToCart: false,
    buyingNow: false,
    canPurchase: false,
    unavailableText: "商品加载中",
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onLoad(query) {
    void this.loadProduct(query);
  },
  retryLoad() {
    // 加载失败重试：用进入时记录的商品复位后重新加载
    if (this.data.loading) {
      return;
    }
    this.setData({ loadFailed: false });
    void this.loadProduct({ id: this.data.lastProductId });
  },
  onDetailImageError() {
    // 详情大图运行时加载失败：切换暖米占位，保持固定宽高
    if (this.data.product && !this.data.product.imageFailed) {
      this.setData({ "product.imageFailed": true });
    }
  },
  async loadProduct(query: Record<string, string | undefined>) {
    const productId = typeof query.id === "string" ? query.id.trim() : "";
    this.setData({ loading: true, loadFailed: false, lastProductId: productId, unavailableText: "商品加载中", canPurchase: false });
    if (!productId) {
      this.setData({ loading: false, product: null, unavailableText: "商品不存在", canPurchase: false });
      wx.showToast({ title: "商品不存在", icon: "none" });
      return;
    }
    let product: CatalogProduct | null | undefined;
    try {
      product = await getProductDetail(productId, { forceRefresh: true });
    } catch {
      this.setData({
        loading: false,
        loadFailed: true,
        product: null,
        unavailableText: "商品加载失败",
        canPurchase: false
      });
      wx.showToast({ title: "商品加载失败，请稍后重试", icon: "none" });
      return;
    }
    if (!product) {
      this.setData({ loading: false, product: null, unavailableText: "商品不存在", canPurchase: false });
      wx.showToast({ title: "商品不存在", icon: "none" });
      return;
    }
    this.setData({
      loading: false,
      loadFailed: false,
      canPurchase: canPurchaseProduct(product),
      unavailableText: getUnavailableText(product),
      purchaseQty: 1,
      product: {
        ...product,
        imageFailed: false,
        priceText: formatFen(product.priceFen),
        displaySubtitle: getDisplaySubtitle(product),
        specChips: getDisplaySpecs(product),
        tagChips: getDisplayTags(product),
        descriptionBlocks: getDescriptionBlocks(product.description || "")
      }
    });
    void this.loadRelatedProducts(product.id);
  },
  async loadRelatedProducts(productId: string) {
    // 搭配推荐：精选商品去重去己，失败静默不打断主流程
    try {
      const related = (await listProducts({ featured: true, limit: RELATED_PRODUCT_LIMIT + 1 }))
        .filter((item) => item.id !== productId)
        .slice(0, RELATED_PRODUCT_LIMIT)
        .map((item) => ({
          id: item.id,
          title: item.title,
          imageUrl: item.imageUrl,
          priceText: formatFen(item.priceFen),
          imageFailed: false
        }));
      this.setData({ relatedProducts: related });
    } catch {
      this.setData({ relatedProducts: [] });
    }
  },
  onRelatedImageError(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
    const index = this.data.relatedProducts.findIndex((item) => item.id === productId);
    if (productId && index !== -1 && !this.data.relatedProducts[index].imageFailed) {
      this.setData({ [`relatedProducts[${index}].imageFailed`]: true });
    }
  },
  openRelated(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
    if (!productId) {
      return;
    }
    wx.navigateTo({
      url: `${ROUTES.productDetail}?id=${productId}`
    });
  },
  decreaseQty() {
    if (this.data.purchaseQty > 1) {
      this.setData({ purchaseQty: this.data.purchaseQty - 1 });
    }
  },
  increaseQty() {
    this.setData({ purchaseQty: this.data.purchaseQty + 1 });
  },
  goChat() {
    wx.switchTab({
      url: ROUTES.chat
    });
  },
  goBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack();
      return;
    }
    wx.switchTab({
      url: ROUTES.products
    });
  },
  addToCart() {
    const product = this.data.product;
    if (!product || !this.data.canPurchase || this.data.addingToCart) {
      if (this.data.unavailableText) {
        wx.showToast({ title: this.data.unavailableText, icon: "none" });
      }
      return false;
    }
    this.setData({ addingToCart: true });
    try {
      addCartItem({
        productId: product.id,
        title: product.title,
        imageUrl: product.imageUrl,
        priceFen: product.priceFen,
        quantity: this.data.purchaseQty
      });
      wx.showToast({
        title: "已加入购物车",
        icon: "success"
      });
      return true;
    } finally {
      this.setData({ addingToCart: false });
    }
  },
  buyNow() {
    if (this.data.buyingNow || this.data.addingToCart) {
      return;
    }
    this.setData({ buyingNow: true });
    const added = this.addToCart();
    if (!added) {
      this.setData({ buyingNow: false });
      return;
    }
    wx.navigateTo({
      url: ROUTES.checkout,
      complete: () => {
        this.setData({ buyingNow: false });
      }
    });
  }
});
