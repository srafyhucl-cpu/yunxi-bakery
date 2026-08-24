import { request } from "./http";
import type { MemberCoupon } from "../utils/member-assets";

export interface MyCouponsData {
  mobile: string;
  coupons: MemberCoupon[];
}

export interface CouponPreview {
  orderId: string;
  totalFen: number;
  balanceFen: number;
  pointsFen: number;
  available: Array<{
    couponId: string;
    title: string;
    valueFen: number;
    thresholdFen: number;
    validUntil: string;
    discountFen: number;
    message?: string;
  }>;
  remainFen: number;
}

export interface CouponApplied {
  orderId: string;
  couponId: string;
  couponFen: number;
  totalFen: number;
  balanceFen: number;
  pointsFen: number;
  remainFen: number;
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

export async function getMyCoupons(): Promise<MyCouponsData> {
  const response = await request<WrappedApiResponse<MyCouponsData> | MyCouponsData>({
    path: "/api/v1/miniapp/coupons"
  });
  return unwrap(response);
}

export async function couponPreview(orderId: string): Promise<CouponPreview> {
  const response = await request<
    WrappedApiResponse<CouponPreview> | CouponPreview,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/coupon-preview`
  });
  return unwrap(response);
}

export async function applyCoupon(orderId: string, couponId: string): Promise<CouponApplied> {
  const response = await request<
    WrappedApiResponse<CouponApplied> | CouponApplied,
    { couponId: string }
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/apply-coupon`,
    data: { couponId }
  });
  return unwrap(response);
}
