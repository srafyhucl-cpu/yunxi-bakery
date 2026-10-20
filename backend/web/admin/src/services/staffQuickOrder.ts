import axios from "axios";

import type {
  QuickOrderPayload,
  QuickOrderResult,
  StaffLoginResult,
  StaffMember,
  StaffPrincipal,
  StaffProduct,
} from "@/types/staffQuickOrder";

/**
 * 店员端独立请求实例：
 * - baseURL 直接指向 /api/v1/staff，调用处不再拼接前缀；
 * - 不挂 admin http.ts 的 401 跳转拦截器，登录态由店员页面自行处理。
 */
const staffHttp = axios.create({
  baseURL: "/api/v1/staff",
  withCredentials: true,
  timeout: 30000,
});

interface StaffEnvelope<T> {
  ok: boolean;
  data: T;
}

/** 统一取出 { ok, data } 中的业务数据，ok 为 false 视为服务端异常。 */
function unwrap<T>(envelope: StaffEnvelope<T>): T {
  if (!envelope.ok) {
    throw new Error("店员服务返回异常");
  }
  return envelope.data;
}

export const staffQuickOrderService = {
  async login(phone: string, pin: string): Promise<StaffLoginResult> {
    const response = await staffHttp.post<StaffEnvelope<StaffLoginResult>>(
      "/auth/login",
      { phone, pin },
    );
    return unwrap(response.data);
  },

  async me(): Promise<StaffPrincipal> {
    const response = await staffHttp.get<StaffEnvelope<StaffPrincipal>>("/auth/me");
    return unwrap(response.data);
  },

  async logout(): Promise<void> {
    await staffHttp.post("/auth/logout");
  },

  async lookupMember(phone: string): Promise<StaffMember> {
    const response = await staffHttp.get<StaffEnvelope<StaffMember>>(
      "/quick-order/member-lookup",
      { params: { phone } },
    );
    return unwrap(response.data);
  },

  async listProducts(keyword: string, limit: number = 20): Promise<StaffProduct[]> {
    const response = await staffHttp.get<StaffEnvelope<StaffProduct[]>>(
      "/quick-order/products",
      { params: { keyword: keyword || undefined, limit } },
    );
    return unwrap(response.data);
  },

  async create(payload: QuickOrderPayload): Promise<QuickOrderResult> {
    const response = await staffHttp.post<StaffEnvelope<QuickOrderResult>>(
      "/quick-order/create",
      payload,
    );
    return unwrap(response.data);
  },
};
