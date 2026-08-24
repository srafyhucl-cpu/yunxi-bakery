import { request } from "./http";

export interface RechargeRecord {
  rechargeId: string;
  amountFen: number;
  status: string;
  paymentMethod: string;
  paidAt: string;
  createdAt: string;
}

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

function unwrap<TData>(response: WrappedApiResponse<TData> | TData): TData {
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<TData>).data;
  }
  return response as TData;
}

export async function createRecharge(amountFen: number): Promise<RechargeRecord> {
  const response = await request<
    WrappedApiResponse<RechargeRecord> | RechargeRecord,
    { amountFen: number }
  >({
    method: "POST",
    path: "/api/v1/miniapp/recharges",
    data: { amountFen }
  });
  return unwrap(response);
}

export async function mockPayRecharge(rechargeId: string): Promise<RechargeRecord> {
  const response = await request<
    WrappedApiResponse<RechargeRecord> | RechargeRecord,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/recharges/${rechargeId}/mock-pay`
  });
  return unwrap(response);
}

export async function cancelRecharge(rechargeId: string): Promise<RechargeRecord> {
  const response = await request<
    WrappedApiResponse<RechargeRecord> | RechargeRecord,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/recharges/${rechargeId}/cancel`
  });
  return unwrap(response);
}

export async function listRecharges(): Promise<RechargeRecord[]> {
  const response = await request<
    WrappedApiResponse<RechargeRecord[]> | RechargeRecord[]
  >({
    path: "/api/v1/miniapp/recharges"
  });
  return unwrap(response);
}
