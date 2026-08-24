import fs from "node:fs";
import path from "node:path";

const reportsRoot = path.join(process.cwd(), "reports", "production-api-check");
const targets = [
  {
    name: "miniapp home page config",
    url: "https://yunxifood.cn/api/v1/miniapp/pages/home",
    expectJson: true,
    validate(data) {
      return data && typeof data === "object" && typeof data.pageId === "string";
    },
  },
  {
    name: "miniapp product list",
    url: "https://yunxifood.cn/api/v1/miniapp/products",
    expectJson: true,
    validate(data) {
      return (
        Array.isArray(data) &&
        data.length > 0 &&
        data.every((item) => {
          return (
            item &&
            typeof item === "object" &&
            typeof item.categoryId === "string" &&
            item.categoryId.length > 0 &&
            item.categoryId !== "商品" &&
            typeof item.categoryName === "string" &&
            item.categoryName.length > 0 &&
            item.categoryName !== "商品"
          );
        })
      );
    },
  },
  {
    name: "miniapp product categories",
    url: "https://yunxifood.cn/api/v1/miniapp/product-categories",
    expectJson: true,
    validate(data) {
      return (
        Array.isArray(data) &&
        data.length > 0 &&
        data.every((item) => {
          return (
            item &&
            typeof item === "object" &&
            typeof item.id === "string" &&
            item.id.length > 0 &&
            typeof item.title === "string" &&
            item.title.length > 0 &&
            !item.title.startsWith("有赞分组 ")
          );
        })
      );
    },
  },
  {
    name: "miniapp shop settings",
    url: "https://yunxifood.cn/api/v1/miniapp/shop-settings",
    expectJson: true,
    validate(data) {
      return data && typeof data === "object" && typeof data.shopName === "string";
    },
  },
];
const authLoginTarget = {
  name: "miniapp auth login configuration",
  url: "https://yunxifood.cn/api/v1/miniapp/auth/login",
};

async function checkTarget(target) {
  const startedAt = Date.now();
  try {
    const response = await fetch(target.url, { method: "GET" });
    const body = await response.text();
    let parsed = null;
    let parseError = "";
    if (target.expectJson) {
      try {
        parsed = JSON.parse(body);
      } catch (error) {
        parseError = String(error?.message || error);
      }
    }
    const code = parsed && typeof parsed.code !== "undefined" ? parsed.code : null;
    const data = parsed && typeof parsed.data !== "undefined" ? parsed.data : null;
    const validationOk = data !== null && (!target.validate || target.validate(data));
    const ok = response.ok && parseError === "" && code === 0 && validationOk;
    return {
      name: target.name,
      url: target.url,
      ok,
      status: response.status,
      durationMs: Date.now() - startedAt,
      bodyHead: body.slice(0, 300),
      error: parseError,
      code,
      dataType: Array.isArray(data) ? "array" : data === null ? "null" : typeof data,
      itemCount: Array.isArray(data) ? data.length : null,
      validationOk,
    };
  } catch (error) {
    return {
      name: target.name,
      url: target.url,
      ok: false,
      status: 0,
      durationMs: Date.now() - startedAt,
      bodyHead: "",
      error: String(error?.message || error),
      cause: error?.cause ? String(error.cause?.message || error.cause) : "",
      code: null,
      dataType: "null",
    };
  }
}

async function checkAuthLoginConfiguration() {
  const startedAt = Date.now();
  try {
    const response = await fetch(authLoginTarget.url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({ code: "codex-invalid-login-code" }),
    });
    const body = await response.text();
    let parsed = null;
    let parseError = "";
    try {
      parsed = JSON.parse(body);
    } catch (error) {
      parseError = String(error?.message || error);
    }
    const detail = parsed && typeof parsed.detail === "string" ? parsed.detail : "";
    const isMissingWechatConfig = /AppID\/Secret 未配置|未配置.*真实会话/.test(detail);
    const ok = response.status === 400 && parseError === "" && detail !== "" && !isMissingWechatConfig;
    return {
      name: authLoginTarget.name,
      url: authLoginTarget.url,
      ok,
      status: response.status,
      durationMs: Date.now() - startedAt,
      bodyHead: body.slice(0, 300),
      error: parseError,
      detail,
      validationOk: ok,
      expectedBehavior: "invalid wx.login code should fail only after backend WeChat AppID/Secret are configured",
    };
  } catch (error) {
    return {
      name: authLoginTarget.name,
      url: authLoginTarget.url,
      ok: false,
      status: 0,
      durationMs: Date.now() - startedAt,
      bodyHead: "",
      error: String(error?.message || error),
      cause: error?.cause ? String(error.cause?.message || error.cause) : "",
      detail: "",
      validationOk: false,
    };
  }
}

async function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const checks = [];
  for (const target of targets) {
    checks.push(await checkTarget(target));
  }
  checks.push(await checkAuthLoginConfiguration());
  const report = {
    traceId: "20260707-production-miniapp-auth-config-gate",
    generatedAt: new Date().toISOString(),
    status: checks.every((item) => item.ok) ? "pass" : "fail",
    checks,
  };
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
  const reportPath = path.join(reportsRoot, `production-miniapp-api-${stamp}.json`);
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "latest.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(
    `Production miniapp API ${report.status}: ${[...targets, authLoginTarget]
      .map((target) => target.url)
      .join(", ")}`
  );
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
