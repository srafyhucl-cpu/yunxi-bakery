import fs from "node:fs";
import path from "node:path";
import automator from "miniprogram-automator";

const root = process.cwd();
const reportsRoot = path.join(root, "reports", "button-runtime");
const wsEndpoint = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";

function nowStamp() {
  return new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
}

function summarizePayload(payload) {
  if (!payload || typeof payload !== "object") {
    return { type: typeof payload };
  }
  const data = Object.prototype.hasOwnProperty.call(payload, "data") ? payload.data : payload;
  if (Array.isArray(data)) {
    return { type: "array", itemCount: data.length };
  }
  if (data && typeof data === "object") {
    return {
      type: "object",
      keys: Object.keys(data).slice(0, 12),
      itemCount: Array.isArray(data.items) ? data.items.length : undefined,
    };
  }
  return { type: typeof data };
}

async function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const miniProgram = await automator.connect({ wsEndpoint });
  let runtimeResult;
  try {
    runtimeResult = await miniProgram.evaluate(function () {
      const apiBaseUrl = "https://yunxifood.cn";
      const authPath = "/api/v1/miniapp/auth/login";
      const targets = [
        { name: "order list", path: "/api/v1/miniapp/orders" },
        { name: "address list", path: "/api/v1/miniapp/addresses" },
        { name: "chat messages", path: "/api/v1/miniapp/chat/messages" },
      ];

      function summarize(payload) {
        if (!payload || typeof payload !== "object") {
          return { type: typeof payload };
        }
        const data = Object.prototype.hasOwnProperty.call(payload, "data") ? payload.data : payload;
        if (Array.isArray(data)) {
          return { type: "array", itemCount: data.length };
        }
        if (data && typeof data === "object") {
          return {
            type: "object",
            keys: Object.keys(data).slice(0, 12),
            itemCount: Array.isArray(data.items) ? data.items.length : undefined,
          };
        }
        return { type: typeof data };
      }

      function loginWithWechat() {
        return new Promise(function (resolve) {
          wx.login({
            success: function (loginResponse) {
              if (!loginResponse.code) {
                resolve({ ok: false, statusCode: 0, errMsg: "wx.login returned no code" });
                return;
              }
              wx.request({
                url: apiBaseUrl + authPath,
                method: "POST",
                data: { code: loginResponse.code },
                timeout: 10000,
                header: { "content-type": "application/json" },
                success: function (response) {
                  const body = response.data && typeof response.data === "object" ? response.data : {};
                  const payload = body.data && typeof body.data === "object" ? body.data : body;
                  const accessToken = typeof payload.accessToken === "string" ? payload.accessToken : "";
                  resolve({
                    ok: response.statusCode >= 200 && response.statusCode < 300 && Boolean(accessToken),
                    statusCode: response.statusCode,
                    hasAccessToken: Boolean(accessToken),
                    accessToken,
                    tokenType: typeof payload.tokenType === "string" ? payload.tokenType : "",
                    expiresIn: typeof payload.expiresIn === "number" ? payload.expiresIn : 0,
                    summary: summarize(response.data),
                  });
                },
                fail: function (error) {
                  resolve({ ok: false, statusCode: 0, errMsg: error.errMsg });
                },
              });
            },
            fail: function (error) {
              resolve({ ok: false, statusCode: 0, errMsg: error.errMsg });
            },
          });
        });
      }

      function requestTarget(target, accessToken) {
        return new Promise(function (resolve) {
          wx.request({
            url: apiBaseUrl + target.path,
            method: "GET",
            timeout: 10000,
            header: {
              "content-type": "application/json",
              Authorization: "Bearer " + accessToken,
            },
            success: function (response) {
              const body = response.data && typeof response.data === "object" ? response.data : {};
              const code = typeof body.code === "number" ? body.code : undefined;
              resolve({
                name: target.name,
                path: target.path,
                ok: response.statusCode >= 200 && response.statusCode < 300 && code === 0,
                statusCode: response.statusCode,
                code,
                summary: summarize(response.data),
              });
            },
            fail: function (error) {
              resolve({
                name: target.name,
                path: target.path,
                ok: false,
                statusCode: 0,
                errMsg: error.errMsg,
              });
            },
          });
        });
      }

      return loginWithWechat().then(function (loginResult) {
        const safeLogin = {
          name: "login",
          path: authPath,
          ok: loginResult.ok,
          statusCode: loginResult.statusCode,
          hasAccessToken: Boolean(loginResult.accessToken),
          tokenType: loginResult.tokenType || "",
          expiresIn: loginResult.expiresIn || 0,
          errMsg: loginResult.errMsg || "",
          summary: loginResult.summary || {},
        };
        if (!loginResult.ok || !loginResult.accessToken) {
          return {
            apiBaseUrl,
            login: safeLogin,
            session: { hasAccessToken: false, tokenType: "", expiresIn: 0 },
            checks: [],
          };
        }
        return Promise.all(targets.map(function (target) {
          return requestTarget(target, loginResult.accessToken);
        })).then(function (checks) {
          return {
            apiBaseUrl,
            login: safeLogin,
            session: {
              hasAccessToken: true,
              tokenType: loginResult.tokenType,
              expiresIn: loginResult.expiresIn,
            },
            checks,
          };
        });
      });
    });
  } finally {
    await miniProgram.disconnect();
  }

  const checks = [runtimeResult.login, ...runtimeResult.checks];
  const report = {
    traceId: "20260805-storefront-auth-contract",
    generatedAt: new Date().toISOString(),
    wsEndpoint,
    apiBaseUrl: runtimeResult.apiBaseUrl,
    session: runtimeResult.session,
    status: checks.length > 0 && checks.every((check) => check.ok) ? "pass" : "fail",
    checks: checks.map((check) => ({
      name: check.name,
      path: check.path,
      ok: Boolean(check.ok),
      statusCode: check.statusCode,
      code: check.code,
      errMsg: check.errMsg || "",
      summary: check.summary || summarizePayload({}),
    })),
    notes: [
      "This smoke performs wx.login and only reads protected order, address, and chat endpoints.",
      "The report intentionally excludes accessToken, openid, userId, order content, address, and chat text.",
      "It proves DevTools runtime authentication only; production release still requires WeChat legal-domain evidence.",
    ],
  };
  const stamp = nowStamp();
  const reportPath = path.join(reportsRoot, `devtools-service-smoke-${stamp}.json`);
  const payload = `${JSON.stringify(report, null, 2)}\n`;
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "devtools-service-smoke-latest.json"), payload, "utf8");
  console.log(`DevTools storefront auth smoke ${report.status}: ${checks.length} checks.`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
