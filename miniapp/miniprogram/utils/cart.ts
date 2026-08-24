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

export function addCartItem(item: CartItem): void {
  const items = getCartItems();
  const existingItem = items.find((cartItem) => cartItem.productId === item.productId);
  if (existingItem) {
    existingItem.quantity += item.quantity;
  } else {
    items.push(item);
  }
  saveCartItems(items);
}
