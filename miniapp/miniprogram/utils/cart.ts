import { STORAGE_KEYS } from "../constants/storage";

export function getCartItems(): CartItem[] {
  const value = wx.getStorageSync(STORAGE_KEYS.cartItems);
  return Array.isArray(value) ? value : [];
}

export function saveCartItems(items: CartItem[]): void {
  wx.setStorageSync(STORAGE_KEYS.cartItems, items);
  const app = getApp<IAppOption>();
  app.globalData.cartItems = items;
}

export function clearCartItems(): void {
  saveCartItems([]);
}

/** 购物车行标识：商品 + 规格 + 选项 + 定制文字，任一不同都必须单独成行。 */
export function buildCartLineKey(
  item: Pick<CartItem, "productId" | "skuId" | "optionChoiceIds" | "greeting" | "accessories">
): string {
  return [
    item.productId,
    item.skuId || "",
    (item.optionChoiceIds || []).slice().sort().join(","),
    (item.greeting || "").trim(),
    (item.accessories || "").trim()
  ].join("|");
}

export function addCartItem(item: CartItem): void {
  const items = getCartItems();
  const lineKey = item.lineKey || buildCartLineKey(item);
  const existingItem = items.find(
    (cartItem) => (cartItem.lineKey || buildCartLineKey(cartItem)) === lineKey
  );
  if (existingItem) {
    existingItem.quantity += item.quantity;
    if (typeof item.stock === "number") {
      existingItem.stock = item.stock;
    }
  } else {
    items.push({ ...item, lineKey });
  }
  saveCartItems(items);
}
