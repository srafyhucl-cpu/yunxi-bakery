import http from "./http";

export interface CouponTemplatePayload {
  name: string;
  couponType: string;
  thresholdFen?: number;
  valueFen?: number;
  discountBp?: number;
  capFen?: number;
  validFrom?: string;
  validUntil?: string;
  status?: string;
}

export interface CouponTemplate {
  id: string;
  name: string;
  coupon_type: string;
  threshold_fen: number;
  value_fen: number;
  discount_bp: number;
  cap_fen: number;
  valid_from: string;
  valid_until: string;
  status: string;
  source: string;
}

export interface CouponRecord {
  coupon_id: string;
  coupon_group_id: string;
  mobile: string;
  status: string;
  order_no: string;
  title: string;
  deducted_fen: number;
  source: string;
  occurred_at: string;
}

export interface CouponGrant {
  coupon_code: string;
  mobile: string;
  status: string;
}

export interface TemplateListResult {
  templates: CouponTemplate[];
}

export interface RecordListResult {
  records: CouponRecord[];
  grants: CouponGrant[];
}

export interface GrantResult {
  couponId: string;
  couponCode: string;
  mobile: string;
  templateId: string;
  status: string;
}

interface ApiResponse<T> {
  code: number;
  data: T;
}

export async function listTemplates(status = ""): Promise<TemplateListResult> {
  const { data } = await http.get<ApiResponse<TemplateListResult>>(
    "/api/v1/admin/coupons/templates",
    { params: { status } },
  );
  return data.data;
}

export async function createTemplate(payload: CouponTemplatePayload): Promise<CouponTemplate> {
  const { data } = await http.post<ApiResponse<CouponTemplate>>(
    "/api/v1/admin/coupons/templates",
    payload,
  );
  return data.data;
}

export async function updateTemplate(
  id: string,
  payload: CouponTemplatePayload,
): Promise<CouponTemplate> {
  const { data } = await http.put<ApiResponse<CouponTemplate>>(
    `/api/v1/admin/coupons/templates/${id}`,
    payload,
  );
  return data.data;
}

export async function setTemplateStatus(id: string, status: string): Promise<CouponTemplate> {
  const { data } = await http.post<ApiResponse<CouponTemplate>>(
    `/api/v1/admin/coupons/templates/${id}/status`,
    { status },
  );
  return data.data;
}

export async function listRecords(params: {
  mobile?: string;
  status?: string;
  templateId?: string;
}): Promise<RecordListResult> {
  const { data } = await http.get<ApiResponse<RecordListResult>>(
    "/api/v1/admin/coupons/records",
    { params },
  );
  return data.data;
}

export async function grantCoupon(templateId: string, mobile: string): Promise<GrantResult> {
  const { data } = await http.post<ApiResponse<GrantResult>>(
    "/api/v1/admin/coupons/grants",
    { templateId, mobile },
  );
  return data.data;
}
