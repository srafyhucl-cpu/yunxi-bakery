import { getCartItems, saveCartItems } from "../../utils/cart";
import { getProductsByIds } from "../../utils/catalog";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { formatFen } from "../../utils/money";
import { ROUTES } from "../../constants/routes";
import { getBakeryPattern, getProductImageClass } from "../../utils/bakery";
import { syncCustomTabBar } from "../../utils/tab-bar";

Page({
  data: {
    items: [] as Array<CartItem & { priceText: string; imageClass: string }>,
    hasItems: false,
    totalText: "¥0.00",
    recommendedProducts: [] as Array<{ id: string; title: string; priceText: string; soldText: string; imageClass: string }>,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onShow() {
    syncCustomTabBar(ROUTES.cart);
    this.refreshCartData();
    this.setData({
      recommendedProducts: getProductsByIds(["p_003", "p_004"]).map((product) => ({
        id: product.id,
        title: product.title,
        imageUrl: product.imageUrl,
        priceText: formatFen(product.priceFen),
        soldText: product.soldText,
        imageClass: getProductImageClass(product)
      }))
    });
  },
  refreshCartData() {
    const items = getCartItems().map((item) => ({
      ...item,
      priceText: formatFen(item.priceFen),
      imageClass: item.imageUrl ? "" : getBakeryPattern(item.productId)
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
        confirmColor: "#4a7a41",
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

    existingItem.quantity += 1;
    saveCartItems(items);
    this.refreshCartData();
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
