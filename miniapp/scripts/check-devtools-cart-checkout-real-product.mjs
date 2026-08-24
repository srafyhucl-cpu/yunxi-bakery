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

async function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const miniProgram = await automator.connect({ wsEndpoint });
  let runtimeResult;
  try {
    runtimeResult = await miniProgram.evaluate(async function () {
      const apiBaseUrl = "https://yunxifood.cn";
      const originalCartItems = wx.getStorageSync("cartItems");
      const originalMiniappSession = wx.getStorageSync("miniappSession");
      const originalMiniappUserId = wx.getStorageSync("miniappUserId");
      const originalUseLocalApi = wx.getStorageSync("yunxiUseLocalApi");

      function sleep(ms) {
        return new Promise(function (resolve) {
          setTimeout(resolve, ms);
        });
      }

      function loginWithWechat() {
        return new Promise(function (resolve, reject) {
          wx.login({
            success: function (loginResponse) {
              if (!loginResponse.code) {
                reject(new Error("wx.login returned no code"));
                return;
              }
              wx.request({
                url: apiBaseUrl + "/api/v1/miniapp/auth/login",
                method: "POST",
                data: { code: loginResponse.code },
                timeout: 10000,
                header: { "content-type": "application/json" },
                success: function (response) {
                  const body = response.data && typeof response.data === "object" ? response.data : {};
                  const payload = body.data && typeof body.data === "object" ? body.data : body;
                  const expiresIn = Number(payload.expiresIn);
                  if (
                    response.statusCode < 200 ||
                    response.statusCode >= 300 ||
                    typeof payload.accessToken !== "string" ||
                    !payload.accessToken ||
                    payload.tokenType !== "Bearer" ||
                    !Number.isFinite(expiresIn) ||
                    expiresIn <= 0
                  ) {
                    reject(new Error("miniapp auth login returned an invalid session"));
                    return;
                  }
                  resolve({
                    userId: typeof payload.userId === "string" ? payload.userId : "",
                    openid: typeof payload.openid === "string" ? payload.openid : "",
                    accessToken: payload.accessToken,
                    tokenType: "Bearer",
                    expiresIn: expiresIn,
                    expiresAt: Date.now() + expiresIn * 1000,
                  });
                },
                fail: function (error) {
                  reject(new Error(error.errMsg || "miniapp auth request failed"));
                },
              });
            },
            fail: function (error) {
              reject(new Error(error.errMsg || "wx.login failed"));
            },
          });
        });
      }

      const session = await loginWithWechat();

      function requestJson(path) {
        return new Promise(function (resolve, reject) {
          wx.request({
            url: apiBaseUrl + path,
            method: "GET",
            timeout: 10000,
            header: {
              "content-type": "application/json",
              Authorization: session.tokenType + " " + session.accessToken,
            },
            success: function (response) {
              if (response.statusCode >= 200 && response.statusCode < 300) {
                resolve(response.data);
                return;
              }
              reject(new Error("HTTP " + response.statusCode));
            },
            fail: function (error) {
              reject(new Error(error.errMsg || "wx.request failed"));
            },
          });
        });
      }

      async function waitForPage(route, timeoutMs) {
        const startedAt = Date.now();
        while (Date.now() - startedAt < timeoutMs) {
          const pages = getCurrentPages();
          const page = pages[pages.length - 1];
          if (page && page.route === route) {
            return page;
          }
          await sleep(200);
        }
        throw new Error("Timed out waiting for " + route);
      }

      function pickPurchasableProduct(products) {
        return products.find(function (product) {
          return product && product.id && product.isActive && product.stock > 0;
        });
      }

      wx.setStorageSync("miniappSession", session);
      wx.setStorageSync("miniappUserId", session.userId);
      wx.removeStorageSync("yunxiUseLocalApi");

      try {
        const listPayload = await requestJson("/api/v1/miniapp/products");
        const products = Array.isArray(listPayload.data) ? listPayload.data : [];
        const product = pickPurchasableProduct(products);
        if (!product) {
          throw new Error("No purchasable product returned from miniapp products API");
        }
        const cartItem = {
          productId: product.id,
          title: product.title,
          imageUrl: product.imageUrl
            ? apiBaseUrl + (product.imageUrl.indexOf("/") === 0 ? "" : "/") + product.imageUrl
            : "",
          priceFen: product.priceFen,
          quantity: 1,
        };
        wx.setStorageSync("cartItems", [cartItem]);

        await new Promise(function (resolve) {
          wx.switchTab({
            url: "/pages/cart/index",
            complete: resolve,
          });
        });
        const cartPage = await waitForPage("pages/cart/index", 10000);
        await sleep(1500);
        if (typeof cartPage.onShow === "function") {
          cartPage.onShow();
          await sleep(500);
        }
        const cartDataBeforeCheckout = cartPage.data;
        cartPage.checkout();
        await sleep(1500);
        const checkoutPage = await waitForPage("pages/checkout/index", 10000);
        await sleep(1500);
        const checkoutData = checkoutPage.data;
        const cartItems = wx.getStorageSync("cartItems");

        return {
          apiBaseUrl: apiBaseUrl,
          selectedProduct: {
            id: product.id,
            title: product.title,
            priceFen: product.priceFen,
            stock: product.stock,
            isActive: product.isActive,
          },
          cartBeforeCheckout: {
            route: cartPage.route,
            hasItems: Boolean(cartDataBeforeCheckout.hasItems),
            itemCount: Array.isArray(cartDataBeforeCheckout.items)
              ? cartDataBeforeCheckout.items.length
              : 0,
            totalText: cartDataBeforeCheckout.totalText,
            firstItem: Array.isArray(cartDataBeforeCheckout.items)
              ? cartDataBeforeCheckout.items[0]
              : undefined,
          },
          checkout: {
            route: checkoutPage.route,
            totalText: checkoutData.totalText,
            selectedAddressText: checkoutData.selectedAddressText,
            submitting: Boolean(checkoutData.submitting),
            errorMessage: checkoutData.errorMessage || "",
          },
          cartItems: cartItems,
          storageDuringCheck: {
            session: {
              hasAccessToken: Boolean(session.accessToken),
              tokenType: session.tokenType,
              expiresIn: session.expiresIn,
            },
            hasMiniappUserIdStorage: Boolean(wx.getStorageSync("miniappUserId")),
            usesLocalApi: Boolean(wx.getStorageSync("yunxiUseLocalApi")),
          },
        };
      } finally {
        wx.setStorageSync("cartItems", Array.isArray(originalCartItems) ? originalCartItems : []);
        if (originalMiniappSession) {
          wx.setStorageSync("miniappSession", originalMiniappSession);
        } else {
          wx.removeStorageSync("miniappSession");
        }
        if (originalMiniappUserId) {
          wx.setStorageSync("miniappUserId", originalMiniappUserId);
        } else {
          wx.removeStorageSync("miniappUserId");
        }
        if (originalUseLocalApi) {
          wx.setStorageSync("yunxiUseLocalApi", originalUseLocalApi);
        } else {
          wx.removeStorageSync("yunxiUseLocalApi");
        }
      }
    });
  } finally {
    await miniProgram.disconnect();
  }

  const cartItems = Array.isArray(runtimeResult.cartItems) ? runtimeResult.cartItems : [];
  const selectedProduct = runtimeResult.selectedProduct;
  const firstCartItem = cartItems[0];
  const checks = [
    {
      name: "cart loaded selected real product",
      ok:
        runtimeResult.cartBeforeCheckout.route === "pages/cart/index" &&
        runtimeResult.cartBeforeCheckout.hasItems &&
        runtimeResult.cartBeforeCheckout.itemCount === 1 &&
        runtimeResult.cartBeforeCheckout.firstItem?.productId === selectedProduct.id,
    },
    {
      name: "cart checkout navigated to checkout",
      ok: runtimeResult.checkout.route === "pages/checkout/index",
    },
    {
      name: "checkout total matches selected product",
      ok: runtimeResult.checkout.totalText === `¥${(selectedProduct.priceFen / 100).toFixed(2)}`,
    },
    {
      name: "cart still contains selected product once",
      ok:
        cartItems.length === 1 &&
        firstCartItem.productId === selectedProduct.id &&
        firstCartItem.quantity === 1,
    },
    {
      name: "checkout is idle without error",
      ok: !runtimeResult.checkout.submitting && !runtimeResult.checkout.errorMessage,
    },
  ];

  const report = {
    traceId: "20260621-real-cart-checkout-runtime",
    generatedAt: new Date().toISOString(),
    wsEndpoint,
    apiBaseUrl: runtimeResult.apiBaseUrl,
    status: checks.every((check) => check.ok) ? "pass" : "fail",
    checks,
    result: runtimeResult,
    notes: [
      "This runtime check uses a real product from the production miniapp product list.",
      "It verifies the cart page checkout action navigates into checkout and restores the previous local cart.",
      "It does not create an order or trigger payment.",
    ],
  };

  const stamp = nowStamp();
  const reportPath = path.join(reportsRoot, `real-cart-checkout-${stamp}.json`);
  const payload = `${JSON.stringify(report, null, 2)}\n`;
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "real-cart-checkout-latest.json"), payload, "utf8");
  console.log(`Real cart checkout runtime ${report.status}: ${selectedProduct.id}`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
