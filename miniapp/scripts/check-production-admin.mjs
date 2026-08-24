import fs from "node:fs";
import path from "node:path";

const reportsRoot = path.join(process.cwd(), "reports", "production-admin-check");
const adminUrl = "https://yunxifood.cn/admin/";
const requiredChunks = [
  "DecorationPage",
  "OrdersPage",
  "AddressesPage",
  "ProductsPage",
  "TransfersPage",
  "ShopSettingsPage",
];

async function fetchText(url) {
  const startedAt = Date.now();
  const response = await fetch(url, { method: "GET" });
  const body = await response.text();
  return {
    url,
    ok: response.ok,
    status: response.status,
    durationMs: Date.now() - startedAt,
    body,
  };
}

function extractAssetPaths(html) {
  const assets = new Set();
  for (const match of html.matchAll(/(?:src|href)="([^"]+)"/g)) {
    const value = match[1];
    if (value.startsWith("/admin/assets/")) {
      assets.add(value);
    }
  }
  return [...assets];
}

async function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const checks = [];
  let htmlBody = "";
  try {
    const html = await fetchText(adminUrl);
    htmlBody = html.body;
    checks.push({
      name: "admin html",
      url: html.url,
      ok: html.ok && html.body.includes('<div id="app"></div>'),
      status: html.status,
      durationMs: html.durationMs,
      bodyHead: html.body.slice(0, 300),
    });
  } catch (error) {
    checks.push({
      name: "admin html",
      url: adminUrl,
      ok: false,
      status: 0,
      durationMs: 0,
      bodyHead: "",
      error: String(error?.message || error),
    });
  }

  const assetPaths = extractAssetPaths(htmlBody);
  const assetResults = [];
  for (const assetPath of assetPaths) {
    const assetUrl = new URL(assetPath, adminUrl).toString();
    try {
      const asset = await fetchText(assetUrl);
      assetResults.push({
        url: assetUrl,
        ok: asset.ok,
        status: asset.status,
        durationMs: asset.durationMs,
        bodyLength: asset.body.length,
        bodyHead: asset.body.slice(0, 120),
        bodyForCheck: asset.body,
      });
    } catch (error) {
      assetResults.push({
        url: assetUrl,
        ok: false,
        status: 0,
        durationMs: 0,
        bodyHead: "",
        error: String(error?.message || error),
      });
    }
  }
  checks.push({
    name: "admin referenced assets",
    ok: assetResults.length > 0 && assetResults.every((item) => item.ok),
    assets: assetResults,
  });

  const bundleText = assetResults.map((item) => item.bodyForCheck || item.bodyHead || "").join("\n");
  const missingChunks = requiredChunks.filter((chunk) => !htmlBody.includes(chunk) && !bundleText.includes(chunk));
  const reportAssetResults = assetResults.map(({ bodyForCheck: _bodyForCheck, ...item }) => item);
  checks.push({
    name: "admin MVP chunk presence",
    ok: missingChunks.length === 0,
    requiredChunks,
    missingChunks,
  });

  const report = {
    traceId: "20260617-production-admin-frontend-check",
    generatedAt: new Date().toISOString(),
    status: checks.every((item) => item.ok) ? "pass" : "fail",
    checks: checks.map((check) =>
      check.name === "admin referenced assets" ? { ...check, assets: reportAssetResults } : check
    ),
  };
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
  const reportPath = path.join(reportsRoot, `production-admin-${stamp}.json`);
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "latest.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(`Production admin check ${report.status}: ${adminUrl}`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
