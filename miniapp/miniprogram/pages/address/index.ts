import {
  findAddressById,
  persistAddressBookDraft,
  persistDefaultAddress,
  removeAddressBookItemRemote,
  setSelectedAddress,
  syncAddressBookFromBackend,
  validateAddressBookDraft,
} from "../../utils/address-book";
import { getMiniappSession } from "../../services/auth";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { goBackOrHome } from "../../utils/navigation";
import { buildMiniappSessionView, isMiniappLoggedIn } from "../../utils/session";
import type { AddressBookItem } from "../../services/address";

type AddressPageMode = "manage" | "select";

function normalizeText(value: string): string {
  return value.trim();
}

function buildEmptyDraft() {
  return {
    id: "",
    receiverName: "",
    receiverPhone: "",
    address: "",
    isDefault: false
  };
}

Page({
  data: {
    mode: "manage" as AddressPageMode,
    addresses: [] as AddressBookItem[],
    editing: false,
    savingAddress: false,
    defaultingAddressId: "",
    deletingAddressId: "",
    draft: buildEmptyDraft(),
    errorMessage: "",
    sessionView: buildMiniappSessionView(getMiniappSession()),
    loginStateText: "地址管理需要真实登录后使用",
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onLoad(query: Record<string, string | undefined>) {
    this.setData({
      mode: query.mode === "select" ? "select" : "manage"
    });
  },
  onShow() {
    this.reloadAddresses();
  },
  goBack() {
    if (this.data.savingAddress || this.data.defaultingAddressId || this.data.deletingAddressId) {
      return;
    }
    goBackOrHome();
  },
  async reloadAddresses() {
    if (!isMiniappLoggedIn(getMiniappSession())) {
      this.setData({
        addresses: [] as AddressBookItem[],
        errorMessage: "",
        sessionView: buildMiniappSessionView(getMiniappSession()),
        loginStateText: "请先登录后管理地址"
      });
      return;
    }
    this.setData({
      sessionView: buildMiniappSessionView(getMiniappSession()),
      loginStateText: "已使用真实登录态加载地址"
    });
    const addresses = await syncAddressBookFromBackend();
    this.setData({ addresses });
  },
  startCreate() {
    if (this.data.savingAddress) {
      return;
    }
    this.setData({
      editing: true,
      draft: buildEmptyDraft(),
      errorMessage: ""
    });
  },
  startEdit(event: WechatMiniprogram.TouchEvent) {
    if (this.data.savingAddress || this.data.defaultingAddressId || this.data.deletingAddressId) {
      return;
    }
    const addressId = String(event.currentTarget.dataset.id || "");
    const item = findAddressById(addressId);
    if (!item) {
      wx.showToast({ title: "地址不存在", icon: "none" });
      this.reloadAddresses();
      return;
    }
    this.setData({
      editing: true,
      draft: {
        id: item.id,
        receiverName: item.receiverName,
        receiverPhone: item.receiverPhone,
        address: item.address,
        isDefault: item.isDefault
      },
      errorMessage: ""
    });
  },
  cancelEdit() {
    if (this.data.savingAddress) {
      return;
    }
    this.setData({
      editing: false,
      draft: buildEmptyDraft(),
      errorMessage: ""
    });
  },
  updateDraftField(event: WechatMiniprogram.Input) {
    const field = event.currentTarget.dataset.field as string;
    this.setData({
      [`draft.${field}`]: event.detail.value
    });
  },
  toggleDraftDefault(event: WechatMiniprogram.SwitchChange) {
    this.setData({
      "draft.isDefault": event.detail.value
    });
  },
  saveDraft() {
    if (this.data.savingAddress) {
      return;
    }
    const draft = {
      ...this.data.draft,
      receiverName: normalizeText(this.data.draft.receiverName),
      receiverPhone: normalizeText(this.data.draft.receiverPhone),
      address: normalizeText(this.data.draft.address)
    };
    const errorMessage = validateAddressBookDraft(draft);
    if (errorMessage) {
      this.setData({ errorMessage });
      wx.showToast({ title: errorMessage, icon: "none" });
      return;
    }
    void this.saveAddressDraft(draft);
  },
  async saveAddressDraft(draft: {
    id: string;
    receiverName: string;
    receiverPhone: string;
    address: string;
    isDefault: boolean;
  }) {
    this.setData({ savingAddress: true });
    try {
      await persistAddressBookDraft({
        id: draft.id || undefined,
        receiverName: draft.receiverName,
        receiverPhone: draft.receiverPhone,
        address: draft.address,
        isDefault: draft.isDefault
      });
      this.setData({
        editing: false,
        draft: buildEmptyDraft(),
        errorMessage: ""
      });
      await this.reloadAddresses();
      wx.showToast({ title: "地址已保存", icon: "success" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存失败";
      this.setData({ errorMessage: message });
      wx.showToast({ title: message, icon: "none" });
    } finally {
      this.setData({ savingAddress: false });
    }
  },
  chooseAddress(event: WechatMiniprogram.TouchEvent) {
    if (this.data.mode !== "select") {
      return;
    }
    const addressId = String(event.currentTarget.dataset.id || "");
    setSelectedAddress(addressId);
    wx.navigateBack();
  },
  markDefault(event: WechatMiniprogram.TouchEvent) {
    if (this.data.defaultingAddressId || this.data.deletingAddressId || this.data.savingAddress) {
      return;
    }
    const addressId = String(event.currentTarget.dataset.id || "");
    void this.markDefaultAddress(addressId);
  },
  async markDefaultAddress(addressId: string) {
    this.setData({ defaultingAddressId: addressId });
    try {
      await persistDefaultAddress(addressId);
      await this.reloadAddresses();
      wx.showToast({ title: "已设为默认", icon: "success" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "设置默认地址失败";
      wx.showToast({ title: message, icon: "none" });
    } finally {
      this.setData({ defaultingAddressId: "" });
    }
  },
  removeAddress(event: WechatMiniprogram.TouchEvent) {
    if (this.data.defaultingAddressId || this.data.deletingAddressId || this.data.savingAddress) {
      return;
    }
    const addressId = String(event.currentTarget.dataset.id || "");
    const address = findAddressById(addressId);
    wx.showModal({
      title: "删除地址",
      content: address ? `确认删除 ${address.receiverName} 的地址吗？` : "确认删除这个地址吗？",
      confirmText: "删除",
      confirmColor: "#c0342b",
      success: (result) => {
        if (result.confirm) {
          void this.deleteAddress(addressId);
        }
      }
    });
  },
  async deleteAddress(addressId: string) {
    this.setData({ deletingAddressId: addressId });
    try {
      await removeAddressBookItemRemote(addressId);
      await this.reloadAddresses();
      wx.showToast({ title: "地址已删除", icon: "none" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "删除失败";
      wx.showToast({ title: message, icon: "none" });
    } finally {
      this.setData({ deletingAddressId: "" });
    }
  }
});
