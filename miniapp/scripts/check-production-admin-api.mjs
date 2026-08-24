import fs from "node:fs";
import path from "node:path";

const reportsRoot = path.join(process.cwd(), "reports", "production-admin-api-check");
const adminApiBaseUrl = "https://yunxifood.cn/api/v1/admin";
const token = process.env.YUNXI_ADMIN_API_TOKEN || process.env.ADMIN_API_TOKEN || "";

const targets = [
  {
    name: "admin settings summary",
    url: `${adminApiBaseUrl}/settings/summary`,
    validate(data) {
      return data && typeof data === "object";
    },
  },
  {
    name: "admin shop operations",
    url: `${adminApiBaseUrl}/shop-config/operations`,
    validate(data) {
      return data && typeof data === "object" && typeof data.shopName === "string";
    },
  },
  {
    name: "admin home decoration config",
    url: `${adminApiBaseUrl}/shop-config/pages/home`,
    validate(data) {
      return data && typeof data === "object" && ("draft" in data || "published" in data);
    },
  },
  {
    name: "admin order summary",
    url: `${adminApiBaseUrl}/orders/summary`,
    validate(data) {
      return data && typeof data === "object" && Array.isArray(data.cards);
    },
  },
  {
    name: "admin order list",
    url: `${adminApiBaseUrl}/orders?page=1`,
    validate(data) {
      return data && typeof data === "object" && Array.isArray(data.items);
    },
  },
  {
    name: "admin address list",
    url: `${adminApiBaseUrl}/addresses?page=1`,
    validate(data) {
      return data && typeof data === "object" && Array.isArray(data.items);
    },
  },
  {
    name: "admin pending transfers",
    url: `${adminApiBaseUrl}/transfers/pending`,
    validate(data) {
      return Array.isArray(data);
    },
  },
];

async function checkTarget(target) {
  const startedAt = Date.now();
  try {
    const response = await fetch(target.url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    const body = await response.text();
    let parsed = null;
    let parseError = "";
    try {
      parsed = JSON.parse(body);
    } catch (error) {
      parseError = String(error?.message || error);
    }

    const code = parsed && typeof parsed.code !== "undefined" ? parsed.code : null;
    const data = parsed && typeof parsed.data !== "undefined" ? parsed.data : null;
    const contractOk = response.ok && parseError === "" && code === 0 && target.validate(data);

    return {
      name: target.name,
      url: target.url,
      ok: contractOk,
      status: response.status,
      durationMs: Date.now() - startedAt,
      bodyHead: body.slice(0, 300),
      error: parseError,
      code,
      dataType: Array.isArray(data) ? "array" : data === null ? "null" : typeof data,
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

function writeReport(report) {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
  const reportPath = path.join(reportsRoot, `production-admin-api-${stamp}.json`);
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "latest.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return reportPath;
}

async function main() {
  if (!token) {
    const report = {
      traceId: "20260617-production-admin-api-check",
      generatedAt: new Date().toISOString(),
      status: "skip",
      reason: "YUNXI_ADMIN_API_TOKEN or ADMIN_API_TOKEN is not set; authenticated production admin API smoke was not executed.",
      checks: [],
    };
    const reportPath = writeReport(report);
    console.log("Production admin API check skipped: set YUNXI_ADMIN_API_TOKEN or ADMIN_API_TOKEN to run authenticated read-only smoke.");
    console.log(`Report: ${reportPath}`);
    return;
  }

  const checks = [];
  for (const target of targets) {
    checks.push(await checkTarget(target));
  }
  const report = {
    traceId: "20260617-production-admin-api-check",
    generatedAt: new Date().toISOString(),
    status: checks.every((item) => item.ok) ? "pass" : "fail",
    checks,
  };
  const reportPath = writeReport(report);
  console.log(`Production admin API check ${report.status}: ${targets.map((target) => target.url).join(", ")}`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
