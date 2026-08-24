import http from "./http";

import type { AddressDetail, AddressDraft, AddressListItem, AddressListPayload } from "@/types/address";

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

export const addressesService = {
  async listAddresses(page: number, keyword: string = ""): Promise<AddressListPayload> {
    const response = await http.get<WrappedApiResponse<AddressListPayload>>("/addresses", {
      params: {
        page,
        keyword: keyword || undefined,
      },
    });
    return response.data.data;
  },

  async getAddress(addressId: string): Promise<AddressDetail> {
    const response = await http.get<WrappedApiResponse<AddressDetail>>(`/addresses/${addressId}`);
    return response.data.data;
  },

  async saveAddress(payload: AddressDraft): Promise<AddressListItem> {
    const method = payload.id ? "put" : "post";
    const url = payload.id ? `/addresses/${payload.id}` : "/addresses";
    const response = await http.request<WrappedApiResponse<AddressListItem>>({
      method,
      url,
      data: payload,
    });
    return response.data.data;
  },

  async setDefault(addressId: string): Promise<AddressListItem> {
    const response = await http.post<WrappedApiResponse<AddressListItem>>(
      `/addresses/${addressId}/default`,
    );
    return response.data.data;
  },

  async deleteAddress(addressId: string): Promise<AddressListItem> {
    const response = await http.delete<WrappedApiResponse<AddressListItem>>(`/addresses/${addressId}`);
    return response.data.data;
  },
};
