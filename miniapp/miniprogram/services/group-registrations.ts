import { request } from "./http";

export type GroupRegistrationFulfillmentMethod = "pickup" | "delivery";
export type GroupRegistrationStatus = "pending" | "confirmed" | "cancelled";

export interface GroupRegistrationPayload {
  campaignId: string;
  customerName: string;
  customerPhone: string;
  productName: string;
  quantity: number;
  fulfillmentMethod: GroupRegistrationFulfillmentMethod;
  desiredTime: string;
  address: string;
  remark: string;
}

export interface GroupRegistration {
  id: string;
  campaignId: string;
  groupId: string;
  userId: string;
  customerName: string;
  customerPhone: string;
  productName: string;
  quantity: number;
  fulfillmentMethod: GroupRegistrationFulfillmentMethod;
  desiredTime: string;
  address: string;
  remark: string;
  status: GroupRegistrationStatus;
  createdAt: string;
  updatedAt: string;
}

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

function unwrapResponse<TData>(response: WrappedApiResponse<TData> | TData): TData {
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<TData>).data;
  }
  return response as TData;
}

export async function submitGroupRegistration(
  payload: GroupRegistrationPayload
): Promise<GroupRegistration> {
  const response = await request<
    WrappedApiResponse<GroupRegistration>,
    GroupRegistrationPayload
  >({
    method: "POST",
    path: "/api/v1/miniapp/group-registrations",
    data: payload
  });
  return unwrapResponse(response);
}

export async function listMyGroupRegistrations(): Promise<GroupRegistration[]> {
  const response = await request<WrappedApiResponse<GroupRegistration[]> | GroupRegistration[]>({
    path: "/api/v1/miniapp/group-registrations/me"
  });
  return unwrapResponse(response);
}
