import { STORAGE_KEYS } from "../constants/storage";
import {
  deleteAddress,
  listAddresses,
  saveAddress,
  setDefaultAddress as setDefaultAddressRemote,
} from "../services/address";

export interface AddressBookDraft {
  id?: string;
  receiverName: string;
  receiverPhone: string;
  address: string;
  isDefault?: boolean;
}

export const ADDRESS_PHONE_PATTERN = /^1[3-9]\d{9}$/;

function normalizeText(value: string): string {
  return value.trim();
}

function createAddressId(): string {
  return `addr_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
}

function normalizeAddressItem(item: Partial<AddressBookItem>): AddressBookItem | null {
  const receiverName = normalizeText(String(item.receiverName || ""));
  const receiverPhone = normalizeText(String(item.receiverPhone || ""));
  const address = normalizeText(String(item.address || ""));
  if (!receiverName || !receiverPhone || !address) {
    return null;
  }
  return {
    id: String(item.id || createAddressId()),
    receiverName,
    receiverPhone,
    address,
    isDefault: Boolean(item.isDefault),
    updatedAt: String(item.updatedAt || new Date().toISOString())
  };
}

export function getAddressBookItems(): AddressBookItem[] {
  const value = wx.getStorageSync(STORAGE_KEYS.addressBookItems);
  if (!Array.isArray(value)) {
    return [];
  }
  const items = value
    .map((item) => normalizeAddressItem(item as Partial<AddressBookItem>))
    .filter((item): item is AddressBookItem => Boolean(item));
  return ensureSingleDefault(items);
}

export async function syncAddressBookFromBackend(): Promise<AddressBookItem[]> {
  try {
    const items = await listAddresses();
    if (items.length > 0) {
      saveAddressBookItems(items);
      const app = getApp<IAppOption>();
      app.globalData.addressBookItems = items;
      return items;
    }
    const localItems = getAddressBookItems();
    if (!localItems.length) {
      saveAddressBookItems([]);
      return [];
    }
    const orderedItems = [
      ...localItems.filter((item) => item.isDefault),
      ...localItems.filter((item) => !item.isDefault)
    ];
    const uploadedItems: AddressBookItem[] = [];
    for (const item of orderedItems) {
      const saved = await saveAddress({
        id: item.id,
        receiverName: item.receiverName,
        receiverPhone: item.receiverPhone,
        address: item.address,
        isDefault: item.isDefault
      });
      uploadedItems.push(saved);
    }
    saveAddressBookItems(uploadedItems);
    return uploadedItems;
  } catch {
    return getAddressBookItems();
  }
}

export function saveAddressBookItems(items: AddressBookItem[]): void {
  const normalizedItems = ensureSingleDefault(items);
  wx.setStorageSync(STORAGE_KEYS.addressBookItems, normalizedItems);
  const app = getApp<IAppOption>();
  app.globalData.addressBookItems = normalizedItems;
}

export function getDefaultAddress(): AddressBookItem | undefined {
  const items = getAddressBookItems();
  return items.find((item) => item.isDefault) || items[0];
}

export function getSelectedAddress(): AddressBookItem | undefined {
  const selectedAddressId = wx.getStorageSync(STORAGE_KEYS.selectedAddressId);
  if (typeof selectedAddressId === "string" && selectedAddressId) {
    const selected = findAddressById(selectedAddressId);
    if (selected) {
      return selected;
    }
  }
  return getDefaultAddress();
}

export function setSelectedAddress(addressId: string): void {
  wx.setStorageSync(STORAGE_KEYS.selectedAddressId, addressId);
}

export function findAddressById(addressId: string): AddressBookItem | undefined {
  return getAddressBookItems().find((item) => item.id === addressId);
}

export function upsertAddressBookItem(draft: AddressBookDraft): AddressBookItem {
  const items = getAddressBookItems();
  const addressId = draft.id || createAddressId();
  const nextItem = normalizeAddressItem({
    id: addressId,
    receiverName: draft.receiverName,
    receiverPhone: draft.receiverPhone,
    address: draft.address,
    isDefault: draft.isDefault ?? items.length === 0,
    updatedAt: new Date().toISOString()
  });
  if (!nextItem) {
    throw new Error("地址信息不完整");
  }
  const nextItems = items.filter((item) => item.id !== addressId);
  nextItems.unshift(nextItem);
  saveAddressBookItems(nextItems);
  return nextItem;
}

export function setDefaultAddress(addressId: string): void {
  saveAddressBookItems(
    getAddressBookItems().map((item) => ({
      ...item,
      isDefault: item.id === addressId
    }))
  );
}

export function removeAddressBookItem(addressId: string): void {
  saveAddressBookItems(getAddressBookItems().filter((item) => item.id !== addressId));
}

export async function persistAddressBookDraft(draft: AddressBookDraft): Promise<AddressBookItem> {
  const item = await saveAddress({
    id: draft.id || undefined,
    receiverName: draft.receiverName,
    receiverPhone: draft.receiverPhone,
    address: draft.address,
    isDefault: draft.isDefault
  });
  const items = getAddressBookItems();
  const nextItems = items.filter((existing) => existing.id !== item.id);
  nextItems.unshift(item);
  saveAddressBookItems(nextItems);
  return item;
}

export async function persistDefaultAddress(addressId: string): Promise<void> {
  const item = await setDefaultAddressRemote(addressId);
  const nextItems = getAddressBookItems().map((existing) => ({
    ...existing,
    isDefault: existing.id === item.id
  }));
  saveAddressBookItems(nextItems);
}

export async function removeAddressBookItemRemote(addressId: string): Promise<void> {
  const items = await deleteAddress(addressId);
  saveAddressBookItems(items);
}

export function validateAddressBookDraft(draft: AddressBookDraft): string {
  if (!normalizeText(draft.receiverName)) {
    return "请填写联系人";
  }
  if (!ADDRESS_PHONE_PATTERN.test(normalizeText(draft.receiverPhone))) {
    return "请填写正确的 11 位手机号";
  }
  if (!normalizeText(draft.address)) {
    return "请填写收货地址";
  }
  return "";
}

function ensureSingleDefault(items: AddressBookItem[]): AddressBookItem[] {
  if (!items.length) {
    return [];
  }
  let hasDefault = false;
  return items.map((item, index) => {
    const isDefault = hasDefault ? false : item.isDefault || index === 0;
    if (isDefault) {
      hasDefault = true;
    }
    return { ...item, isDefault };
  });
}
