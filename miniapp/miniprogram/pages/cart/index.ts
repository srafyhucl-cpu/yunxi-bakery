import { addCartItem, getCartItems, saveCartItems } from "../../utils/cart";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { formatFen } from "../../utils/money";
import { ROUTES } from "../../constants/routes";
import { getBakeryPattern, getProductImageClass } from "../../utils/bakery";
import { syncCustomTabBar } from "../../utils/tab-bar";
import { listProducts } from "../../services/products";
import type { CatalogProduct } from "../../types/catalog";

interface RecommendedProductView {
  id: string;
  title: string;
  priceText: string;
  soldText: string;
  imageClass: string;
  imageUrl: string;
  imageFailed: boolean;
  isUnavailable: boolean;
  actionText: string;
  priceFen: number;
  stock: number;
  isActive: boolean;
}

interface CartItemView extends CartItem {
  priceText: string;
  imageClass: string;
  imageFailed: boolean;
  stock?: number;
  stockText: string;
}

const RECOMMENDED_PRODUCT_LIMIT = 4;

function toRecommendedProductView(product: CatalogProduct): RecommendedProductView {
  const isUnavailable = !product.isActive || product.stock <= 0;
  return {
    id: product.id,
    title: product.title,
    imageUrl: product.imageUrl,
    priceText: formatFen(product.priceFen),
    soldText: isUnavailable ? "可咨询客服" : "建议提前1天预订",
    imageClass: getProductImageClass(product),
    imageFailed: false,
    isUnavailable,
    actionText: isUnavailable ? "查看" : "加入",
    priceFen: product.priceFen,
    stock: product.stock,
    isActive: product.isActive
  };
}

function getCartStockText(item: CartItem): string {
  if (typeof item.stock !== "number") {
    return "建议提前1天预订";
  }
  if (item.stock <= 0) {
    return "暂时售罄";
  }
  if (item.quantity >= item.stock) {
    return "已达库存上限";
  }
  if (item.stock <= 5) {
    return "仅余 " + item.stock + " 件";
  }
  return "建议提前1天预订";
}

Page({
  data: {
    items: [] as CartItemView[],
    hasItems: false,
    totalText: "¥0.00",
    recommendedProducts: [] as RecommendedProductView[],
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onShow() {
    syncCustomTabBar(ROUTES.cart);
    this.refreshCartData();
    void this.loadRecommendedProducts();
  },
  async loadRecommendedProducts() {
    try {
      let products = await listProducts({ featured: true, limit: RECOMMENDED_PRODUCT_LIMIT });
      if (!products.length) {
        products = await listProducts({ limit: RECOMMENDED_PRODUCT_LIMIT });
      }
      this.setData({ recommendedProducts: products.slice(0, RECOMMENDED_PRODUCT_LIMIT).map(toRecommendedProductView) });
    } catch {
      this.setData({ recommendedProducts: [] });
    }
  },
  onCartImageError(event: WechatMiniprogram.TouchEvent) {
    // 购物车行图加载失败：切换占位，保持固定宽高
    const productId = event.currentTarget.dataset.id as string;
    const index = this.data.items.findIndex((item) => item.productId === productId);
    if (productId && index !== -1 && !this.data.items[index].imageFailed) {
      this.setData({ [`items[${index}].imageFailed`]: true });
    }
  },
  onRecommendImageError(event: WechatMiniprogram.TouchEvent) {
    // 推荐位图片加载失败：切换占位，保持固定宽高
    const productId = event.currentTarget.dataset.id as string;
    const index = this.data.recommendedProducts.findIndex((item) => item.id === productId);
    if (productId && index !== -1 && !this.data.recommendedProducts[index].imageFailed) {
      this.setData({ [`recommendedProducts[${index}].imageFailed`]: true });
    }
  },
  refreshCartData() {
    const items = getCartItems().map((item) => ({
      ...item,
      priceText: formatFen(item.priceFen),
      imageClass: item.imageUrl ? "" : getBakeryPattern(item.productId),
      imageFailed: false,
      stockText: getCartStockText(item)
    }));
    const totalFen = items.reduce((sum, item) => sum + item.priceFen * item.quantity, 0);
    this.setData({
      items,
      hasItems: items.length > 0,
      totalText: formatFen(totalFen)
    });
  },
  decreaseQty(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
    const items = getCartItems();
    const existingItem = items.find((item) => item.productId === productId);
    if (!existingItem) return;

    if (existingItem.quantity > 1) {
      existingItem.quantity -= 1;
      saveCartItems(items);
      this.refreshCartData();
    } else {
      wx.showModal({
        title: "确认移除",
        content: `确定从购物车中移除“${existingItem.title}”吗？`,
        confirmColor: "#3D332D",
        success: (res) => {
          if (res.confirm) {
            const updatedItems = items.filter((item) => item.productId !== productId);
            saveCartItems(updatedItems);
            this.refreshCartData();
          }
        }
      });
    }
  },
  increaseQty(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
    const items = getCartItems();
    const existingItem = items.find((item) => item.productId === productId);
    if (!existingItem) return;
    const visibleItem = this.data.items.find((item) => item.productId === productId);
    if (visibleItem?.stock && existingItem.quantity >= visibleItem.stock) {
      wx.showToast({ title: "库存仅余 " + visibleItem.stock + " 件", icon: "none" });
      return;
    }

    existingItem.quantity += 1;
    saveCartItems(items);
    this.refreshCartData();
  },
  addRecommendedProduct(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
    const product = this.data.recommendedProducts.find((item) => item.id === productId);
    if (!product) {
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
      stock: product.stock,
    });
    this.refreshCartData();
    wx.showToast({ title: "已加入预订单", icon: "success" });
  },
  goShopping() {
    wx.switchTab({
      url: ROUTES.products
    });
  },
  openProduct(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
    wx.navigateTo({
      url: `${ROUTES.productDetail}?id=${productId}`
    });
  },
  checkout() {
    if (!this.data.hasItems) {
      wx.switchTab({ url: ROUTES.products });
      return;
    }
    wx.navigateTo({
      url: ROUTES.checkout
    });
  }
});
