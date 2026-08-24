import fs from "node:fs";
import path from "node:path";

const reportsRoot = path.join(process.cwd(), "reports", "domain-check");
const targets = [
  "https://yunxifood.cn/health",
  "https://yunxifood.cn",
];

async function checkTarget(url) {
  const startedAt = Date.now();
  try {
    const response = await fetch(url, { method: "GET" });
    const body = await response.text();
    return {
      url,
      ok: response.ok,
      status: response.status,
      durationMs: Date.now() - startedAt,
      bodyHead: body.slice(0, 300),
      error: "",
    };
  } catch (error) {
    return {
      url,
      ok: false,
      status: 0,
      durationMs: Date.now() - startedAt,
      bodyHead: "",
      error: String(error?.message || error),
      cause: error?.cause ? String(error.cause?.message || error.cause) : "",
    };
  }
}

async function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const checks = [];
  for (const target of targets) {
    checks.push(await checkTarget(target));
  }
  const report = {
    traceId: "20260617-production-domain-check",
    generatedAt: new Date().toISOString(),
    status: checks.every((item) => item.ok) ? "pass" : "fail",
    checks,
  };
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
  const reportPath = path.join(reportsRoot, `domain-check-${stamp}.json`);
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "latest.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(`Domain check ${report.status}: ${targets.join(", ")}`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
