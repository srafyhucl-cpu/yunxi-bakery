import { request } from "./http";
import type { PointsLedgerItem } from "../utils/member-assets";

export interface PointsSummary {
  pointsBalance: number;
  mobile: string;
  ledger: PointsLedgerItem[];
}

export interface PointsPreview {
  orderId: string;
  totalFen: number;
  balanceFen: number;
  pointsFen: number;
  pointsUsed: number;
  remainFen: number;
}

export interface PointsApplied extends PointsPreview {}

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

export async function pointsPreview(orderId: string): Promise<PointsPreview> {
  const response = await request<
    WrappedApiResponse<PointsPreview> | PointsPreview,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/points-preview`
  });
  return unwrap(response);
}

export async function applyPoints(orderId: string): Promise<PointsApplied> {
  const response = await request<
    WrappedApiResponse<PointsApplied> | PointsApplied,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/apply-points`
  });
  return unwrap(response);
}
