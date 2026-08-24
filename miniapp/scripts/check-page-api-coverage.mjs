import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const miniappRoot = path.join(root, "miniprogram");
const appJsonPath = path.join(miniappRoot, "app.json");
const apiContractPath = path.join(root, "docs", "api-contract.md");
const pageApiCoveragePath = path.join(root, "docs", "page-api-coverage.md");
const servicesRoot = path.join(miniappRoot, "services");

const requiredPages = [
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
  "pages/recharge/index",
];

const requiredCoverageTerms = [
  "GET /api/v1/miniapp/pages/{pageId}",
  "GET /api/v1/miniapp/pages/home",
  "GET /api/v1/miniapp/pages/products",
  "GET /api/v1/miniapp/pages/profile",
  "GET /api/v1/miniapp/products",
  "GET /api/v1/miniapp/products/{productId}",
  "GET /api/v1/miniapp/product-categories",
  "GET /api/v1/miniapp/addresses",
  "POST /api/v1/miniapp/addresses",
  "POST /api/v1/miniapp/addresses/{addressId}/default",
  "DELETE /api/v1/miniapp/addresses/{addressId}",
  "POST /api/v1/miniapp/orders",
  "GET /api/v1/miniapp/orders",
  "GET /api/v1/miniapp/orders/{orderId}",
  "POST /api/v1/miniapp/orders/{orderId}/cancel",
  "POST /api/v1/miniapp/orders/{orderId}/prepare-payment",
  "POST /api/v1/miniapp/orders/{orderId}/mock-pay",
  "GET /api/v1/miniapp/chat/messages",
  "POST /api/v1/miniapp/chat/messages",
  "POST /api/v1/miniapp/chat/transfer",
  "POST /api/v1/miniapp/group-registrations",
  "GET /api/v1/miniapp/group-registrations/me",
  "GET /api/v1/miniapp/shop-settings",
  "POST /api/v1/miniapp/auth/login",
  "GET /api/v1/miniapp/balance",
  "GET /api/v1/miniapp/points",
  "GET /api/v1/miniapp/coupons",
  "GET /api/v1/miniapp/recharges",
  "POST /api/v1/miniapp/recharges",
  "POST /api/v1/miniapp/orders/{orderId}/apply-coupon",
  "POST /api/v1/miniapp/orders/{orderId}/apply-points",
  "POST /api/v1/miniapp/orders/{orderId}/pay-with-balance",
  "POST /api/v1/miniapp/orders/{orderId}/prepare-combined-payment",
];

const requiredApiContractTerms = [
  "/api/v1/miniapp/pages/{pageId}",
  "/api/v1/miniapp/products",
  "/api/v1/miniapp/products/{productId}",
  "/api/v1/miniapp/product-categories",
  "/api/v1/miniapp/addresses",
  "/api/v1/miniapp/orders",
  "/api/v1/miniapp/chat/messages",
  "/api/v1/miniapp/chat/transfer",
  "/api/v1/miniapp/group-registrations",
  "/api/v1/miniapp/group-registrations/me",
  "/api/v1/miniapp/shop-settings",
  "/api/v1/miniapp/auth/login",
];

const requiredServiceTerms = [
  "/api/v1/miniapp/pages/",
  "/api/v1/miniapp/products",
  "/api/v1/miniapp/product-categories",
  "/api/v1/miniapp/addresses",
  "/api/v1/miniapp/orders",
  "/api/v1/miniapp/chat/messages",
  "/api/v1/miniapp/chat/transfer",
  "/api/v1/miniapp/group-registrations",
  "/api/v1/miniapp/shop-settings",
  "/api/v1/miniapp/auth/login",
];

const requiredBoundaryTerms = [
  "不在本仓实现会员权益计算",
  "不在本仓实现积分、储值余额或优惠券账本",
  "不在本仓实现配送费、满减或活动价规则",
  "不在本仓实现商品价格、库存或分类真相",
  "不在本仓实现订单状态机",
  "不把 mock-pay 当作正式微信支付闭环",
  "不在本仓解析企业微信群身份或生成活动归因真相",
  "接口缺口先回 Platform 定义 API 契约",
];

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function readJson(filePath) {
  return JSON.parse(readText(filePath));
}

function collectFiles(dirPath, extension) {
  const files = [];
  for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
    const entryPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFiles(entryPath, extension));
    } else if (entry.name.endsWith(extension)) {
      files.push(entryPath);
    }
  }
  return files;
}

function expectIncludes(source, terms, label, failures) {
  for (const term of terms) {
    if (!source.includes(term)) {
      failures.push(`${label} missing required term: ${term}`);
    }
  }
}

const failures = [];
const appConfig = readJson(appJsonPath);
const appPages = appConfig.pages ?? [];
const pageCoverage = readText(pageApiCoveragePath);
const apiContract = readText(apiContractPath);
const serviceSource = collectFiles(servicesRoot, ".ts").map(readText).join("\n");

for (const page of requiredPages) {
  if (!appPages.includes(page)) {
    failures.push(`miniprogram/app.json missing required page: ${page}`);
  }
}

for (const page of appPages) {
  if (!pageCoverage.includes(page)) {
    failures.push(`docs/page-api-coverage.md missing app.json page: ${page}`);
  }
}

expectIncludes(pageCoverage, requiredCoverageTerms, "docs/page-api-coverage.md", failures);
expectIncludes(pageCoverage, requiredBoundaryTerms, "docs/page-api-coverage.md", failures);
expectIncludes(apiContract, requiredApiContractTerms, "docs/api-contract.md", failures);
expectIncludes(serviceSource, requiredServiceTerms, "miniprogram/services", failures);

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join("\n"));
  process.exit(1);
}

console.log(
  `Miniapp page API coverage passed: ${appPages.length} pages, ${requiredCoverageTerms.length} API terms, ${requiredBoundaryTerms.length} boundaries.`,
);
