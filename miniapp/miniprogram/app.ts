import { STORAGE_KEYS } from "./constants/storage";
import { ensureMiniappSession, getMiniappSession } from "./services/auth";

App<IAppOption>({
  globalData: {
    addressBookItems: [],
    cartItems: []
  },
  async onLaunch() {
    try {
      this.globalData.miniappSession = await ensureMiniappSession();
    } catch {
      this.globalData.miniappSession = getMiniappSession();
    }
    const addressBookItems = wx.getStorageSync(STORAGE_KEYS.addressBookItems);
    if (Array.isArray(addressBookItems)) {
      this.globalData.addressBookItems = addressBookItems;
    }
    const cartItems = wx.getStorageSync(STORAGE_KEYS.cartItems);
    if (Array.isArray(cartItems)) {
      this.globalData.cartItems = cartItems;
    }
  }
});
