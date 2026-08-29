import { API_BASE_URL } from "./config";

export type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";
export type RequestData = string | WechatMiniprogram.IAnyObject | ArrayBuffer;
export const REQUEST_TIMEOUT_MS = 12000;

export interface TransportRequestOptions<TBody extends RequestData> {
  method?: HttpMethod;
  path: string;
  data?: TBody;
  header?: WechatMiniprogram.IAnyObject;
  // 单请求超时覆盖：AI 消息等慢接口需大于默认 12 秒
  timeoutMs?: number;
}

export interface TransportResponse<TData> {
  statusCode: number;
  data: TData;
}

export function sendTransportRequest<
  TData,
  TBody extends RequestData = WechatMiniprogram.IAnyObject
>(
  options: TransportRequestOptions<TBody>
): Promise<TransportResponse<TData>> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE_URL}${options.path}`,
      method: options.method ?? "GET",
      data: options.data,
      timeout: options.timeoutMs ?? REQUEST_TIMEOUT_MS,
      header: {
        "content-type": "application/json",
        ...(options.header ?? {})
      },
      success(response) {
        resolve({
          statusCode: response.statusCode,
          data: response.data as TData
        });
      },
      fail(error) {
        reject(new Error(error.errMsg));
      }
    });
  });
}
