import { request } from "./http";

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

export interface AddressBookItem {
  id: string;
  receiverName: string;
  receiverPhone: string;
  address: string;
  isDefault: boolean;
  updatedAt: string;
}

export interface AddressBookPayload {
  id?: string;
  receiverName: string;
  receiverPhone: string;
  address: string;
  isDefault?: boolean;
}

function unwrapResponse<TData>(response: WrappedApiResponse<TData> | TData): TData {
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<TData>).data;
  }
  return response as TData;
}

export async function listAddresses(): Promise<AddressBookItem[]> {
  const response = await request<WrappedApiResponse<AddressBookItem[]> | AddressBookItem[]>({
    path: "/api/v1/miniapp/addresses"
  });
  return unwrapResponse(response);
}

export async function saveAddress(payload: AddressBookPayload): Promise<AddressBookItem> {
  const response = await request<WrappedApiResponse<AddressBookItem>, AddressBookPayload>({
    method: "POST",
    path: "/api/v1/miniapp/addresses",
    data: payload
  });
  return unwrapResponse(response);
}

export async function setDefaultAddress(addressId: string): Promise<AddressBookItem> {
  const response = await request<WrappedApiResponse<AddressBookItem>>({
    method: "POST",
    path: `/api/v1/miniapp/addresses/${addressId}/default`
  });
  return unwrapResponse(response);
}

export async function deleteAddress(addressId: string): Promise<AddressBookItem[]> {
  const response = await request<WrappedApiResponse<AddressBookItem[]> | AddressBookItem[]>({
    method: "DELETE",
    path: `/api/v1/miniapp/addresses/${addressId}`
  });
  return unwrapResponse(response);
}
