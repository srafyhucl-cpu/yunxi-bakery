import { request } from "./http";

export interface BalanceSummary {
  balanceFen: number;
  mobile: string;
}

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

export async function getBalance(): Promise<BalanceSummary> {
  const response = await request<WrappedApiResponse<BalanceSummary> | BalanceSummary>({
    path: "/api/v1/miniapp/balance"
  });
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<BalanceSummary>).data;
  }
  return response as BalanceSummary;
}
