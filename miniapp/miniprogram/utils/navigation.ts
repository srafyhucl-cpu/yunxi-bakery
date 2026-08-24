import { ROUTES } from "../constants/routes";

interface LinkNavigationOptions {
  linkType?: string;
  linkTarget?: string;
  fallbackToast?: string;
}

export function goBackOrHome(): void {
  if (getCurrentPages().length > 1) {
    wx.navigateBack();
    return;
  }
  wx.switchTab({ url: ROUTES.home });
}

function openPolicy(policyType: string): void {
  wx.navigateTo({ url: `${ROUTES.policy}?type=${policyType}` });
}

export function navigateByLink(options: LinkNavigationOptions): void {
  const linkType = options.linkType || "none";
  const linkTarget = options.linkTarget || "";

  if (linkType === "page") {
    if (linkTarget === "home") {
      wx.switchTab({ url: ROUTES.home });
      return;
    }
    if (linkTarget === "products") {
      wx.switchTab({ url: ROUTES.products });
      return;
    }
    if (linkTarget === "cart") {
      wx.switchTab({ url: ROUTES.cart });
      return;
    }
    if (linkTarget === "chat") {
      wx.switchTab({ url: ROUTES.chat });
      return;
    }
    if (linkTarget === "profile") {
      wx.switchTab({ url: ROUTES.profile });
      return;
    }
    if (linkTarget === "orders") {
      wx.navigateTo({ url: ROUTES.orders });
      return;
    }
    if (linkTarget === "address") {
      wx.navigateTo({ url: ROUTES.address });
      return;
    }
  }

  if (linkType === "product" && linkTarget) {
    wx.navigateTo({ url: `${ROUTES.productDetail}?id=${linkTarget}` });
    return;
  }

  if (linkType === "category") {
    wx.switchTab({ url: ROUTES.products });
    return;
  }

  if (linkType === "policy" && linkTarget) {
    openPolicy(linkTarget);
    return;
  }

  if (linkType === "contact") {
    wx.switchTab({ url: ROUTES.chat });
    return;
  }

  if (linkType === "phone" && linkTarget) {
    wx.makePhoneCall({ phoneNumber: linkTarget });
    return;
  }

  if (linkType === "wechat" && linkTarget) {
    wx.setClipboardData({ data: linkTarget });
    wx.showToast({ title: "微信号已复制", icon: "none" });
    return;
  }

  wx.showToast({ title: options.fallbackToast || "功能建设中", icon: "none" });
}
