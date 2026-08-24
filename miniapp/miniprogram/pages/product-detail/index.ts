import { addCartItem } from "../../utils/cart";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { formatFen } from "../../utils/money";
import { ROUTES } from "../../constants/routes";
import { getProductDetail } from "../../services/products";
import type { CatalogProduct } from "../../types/catalog";

interface ProductDetailView extends CatalogProduct {
  priceText: string;
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

Page({
  data: {
    product: null as ProductDetailView | null,
    loading: true,
    addingToCart: false,
    buyingNow: false,
    canPurchase: false,
    unavailableText: "商品加载中",
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onLoad(query) {
    void this.loadProduct(query);
  },
  async loadProduct(query: Record<string, string | undefined>) {
    const productId = typeof query.id === "string" ? query.id.trim() : "";
    this.setData({ loading: true, unavailableText: "商品加载中", canPurchase: false });
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
      canPurchase: canPurchaseProduct(product),
      unavailableText: getUnavailableText(product),
      product: {
        ...product,
        priceText: formatFen(product.priceFen)
      }
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
        quantity: 1
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
