/**
 * Phase C 第二步：15 页面实机走查 v2。
 * 每个操作带独立超时，单页失败不阻塞后续页面。
 */
import automator from "miniprogram-automator";
import fs from "node:fs";

const WS = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const OP_TIMEOUT = Number(process.env.OP_TIMEOUT || 12000);

const PAGES = [
  "pages/home/index",
  "pages/products/index",
  "pages/product-detail/index",
  "pages/cart/index",
  "pages/checkout/index",
  "pages/policy/index",
  "pages/address/index",
  "pages/orders/index",
  "pages/order-detail/index",
  "pages/group-registration/index",
  "pages/chat/index",
  "pages/profile/index",
  "pages/points/index",
  "pages/coupons/index",
  "pages/recharge/index"
];

const consoleErrors = [];
const report = [];

function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`${label} timeout ${ms}ms`)), ms)
    )
  ]);
}

async function safe(fn, label, fallback = null) {
  try {
    return await withTimeout(fn(), OP_TIMEOUT, label);
  } catch (e) {
    return { __failed: true, message: `${label}: ${String(e.message || e).slice(0, 120)}`, fallback };
  }
}

function summarize(page, data) {
  if (!data || typeof data !== "object") return "";
  const out = {};
  for (const k of Object.keys(data)) {
    const v = data[k];
    if (Array.isArray(v)) out[k] = `array(${v.length})`;
    else if (typeof v === "object" && v !== null) continue;
    else out[k] = String(v).slice(0, 36);
  }
  if (page === "pages/product-detail/index") {
    out.productTitle = String(data.product?.title ?? "").slice(0, 30);
    out.unavailableText = String(data.unavailableText ?? "");
  }
  if (page === "pages/home/index" || page === "pages/products/index") {
    for (const [k, v] of Object.entries(data)) {
      if (Array.isArray(v) && v.length > 0 && typeof v[0] === "object") {
        const f = v[0];
        out.sampleTitle = String(f.title ?? f.name ?? "").slice(0, 28);
        out.samplePrice = String(f.priceText ?? f.priceFen ?? "");
        break;
      }
    }
  }
  return JSON.stringify(out).slice(0, 380);
}

async function main() {
  console.log(`connecting ${WS}`);
  const miniProgram = await withTimeout(
    automator.connect({ wsEndpoint: WS }),
    30000,
    "connect"
  );
  console.log("connected");

  miniProgram.on("console", (msg) => {
    if (msg.type === "error" || msg.type === "warn") {
      const args = (msg.args || [])
        .map((a) => (typeof a === "string" ? a : JSON.stringify(a)))
        .join(" ");
      consoleErrors.push(`${msg.type}: ${args}`.slice(0, 200));
    }
  });
  miniProgram.on("exception", (exp) => {
    consoleErrors.push(`exception: ${exp.message}`.slice(0, 200));
  });

  await safe(
    () => miniProgram.callWxMethod("setStorageSync", "yunxiUseLocalApi", true),
    "setStorage"
  );

  for (const page of PAGES) {
    const entry = { page, navigated: false, errors: [], dataSnapshot: "" };
    const t0 = Date.now();

    const nav = await safe(() => miniProgram.reLaunch(`/${page}`), `reLaunch ${page}`);
    entry.navigated = !nav?.__failed;
    if (nav?.__failed) entry.errors.push(nav.message);

    await sleep(2200);

    const cur = await safe(() => miniProgram.currentPage(), "currentPage");
    entry.currentPage = cur && !cur.__failed ? cur.path : "(fail)";

    const data = await safe(() => (cur && !cur.__failed ? cur.data() : null), "pageData");
    entry.dataSnapshot =
      data && !data.__failed ? summarize(page, data) : data?.message ?? "";

    // 页面级报错从全局 console 流里取本时间窗新增
    shot: {
      const r = await safe(
        () => miniProgram.screenshot({ path: `reports/devtools/wt-${page.split("/")[1]}.png` }),
        "screenshot"
      );
      if (r?.__failed) entry.errors.push(r.message);
    }

    entry.elapsedMs = Date.now() - t0;
    report.push(entry);
    console.log(
      `${entry.navigated ? "OK " : "FAIL"} ${page} (${entry.elapsedMs}ms) ${
        entry.errors.join("; ")
      } ${entry.dataSnapshot}`
    );
  }

  fs.mkdirSync("reports/devtools", { recursive: true });
  fs.writeFileSync(
    "reports/devtools/walkthrough-phase-c.json",
    JSON.stringify(
      { generatedAt: new Date().toISOString(), pages: report, consoleErrors: consoleErrors.slice(-100) },
      null,
      2
    )
  );
  console.log(`\ndone. report written. console warn/error total: ${consoleErrors.length}`);

  await safe(() => miniProgram.disconnect(), "disconnect");
  process.exit(0);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

main().catch((e) => {
  console.error("walkthrough fatal:", e.message);
  process.exit(1);
});
