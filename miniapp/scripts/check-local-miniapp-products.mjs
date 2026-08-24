import fs from "node:fs";
import path from "node:path";

const baseUrl = process.env.LOCAL_MINIAPP_API_BASE_URL || "http://127.0.0.1:7001";
const reportsRoot = path.join(process.cwd(), "reports", "local-miniapp-products");

async function readJson(pathname) {
  const startedAt = Date.now();
  const url = `${baseUrl}${pathname}`;
  const response = await fetch(url);
  const body = await response.text();
  let parsed = null;
  let parseError = "";
  try {
    parsed = JSON.parse(body);
  } catch (error) {
    parseError = String(error?.message || error);
  }
  return {
    url,
    status: response.status,
    ok: response.ok && parseError === "",
    durationMs: Date.now() - startedAt,
    parsed,
    bodyHead: body.slice(0, 500),
    error: parseError,
  };
}

async function checkImage(pathname) {
  const startedAt = Date.now();
  const url = `${baseUrl}${pathname}`;
  const response = await fetch(url);
  const contentType = response.headers.get("content-type") || "";
  const body = await response.arrayBuffer();
  return {
    url,
    status: response.status,
    ok: response.ok && contentType.startsWith("image/") && body.byteLength > 0,
    contentType,
    size: body.byteLength,
    durationMs: Date.now() - startedAt,
  };
}

function summarizeProduct(product) {
  return {
    id: product?.id || "",
    title: product?.title || "",
    priceFen: product?.priceFen ?? null,
    stock: product?.stock ?? null,
    isActive: product?.isActive ?? null,
    imageUrl: product?.imageUrl || "",
  };
}

function normalizeDisplayText(value) {
  return String(value || "").trim().replace(/\s+/g, "").toLocaleLowerCase();
}

function getDisplayDedupKey(product) {
  return [
    normalizeDisplayText(product?.title),
    product?.priceFen ?? "",
  ].join("|");
}

function findDisplayDuplicates(products) {
  const byKey = new Map();
  for (const product of products) {
    const key = getDisplayDedupKey(product);
    if (!byKey.has(key)) {
      byKey.set(key, []);
    }
    byKey.get(key).push(summarizeProduct(product));
  }
  return Array.from(byKey.entries())
    .filter(([, items]) => items.length > 1)
    .map(([key, items]) => ({ key, count: items.length, items }));
}

async function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });

  const listCheck = await readJson("/api/v1/miniapp/products");
  const products = Array.isArray(listCheck.parsed?.data) ? listCheck.parsed.data : [];
  const categoriesCheck = await readJson("/api/v1/miniapp/product-categories");
  const categories = Array.isArray(categoriesCheck.parsed?.data) ? categoriesCheck.parsed.data : [];
  const firstCategory = categories[0] || null;
  const categoryProductsCheck = firstCategory?.id
    ? await readJson(`/api/v1/miniapp/products?categoryId=${encodeURIComponent(firstCategory.id)}`)
    : null;
  const categoryProducts = Array.isArray(categoryProductsCheck?.parsed?.data)
    ? categoryProductsCheck.parsed.data
    : [];
  const displayDuplicates = findDisplayDuplicates(products);
  const firstProduct = products[0] || null;
  const detailCheck = firstProduct?.id
    ? await readJson(`/api/v1/miniapp/products/${encodeURIComponent(firstProduct.id)}`)
    : null;
  const detailProduct = detailCheck?.parsed?.data || null;
  const imagePath = detailProduct?.imageUrl || firstProduct?.imageUrl || "";
  const imageCheck = imagePath ? await checkImage(imagePath) : null;

  const checks = [
    {
      name: "local product list",
      ok: listCheck.ok && listCheck.parsed?.code === 0 && products.length > 0,
      status: listCheck.status,
      durationMs: listCheck.durationMs,
      count: products.length,
      sample: summarizeProduct(firstProduct),
      error: listCheck.error,
    },
    {
      name: "local product categories",
      ok: categoriesCheck.ok
        && categoriesCheck.parsed?.code === 0
        && categories.length > 0
        && categories.every((category) => !String(category.title || "").startsWith("有赞分组 ")),
      status: categoriesCheck.status,
      durationMs: categoriesCheck.durationMs,
      count: categories.length,
      sample: firstCategory,
      leakedFallbackTitles: categories
        .filter((category) => String(category.title || "").startsWith("有赞分组 "))
        .slice(0, 10),
      error: categoriesCheck.error,
    },
    {
      name: "local products filtered by category",
      ok: Boolean(
        firstCategory
          && categoryProductsCheck?.ok
          && categoryProductsCheck.parsed?.code === 0
          && categoryProducts.length > 0
          && categoryProducts.every((product) => product.categoryId === firstCategory.id)
      ),
      status: categoryProductsCheck?.status ?? 0,
      durationMs: categoryProductsCheck?.durationMs ?? 0,
      count: categoryProducts.length,
      category: firstCategory,
      sample: summarizeProduct(categoryProducts[0]),
      error: categoryProductsCheck?.error || "",
    },
    {
      name: "local product detail",
      ok: Boolean(
        detailCheck?.ok
          && detailCheck.parsed?.code === 0
          && detailProduct
          && detailProduct.id === firstProduct?.id
      ),
      status: detailCheck?.status ?? 0,
      durationMs: detailCheck?.durationMs ?? 0,
      sample: summarizeProduct(detailProduct),
      error: detailCheck?.error || "",
    },
    {
      name: "local product image proxy",
      ok: imageCheck === null || imageCheck.ok,
      status: imageCheck?.status ?? 0,
      durationMs: imageCheck?.durationMs ?? 0,
      contentType: imageCheck?.contentType || "",
      size: imageCheck?.size ?? 0,
      skipped: imageCheck === null,
    },
    {
      name: "local product display duplicates",
      ok: true,
      warning: displayDuplicates.length > 0
        ? "API returned display-duplicate products; miniapp service should dedupe them before rendering."
        : "",
      duplicateGroupCount: displayDuplicates.length,
      samples: displayDuplicates.slice(0, 10),
    },
  ];

  const report = {
    traceId: "20260618-local-real-products-link",
    generatedAt: new Date().toISOString(),
    baseUrl,
    status: checks.every((item) => item.ok) ? "pass" : "fail",
    checks,
  };
  const stamp = new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
  const reportPath = path.join(reportsRoot, `local-miniapp-products-${stamp}.json`);
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "latest.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");

  console.log(`Local miniapp products ${report.status}: ${baseUrl}`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
