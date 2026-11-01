import { request } from "./http";
import type { PointsLedgerItem } from "../utils/member-assets";

export interface PointsSummary {
  pointsBalance: number;
  mobile: string;
  ledger: PointsLedgerItem[];
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

export async function getPoints(): Promise<PointsSummary> {
  const response = await request<WrappedApiResponse<PointsSummary> | PointsSummary>({
    path: "/api/v1/miniapp/points"
  });
  return unwrap(response);
}
