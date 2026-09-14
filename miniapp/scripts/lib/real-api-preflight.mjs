// 真实链路脚本会直接访问线上 API。证书过期、DNS 或网络不可达时，
// 开发者工具里只会留下“automator 响应超时”，很容易被误判成页面缺陷，
// 因此这里先做一次快速预检，把环境原因明确报出来。
import http from "node:http";
import https from "node:https";

export const DEFAULT_REAL_API_BASE_URL = "https://yunxifood.cn";

export function resolveRealApiBaseUrl() {
  const raw = String(process.env.MINIAPP_REAL_API_BASE_URL || DEFAULT_REAL_API_BASE_URL).trim();
  return raw.replace(/\/+$/, "");
}

const ERROR_HINTS = {
  CERT_HAS_EXPIRED: "TLS 证书已过期，需要先完成续期",
  CERT_NOT_YET_VALID: "TLS 证书尚未生效",
  DEPTH_ZERO_SELF_SIGNED_CERT: "TLS 证书为自签名，链校验不通过",
  UNABLE_TO_VERIFY_LEAF_SIGNATURE: "TLS 证书链校验失败",
  SELF_SIGNED_CERT_IN_CHAIN: "TLS 证书链包含自签名证书",
  ENOTFOUND: "域名解析失败",
  ECONNREFUSED: "目标端口拒绝连接",
  ETIMEDOUT: "连接超时",
  ECONNRESET: "连接被重置",
};

export function describeNetworkError(error) {
  const code = String(error?.code || "");
  const hint = ERROR_HINTS[code];
  const detail = String(error?.message || error);
  return hint ? `${hint}（${code}）` : detail;
}

// 只判断“能否完成一次 HTTPS 请求”，业务状态码交给脚本本身校验。
export function probeRealApi(baseUrl, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    let target;
    try {
      target = new URL("/health", baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
    } catch {
      reject(new Error(`真实链路 API 地址非法：${baseUrl}`));
      return;
    }
    const client = target.protocol === "http:" ? http : https;
    const request = client.request(target, { method: "GET", timeout: timeoutMs }, (response) => {
      response.resume();
      resolve({ url: target.toString(), status: response.statusCode });
    });
    request.on("timeout", () => {
      const timeoutError = new Error(`请求超时（${timeoutMs}ms）`);
      timeoutError.code = "ETIMEDOUT";
      request.destroy(timeoutError);
    });
    request.on("error", reject);
    request.end();
  });
}

export async function assertRealApiReachable(baseUrl, timeoutMs = 10000) {
  try {
    return await probeRealApi(baseUrl, timeoutMs);
  } catch (error) {
    throw new Error(`真实链路 API 不可用：${baseUrl} — ${describeNetworkError(error)}`);
  }
}
