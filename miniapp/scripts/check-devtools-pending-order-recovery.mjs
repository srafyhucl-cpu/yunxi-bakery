import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import automator from "miniprogram-automator";

const TRACE_ID = "20260925-miniapp-core-loop-candidate-review";
const RUN_ID = "20260925-miniapp-core-loop-candidate-review-r1";
const LOCAL_API_BASE_URL = "http://127.0.0.1:7001";
const AUTOMATOR_WS_ENDPOINT = "ws://127.0.0.1:9420";
const HEALTH_TIMEOUT_MS = 5_000;
const PAGE_WAIT_TIMEOUT_MS = 15_000;
const EXPECTED_PICKUP_ADDRESS = "北京市东城区南竹杆胡同2号银河SOHO";
const TEST_EXPECT_TIME = "2099-01-02 18:00";
const root = process.cwd();
const reportsRoot = path.join(root, "reports", "button-runtime");
const runtimeStateKey = "__yunxiPendingOrderRecoveryTestState";

function nowStamp() {
  return new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
}

function safeError(error) {
  const message = error instanceof Error ? error.message : String(error);
  return message
    .replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer <redacted>")
    .replace(/1\d{10}/g, "1**********")
    .slice(0, 500);
}

function shortOrderId(orderId) {
  const value = String(orderId || "");
  return value.length <= 12 ? value : `${value.slice(0, 6)}...${value.slice(-4)}`;
}

function isBlockedError(error) {
  return /BLOCKED:|timeout waiting for automator response|Connection closed|ECONNREFUSED|ETIMEDOUT/.test(
    safeError(error)
  );
}

function addError(report, stage, error) {
  report.errors.push({ stage, message: safeError(error) });
}

function probeLocalHealth() {
  return new Promise((resolve, reject) => {
    const request = http.request(
      `${LOCAL_API_BASE_URL}/health`,
      { method: "GET", timeout: HEALTH_TIMEOUT_MS },
      (response) => {
        response.resume();
        if (response.statusCode && response.statusCode >= 200 && response.statusCode < 300) {
          resolve({ ok: true, statusCode: response.statusCode });
          return;
        }
        reject(new Error(`本地后端健康检查返回 HTTP ${response.statusCode || 0}`));
      }
    );
    request.on("timeout", () => {
      const timeoutError = new Error(`本地后端健康检查超时（${HEALTH_TIMEOUT_MS}ms）`);
      timeoutError.code = "ETIMEDOUT";
      request.destroy(timeoutError);
    });
    request.on("error", reject);
    request.end();
  });
}

function requestLocalJson(requestPath, accessToken) {
  return new Promise((resolve, reject) => {
    const request = http.request(
      `${LOCAL_API_BASE_URL}${requestPath}`,
      {
        method: "GET",
        timeout: 10_000,
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
      },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          body += chunk;
        });
        response.on("end", () => {
          if (!response.statusCode || response.statusCode < 200 || response.statusCode >= 300) {
            reject(new Error(`本地 API 返回 HTTP ${response.statusCode || 0}: ${requestPath}`));
            return;
          }
          try {
            resolve(JSON.parse(body));
          } catch {
            reject(new Error(`本地 API 返回无效 JSON: ${requestPath}`));
          }
        });
      }
    );
    request.on("timeout", () => {
      const timeoutError = new Error(`本地 API 请求超时: ${requestPath}`);
      timeoutError.code = "ETIMEDOUT";
      request.destroy(timeoutError);
    });
    request.on("error", reject);
    request.end();
  });
}

async function connectAutomator() {
  return Promise.race([
    automator.connect({ wsEndpoint: AUTOMATOR_WS_ENDPOINT }),
    new Promise((_, reject) => {
      setTimeout(
        () => reject(new Error("DevTools Automator 连接超时（8000ms）")),
        8_000
      );
    }),
  ]);
}

async function setupRuntime(miniProgram) {
  const login = await miniProgram.evaluate(async function (apiBaseUrl) {
    const storageKeys = [
      "cartItems",
      "miniappSession",
      "miniappUserId",
      "yunxiPendingOrder",
      "yunxiUseLocalApi",
    ];

    function snapshotStorage() {
      const existingKeys = wx.getStorageInfoSync().keys || [];
      const snapshot = {};
      storageKeys.forEach(function (key) {
        snapshot[key] = {
          exists: existingKeys.indexOf(key) !== -1,
          value: wx.getStorageSync(key),
        };
      });
      return snapshot;
    }

    function loginWithWechat() {
      return new Promise(function (resolve, reject) {
        wx.login({
          success: function (loginResult) {
            if (!loginResult.code) {
              reject(new Error("BLOCKED: wx.login 未返回 code"));
              return;
            }
            wx.request({
              url: apiBaseUrl + "/api/v1/miniapp/auth/login",
              method: "POST",
              data: { code: loginResult.code },
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
                  reject(new Error("BLOCKED: 本地登录接口未返回有效 Bearer 会话"));
                  return;
                }
                resolve({
                  userId: String(payload.userId || ""),
                  openid: String(payload.openid || ""),
                  sessionReady: true,
                  isDemo: false,
                  accessToken: payload.accessToken,
                  tokenType: "Bearer",
                  expiresIn: expiresIn,
                  expiresAt: Date.now() + expiresIn * 1000,
                });
              },
              fail: function (error) {
                reject(new Error("BLOCKED: 本地登录请求失败：" + (error.errMsg || "未知错误")));
              },
            });
          },
          fail: function (error) {
            reject(new Error("BLOCKED: wx.login 失败：" + (error.errMsg || "未知错误")));
          },
        });
      });
    }

    const accountInfo = wx.getAccountInfoSync();
    if (accountInfo.miniProgram.envVersion !== "develop") {
      throw new Error("BLOCKED: 待支付恢复测试只允许在 develop 环境运行");
    }
    const storedLocalApi = wx.getStorageSync("yunxiUseLocalApi");
    if (storedLocalApi === false || storedLocalApi === "false") {
      throw new Error("BLOCKED: DevTools 当前以生产 API 启动，无法执行本地订单复现");
    }

    const session = await loginWithWechat();
    globalThis.__yunxiPendingOrderRecoveryTestState = {
      storageSnapshot: snapshotStorage(),
      session: session,
    };
    wx.setStorageSync("yunxiUseLocalApi", true);
    wx.setStorageSync("miniappSession", session);
    wx.setStorageSync("miniappUserId", session.userId);
    wx.removeStorageSync("yunxiPendingOrder");
    return {
      envVersion: accountInfo.miniProgram.envVersion,
      session: session,
    };
  }, LOCAL_API_BASE_URL);

  const productPayload = await requestLocalJson(
    "/api/v1/miniapp/products?limit=100",
    login.session.accessToken
  );
  const products = Array.isArray(productPayload.data) ? productPayload.data : [];
  const selectedProducts = products
    .filter(
      (item) =>
        item &&
        item.id &&
        item.isActive === true &&
        item.isPurchasable !== false &&
        Number(item.stock) >= 2 &&
        Number(item.priceFen) > 0
    )
    .slice(0, 2)
    .map((item) => ({
      id: String(item.id),
      title: String(item.title || item.id),
      imageUrl: String(item.imageUrl || ""),
      priceFen: Number(item.priceFen),
      stock: Number(item.stock),
    }));
  if (selectedProducts.length < 2) {
    throw new Error("BLOCKED: 本地测试需要至少两个在售、可购买且库存不少于 2 件的商品");
  }
  await miniProgram.evaluate(function (products) {
    if (!globalThis.__yunxiPendingOrderRecoveryTestState) {
      throw new Error("待支付恢复测试运行态已丢失");
    }
    globalThis.__yunxiPendingOrderRecoveryTestState.products = products;
  }, selectedProducts);
  return {
    envVersion: login.envVersion,
    session: {
      hasAccessToken: true,
      tokenType: login.session.tokenType,
      expiresIn: login.session.expiresIn,
    },
    products: selectedProducts.map((product) => ({
      id: product.id,
      priceFen: product.priceFen,
      stock: product.stock,
    })),
  };
}

async function openCheckoutForProduct(miniProgram, productIndex, scenario) {
  return miniProgram.evaluate(async function (options) {
    const state = globalThis.__yunxiPendingOrderRecoveryTestState;
    const product = state.products[options.productIndex];
    const scenario = options.scenario;
    if (!state || !product) {
      throw new Error("待支付恢复测试商品未初始化");
    }

    function sleep(milliseconds) {
      return new Promise(function (resolve) {
        setTimeout(resolve, milliseconds);
      });
    }

    function waitFor(predicate, timeoutMilliseconds, message) {
      return new Promise(function (resolve, reject) {
        const startedAt = Date.now();
        const timer = setInterval(function () {
          if (predicate()) {
            clearInterval(timer);
            resolve();
            return;
          }
          if (Date.now() - startedAt >= timeoutMilliseconds) {
            clearInterval(timer);
            reject(new Error(message));
          }
        }, 100);
      });
    }

    async function waitForCheckoutPage(timeoutMilliseconds) {
      return new Promise(function (resolve, reject) {
        const startedAt = Date.now();
        const timer = setInterval(function () {
          const pages = getCurrentPages();
          const page = pages[pages.length - 1];
          if (page && page.route === "pages/checkout/index") {
            clearInterval(timer);
            resolve(page);
            return;
          }
          if (Date.now() - startedAt >= timeoutMilliseconds) {
            clearInterval(timer);
            reject(new Error("等待结算页超时"));
          }
        }, 100);
      });
    }

    function relaunchCart() {
      return new Promise(function (resolve, reject) {
        wx.reLaunch({
          url: "/pages/cart/index",
          success: resolve,
          fail: function (error) {
            reject(new Error(error.errMsg || "重载购物车失败"));
          },
        });
      });
    }

    function setPageData(page, values) {
      return new Promise(function (resolve) {
        page.setData(values, resolve);
      });
    }

    const cartItem = {
      productId: product.id,
      title: product.title,
      imageUrl: product.imageUrl,
      priceFen: product.priceFen,
      quantity: 1,
      stock: product.stock,
    };
    wx.setStorageSync("cartItems", [cartItem]);
    if (!scenario.preservePendingOrder) {
      wx.removeStorageSync("yunxiPendingOrder");
    }
    const app = getApp();
    app.globalData.cartItems = [cartItem];
    await relaunchCart();
    await sleep(250);
    const pages = getCurrentPages();
    const cartPage = pages[pages.length - 1];
    await waitFor(
      function () {
        return cartPage.data && cartPage.data.hasItems === true;
      },
      options.pageWaitTimeoutMs,
      "购物车未加载复现商品"
    );
    cartPage.checkout();
    const checkoutPage = await waitForCheckoutPage(options.pageWaitTimeoutMs);
    await waitFor(
      function () {
        return (
          checkoutPage.data &&
          checkoutPage.data.isLoggedIn === true &&
          Array.isArray(checkoutPage.data.checkoutItems) &&
          checkoutPage.data.checkoutItems.length === 1
        );
      },
      options.pageWaitTimeoutMs,
      "结算页未加载复现商品"
    );
    await setPageData(checkoutPage, {
      receiverName: scenario.receiverName,
      receiverPhone: scenario.receiverPhone,
      deliveryType: "pickup",
      deliveryAddress: "",
      remark: scenario.remark,
      pickupAddress: options.expectedPickupAddress,
      agreementAccepted: true,
      expectTime: options.testExpectTime,
      isLoggedIn: true,
      selectedCouponId: "",
      pointsEnabled: false,
      balanceEnabled: false,
      pendingOrderId: "",
      pendingBarVisible: false,
      orderLocked: false,
      errorMessage: "",
    });
    if (typeof checkoutPage.refreshEstimate === "function") {
      checkoutPage.refreshEstimate();
    }
    if (typeof checkoutPage.refreshSubmitState === "function") {
      checkoutPage.refreshSubmitState();
    }
    await sleep(100);
    return {
      productId: product.id,
      productTitle: product.title,
      receiverName: scenario.receiverName,
      receiverPhoneSuffix: scenario.receiverPhone.slice(-4),
      remark: scenario.remark,
    };
  }, {
    expectedPickupAddress: EXPECTED_PICKUP_ADDRESS,
    pageWaitTimeoutMs: PAGE_WAIT_TIMEOUT_MS,
    productIndex,
    scenario,
    testExpectTime: TEST_EXPECT_TIME,
  });
}

async function createPendingOrder(miniProgram) {
  return miniProgram.evaluate(async function (options) {
    function sleep(milliseconds) {
      return new Promise(function (resolve) {
        setTimeout(resolve, milliseconds);
      });
    }

    const pages = getCurrentPages();
    const checkoutPage = pages[pages.length - 1];
    if (!checkoutPage || checkoutPage.route !== "pages/checkout/index") {
      throw new Error("创建待支付订单时当前页面不是结算页");
    }
    await checkoutPage.submitOrder();
    await sleep(500);
    const pending = wx.getStorageSync("yunxiPendingOrder");
    if (!pending || !pending.orderId) {
      throw new Error("取消支付后未生成待支付订单");
    }
    await checkoutPage.loadCheckout();
    await sleep(200);
    return {
      orderId: String(pending.orderId),
      signature: String(pending.signature || ""),
      pendingBarVisibleAfterReload: Boolean(checkoutPage.data.pendingBarVisible),
      pendingOrderIdAfterReload: String(checkoutPage.data.pendingOrderId || ""),
      orderLockedAfterReload: Boolean(checkoutPage.data.orderLocked),
      checkoutError: String(checkoutPage.data.errorMessage || ""),
      pageWaitTimeoutMs: options.pageWaitTimeoutMs,
    };
  }, { pageWaitTimeoutMs: PAGE_WAIT_TIMEOUT_MS });
}

async function payRestoredOrder(miniProgram, expectedValues) {
  return miniProgram.evaluate(async function (options) {
    const state = globalThis.__yunxiPendingOrderRecoveryTestState;
    if (!state || !state.session) {
      throw new Error("待支付恢复测试会话已丢失");
    }

    function sleep(milliseconds) {
      return new Promise(function (resolve) {
        setTimeout(resolve, milliseconds);
      });
    }

    function waitForPage(route, timeoutMilliseconds) {
      return new Promise(function (resolve, reject) {
        const startedAt = Date.now();
        const timer = setInterval(function () {
          const pages = getCurrentPages();
          const page = pages[pages.length - 1];
          if (page && page.route === route) {
            clearInterval(timer);
            resolve(page);
            return;
          }
          if (Date.now() - startedAt >= timeoutMilliseconds) {
            clearInterval(timer);
            reject(new Error("等待页面超时：" + route));
          }
        }, 100);
      });
    }

    function waitForOrderDetail(page, timeoutMilliseconds) {
      return new Promise(function (resolve, reject) {
        const startedAt = Date.now();
        const timer = setInterval(function () {
          if (page.data && page.data.loading === false && page.data.order) {
            clearInterval(timer);
            resolve(page);
            return;
          }
          if (Date.now() - startedAt >= timeoutMilliseconds) {
            clearInterval(timer);
            reject(new Error("等待订单详情数据超时"));
          }
        }, 100);
      });
    }

    function getOrder(requestPath) {
      return new Promise(function (resolve, reject) {
        wx.request({
          url: options.apiBaseUrl + requestPath,
          method: "GET",
          timeout: 10000,
          header: {
            "content-type": "application/json",
            Authorization: state.session.tokenType + " " + state.session.accessToken,
          },
          success: function (response) {
            if (response.statusCode < 200 || response.statusCode >= 300) {
              reject(new Error("读取订单详情返回 HTTP " + response.statusCode));
              return;
            }
            resolve(response.data && response.data.data ? response.data.data : response.data);
          },
          fail: function (error) {
            reject(new Error(error.errMsg || "读取订单详情失败"));
          },
        });
      });
    }

    function setPageData(page, values) {
      return new Promise(function (resolve) {
        page.setData(values, resolve);
      });
    }

    const pages = getCurrentPages();
    const checkoutPage = pages[pages.length - 1];
    if (!checkoutPage || checkoutPage.route !== "pages/checkout/index") {
      throw new Error("恢复支付时当前页面不是结算页");
    }
    await setPageData(checkoutPage, {
      receiverName: options.expected.receiverName,
      receiverPhone: options.expected.receiverPhone,
      remark: options.expected.remark,
      deliveryType: "pickup",
      deliveryAddress: "",
      agreementAccepted: true,
    });
    await checkoutPage.submitOrder();
    const detailPage = await waitForPage("pages/order-detail/index", options.pageWaitTimeoutMs);
    await waitForOrderDetail(detailPage, options.pageWaitTimeoutMs);
    const orderId = String((detailPage.data && detailPage.data.order && detailPage.data.order.id) || "");
    if (!orderId) {
      throw new Error("支付后订单详情未返回订单号");
    }
    const order = await getOrder("/api/v1/miniapp/orders/" + encodeURIComponent(orderId));
    const itemIds = Array.isArray(order.items)
      ? order.items.map(function (item) {
          return String(item.productId || item.product_id || "");
        })
      : [];
    return {
      orderId: orderId,
      paymentStatus: String(order.paymentStatus || ""),
      paymentMethod: String(order.paymentMethod || ""),
      receiverNameMatches:
        String(order.receiverName || "") === options.expected.receiverName,
      receiverPhoneMatches:
        String(order.receiverPhone || "") === options.expected.receiverPhone,
      remarkMatches: String(order.remark || "") === options.expected.remark,
      expectedProductPaid:
        itemIds.length === 1 && itemIds[0] === options.expected.productId,
      actualProductIds: itemIds,
      checkoutErrorBeforeRedirect: String(checkoutPage.data.errorMessage || ""),
      cartItemCountAfterPayment: Array.isArray(wx.getStorageSync("cartItems"))
        ? wx.getStorageSync("cartItems").length
        : -1,
      pageWaitTimeoutMs: options.pageWaitTimeoutMs,
    };
  }, {
    apiBaseUrl: LOCAL_API_BASE_URL,
    expected: expectedValues,
    pageWaitTimeoutMs: PAGE_WAIT_TIMEOUT_MS,
    pendingOrderId: expectedValues.pendingOrderId,
  });
}

async function prepareChangedContactScenario(miniProgram) {
  const original = {
    receiverName: "待支付原联系人",
    receiverPhone: "18800000101",
    remark: "原备注",
  };
  const changed = {
    receiverName: "待支付新联系人",
    receiverPhone: "18800000102",
    remark: "新备注",
  };
  const prepared = await openCheckoutForProduct(miniProgram, 0, original);
  const pending = await createPendingOrder(miniProgram);
  return { original, changed, prepared, pending };
}

async function completeChangedContactScenario(miniProgram, preparedScenario) {
  const paid = await payRestoredOrder(miniProgram, {
    ...preparedScenario.changed,
    pendingOrderId: preparedScenario.pending.orderId,
  });
  return {
    expected: {
      productId: preparedScenario.prepared.productId,
      receiverName: preparedScenario.changed.receiverName,
      receiverPhone: preparedScenario.changed.receiverPhone,
      remark: preparedScenario.changed.remark,
    },
    originalPhoneSuffix: preparedScenario.original.receiverPhone.slice(-4),
    changedPhoneSuffix: preparedScenario.changed.receiverPhone.slice(-4),
    pending: {
      orderId: preparedScenario.pending.orderId,
      pendingBarVisibleAfterReload: preparedScenario.pending.pendingBarVisibleAfterReload,
      pendingOrderIdAfterReload: preparedScenario.pending.pendingOrderIdAfterReload,
      orderLockedAfterReload: preparedScenario.pending.orderLockedAfterReload,
      checkoutError: preparedScenario.pending.checkoutError,
    },
    paid,
  };
}

async function prepareChangedProductScenario(miniProgram) {
  const originalProductIndex = 0;
  const original = {
    receiverName: "换商品联系人",
    receiverPhone: "18800000103",
    remark: "换商品复现",
  };
  const firstPrepared = await openCheckoutForProduct(
    miniProgram,
    originalProductIndex,
    original
  );
  const pending = await createPendingOrder(miniProgram);
  const changedPrepared = await openCheckoutForProduct(miniProgram, 1, {
    ...original,
    preservePendingOrder: true,
  });
  await miniProgram.evaluate(async function (options) {
    const pending = wx.getStorageSync("yunxiPendingOrder");
    const pages = getCurrentPages();
    const checkoutPage = pages[pages.length - 1];
    if (!pending || !checkoutPage || checkoutPage.route !== "pages/checkout/index") {
      throw new Error("更换商品场景的待支付状态或结算页缺失");
    }
    await checkoutPage.loadCheckout();
    await new Promise(function (resolve) {
      setTimeout(resolve, 200);
    });
  }, { pageWaitTimeoutMs: PAGE_WAIT_TIMEOUT_MS });
  const changedWithPending = await miniProgram.evaluate(function () {
    const pages = getCurrentPages();
    const checkoutPage = pages[pages.length - 1];
    const pending = wx.getStorageSync("yunxiPendingOrder");
    return {
      pendingBarVisible: Boolean(checkoutPage.data.pendingBarVisible),
      pendingOrderId: String(checkoutPage.data.pendingOrderId || ""),
      expectedChangedProductId: String(checkoutPage.data.checkoutItems[0].productId || ""),
      storedOrderId: String(pending.orderId || ""),
    };
  });
  return { firstPrepared, changedPrepared, pending, changedWithPending, original };
}

async function completeChangedProductScenario(miniProgram, preparedScenario) {
  const paid = await payRestoredOrder(miniProgram, {
    productId: preparedScenario.changedPrepared.productId,
    receiverName: preparedScenario.original.receiverName,
    receiverPhone: preparedScenario.original.receiverPhone,
    remark: preparedScenario.original.remark,
    pendingOrderId: preparedScenario.pending.orderId,
  });
  return {
    firstProductId: preparedScenario.firstPrepared.productId,
    changedProductId: preparedScenario.changedPrepared.productId,
    pending: {
      orderId: preparedScenario.pending.orderId,
      barVisibleAfterChangedCart: preparedScenario.changedWithPending.pendingBarVisible,
      restoredOrderId: preparedScenario.changedWithPending.pendingOrderId,
      storedOrderId: preparedScenario.changedWithPending.storedOrderId,
    },
    paid,
  };
}

async function runDoubleSubmitScenario(miniProgram) {
  const prepared = await openCheckoutForProduct(miniProgram, 0, {
    receiverName: "双击提交联系人",
    receiverPhone: "18800000104",
    remark: "双击提交复现",
  });
  return miniProgram.evaluate(async function (options) {
    const state = globalThis.__yunxiPendingOrderRecoveryTestState;
    const pages = getCurrentPages();
    const checkoutPage = pages[pages.length - 1];
    if (!checkoutPage || checkoutPage.route !== "pages/checkout/index") {
      throw new Error("双击提交场景当前页面不是结算页");
    }

    function listOrders() {
      return new Promise(function (resolve, reject) {
        wx.request({
          url: options.apiBaseUrl + "/api/v1/miniapp/orders?page=1&pageSize=1",
          method: "GET",
          timeout: 10000,
          header: {
            "content-type": "application/json",
            Authorization: state.session.tokenType + " " + state.session.accessToken,
          },
          success: function (response) {
            if (response.statusCode < 200 || response.statusCode >= 300) {
              reject(new Error("读取订单数量返回 HTTP " + response.statusCode));
              return;
            }
            const payload = response.data && response.data.data ? response.data.data : response.data;
            resolve(Number(payload.total || 0));
          },
          fail: function (error) {
            reject(new Error(error.errMsg || "读取订单数量失败"));
          },
        });
      });
    }

    const before = await listOrders();
    const first = checkoutPage.submitOrder();
    const second = checkoutPage.submitOrder();
    await Promise.all([first, second]);
    await new Promise(function (resolve) {
      setTimeout(resolve, 500);
    });
    const pending = wx.getStorageSync("yunxiPendingOrder");
    const after = await listOrders();
    return {
      productId: options.productId,
      orderCountBefore: before,
      orderCountAfter: after,
      createdOrderCount: after - before,
      hasPendingOrder: Boolean(pending && pending.orderId),
      checkoutError: String(checkoutPage.data.errorMessage || ""),
      pageWaitTimeoutMs: options.pageWaitTimeoutMs,
    };
  }, {
    apiBaseUrl: LOCAL_API_BASE_URL,
    pageWaitTimeoutMs: PAGE_WAIT_TIMEOUT_MS,
    productId: prepared.productId,
  });
}

async function cleanupRuntime(miniProgram) {
  return miniProgram.evaluate(function (stateKey) {
    const state = globalThis[stateKey];
    if (!state) {
      return { restored: true, hadState: false };
    }
    const snapshot = state.storageSnapshot || {};
    Object.keys(snapshot).forEach(function (key) {
      const entry = snapshot[key];
      if (entry && entry.exists) {
        wx.setStorageSync(key, entry.value);
      } else {
        wx.removeStorageSync(key);
      }
    });
    const restoredCartItems = snapshot.cartItems && snapshot.cartItems.value;
    getApp().globalData.cartItems = Array.isArray(restoredCartItems) ? restoredCartItems : [];
    delete globalThis[stateKey];
    return { restored: true, hadState: true };
  }, runtimeStateKey);
}

function buildChecks(result) {
  const contact = result.changedContact || {};
  const contactPaid = contact.paid || {};
  const product = result.changedProduct || {};
  const productPaid = product.paid || {};
  const doubleSubmit = result.doubleSubmit || {};
  return [
    {
      name: "同商品修改联系人手机号后支付当前订单快照",
      ok:
        contactPaid.paymentStatus === "paid" &&
        contactPaid.receiverNameMatches === true &&
        contactPaid.receiverPhoneMatches === true &&
        contactPaid.remarkMatches === true,
      detail: {
        orderId: shortOrderId(contactPaid.orderId),
        paymentStatus: contactPaid.paymentStatus || "",
        receiverNameMatches: Boolean(contactPaid.receiverNameMatches),
        receiverPhoneMatches: Boolean(contactPaid.receiverPhoneMatches),
        remarkMatches: Boolean(contactPaid.remarkMatches),
        originalPhoneSuffix: contact.originalPhoneSuffix || "",
        changedPhoneSuffix: contact.changedPhoneSuffix || "",
      },
    },
    {
      name: "更换购物车商品后支付新商品订单",
      ok: productPaid.paymentStatus === "paid" && productPaid.expectedProductPaid === true,
      detail: {
        orderId: shortOrderId(productPaid.orderId),
        firstProductId: product.firstProductId || "",
        changedProductId: product.changedProductId || "",
        paymentStatus: productPaid.paymentStatus || "",
        expectedProductPaid: Boolean(productPaid.expectedProductPaid),
        actualProductIds: productPaid.actualProductIds || [],
        pendingBarVisibleAfterChangedCart: Boolean(
          product.pending && product.pending.barVisibleAfterChangedCart
        ),
      },
    },
    {
      name: "连续两次提交只创建一个订单",
      ok:
        Number(doubleSubmit.createdOrderCount) === 1 &&
        doubleSubmit.hasPendingOrder === true &&
        !doubleSubmit.checkoutError,
      detail: {
        productId: doubleSubmit.productId || "",
        orderCountBefore: Number(doubleSubmit.orderCountBefore || 0),
        orderCountAfter: Number(doubleSubmit.orderCountAfter || 0),
        createdOrderCount: Number(doubleSubmit.createdOrderCount || 0),
        hasPendingOrder: Boolean(doubleSubmit.hasPendingOrder),
        checkoutError: doubleSubmit.checkoutError || "",
      },
    },
  ];
}

function sanitizeResult(result) {
  return {
    changedContact: result.changedContact
      ? {
          expected: result.changedContact.expected
            ? {
                productId: result.changedContact.expected.productId,
                receiverName: result.changedContact.expected.receiverName,
                phoneSuffix: result.changedContact.expected.receiverPhone.slice(-4),
                remark: result.changedContact.expected.remark,
              }
            : null,
          pending: result.changedContact.pending
            ? {
                orderId: shortOrderId(result.changedContact.pending.orderId),
                pendingBarVisibleAfterReload: Boolean(
                  result.changedContact.pending.pendingBarVisibleAfterReload
                ),
                pendingOrderIdAfterReload: shortOrderId(
                  result.changedContact.pending.pendingOrderIdAfterReload
                ),
                orderLockedAfterReload: Boolean(
                  result.changedContact.pending.orderLockedAfterReload
                ),
                checkoutError: result.changedContact.pending.checkoutError || "",
              }
            : null,
          paid: result.changedContact.paid
            ? {
                orderId: shortOrderId(result.changedContact.paid.orderId),
                paymentStatus: result.changedContact.paid.paymentStatus || "",
                paymentMethod: result.changedContact.paid.paymentMethod || "",
                receiverNameMatches: Boolean(result.changedContact.paid.receiverNameMatches),
                receiverPhoneMatches: Boolean(result.changedContact.paid.receiverPhoneMatches),
                remarkMatches: Boolean(result.changedContact.paid.remarkMatches),
                expectedProductPaid: Boolean(result.changedContact.paid.expectedProductPaid),
                actualProductIds: result.changedContact.paid.actualProductIds || [],
                cartItemCountAfterPayment: Number(
                  result.changedContact.paid.cartItemCountAfterPayment || -1
                ),
              }
            : null,
        }
      : null,
    changedProduct: result.changedProduct
      ? {
          firstProductId: result.changedProduct.firstProductId || "",
          changedProductId: result.changedProduct.changedProductId || "",
          pending: result.changedProduct.pending
            ? {
                orderId: shortOrderId(result.changedProduct.pending.orderId),
                barVisibleAfterChangedCart: Boolean(
                  result.changedProduct.pending.barVisibleAfterChangedCart
                ),
                restoredOrderId: shortOrderId(result.changedProduct.pending.restoredOrderId),
                storedOrderId: shortOrderId(result.changedProduct.pending.storedOrderId),
              }
            : null,
          paid: result.changedProduct.paid
            ? {
                orderId: shortOrderId(result.changedProduct.paid.orderId),
                paymentStatus: result.changedProduct.paid.paymentStatus || "",
                paymentMethod: result.changedProduct.paid.paymentMethod || "",
                expectedProductPaid: Boolean(result.changedProduct.paid.expectedProductPaid),
                actualProductIds: result.changedProduct.paid.actualProductIds || [],
                receiverNameMatches: Boolean(result.changedProduct.paid.receiverNameMatches),
                receiverPhoneMatches: Boolean(result.changedProduct.paid.receiverPhoneMatches),
                remarkMatches: Boolean(result.changedProduct.paid.remarkMatches),
                cartItemCountAfterPayment: Number(
                  result.changedProduct.paid.cartItemCountAfterPayment || -1
                ),
              }
            : null,
        }
      : null,
    doubleSubmit: result.doubleSubmit
      ? {
          productId: result.doubleSubmit.productId || "",
          orderCountBefore: Number(result.doubleSubmit.orderCountBefore || 0),
          orderCountAfter: Number(result.doubleSubmit.orderCountAfter || 0),
          createdOrderCount: Number(result.doubleSubmit.createdOrderCount || 0),
          hasPendingOrder: Boolean(result.doubleSubmit.hasPendingOrder),
          checkoutError: result.doubleSubmit.checkoutError || "",
        }
      : null,
  };
}

async function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const report = {
    traceId: TRACE_ID,
    runId: RUN_ID,
    generatedAt: new Date().toISOString(),
    apiBaseUrl: LOCAL_API_BASE_URL,
    automatorWsEndpoint: AUTOMATOR_WS_ENDPOINT,
    status: "blocked",
    checks: [],
    errors: [],
    result: {},
    notes: [
      "仅使用本地后端、合成联系人和 DevTools 本地存储。",
      "不读取生产订单，不执行真实微信支付。",
      "报告不保存 accessToken、openid、手机号全文或请求头。",
    ],
  };
  let miniProgram;
  let setupCompleted = false;
  let modalMocked = false;
  let cleanupBlocked = false;
  try {
    try {
      report.result.health = await probeLocalHealth();
    } catch (error) {
      addError(report, "local-health", error);
    }
    if (report.result.health) {
      try {
        miniProgram = await connectAutomator();
      } catch (error) {
        addError(report, "devtools-connect", error);
      }
    }
    if (miniProgram) {
      try {
        const setup = await setupRuntime(miniProgram);
        setupCompleted = true;
        report.result.setup = {
          envVersion: setup.envVersion,
          session: setup.session,
          products: setup.products,
        };
      } catch (error) {
        addError(report, "runtime-setup", error);
        report.status = isBlockedError(error) ? "blocked" : "fail";
      }
    }
    if (setupCompleted) {
      const rawResult = {};
      let preparedChangedContact = null;
      try {
        await miniProgram.mockWxMethod("showModal", { confirm: false, cancel: true });
        modalMocked = true;
        preparedChangedContact = await prepareChangedContactScenario(miniProgram);
      } catch (error) {
        addError(report, "changed-contact", error);
      } finally {
        if (modalMocked) {
          await miniProgram.restoreWxMethod("showModal");
          modalMocked = false;
        }
      }
      if (preparedChangedContact) {
        try {
          await miniProgram.mockWxMethod("showModal", { confirm: true, cancel: false });
          modalMocked = true;
          rawResult.changedContact = await completeChangedContactScenario(
            miniProgram,
            preparedChangedContact
          );
        } catch (error) {
          addError(report, "changed-contact", error);
        } finally {
          if (modalMocked) {
            await miniProgram.restoreWxMethod("showModal");
            modalMocked = false;
          }
        }
      }
      let preparedChangedProduct = null;
      if (!report.errors.some((entry) => entry.stage === "changed-contact")) {
        try {
          await miniProgram.mockWxMethod("showModal", { confirm: false, cancel: true });
          modalMocked = true;
          preparedChangedProduct = await prepareChangedProductScenario(miniProgram);
        } catch (error) {
          addError(report, "changed-product", error);
        } finally {
          if (modalMocked) {
            await miniProgram.restoreWxMethod("showModal");
            modalMocked = false;
          }
        }
      }
      if (preparedChangedProduct) {
        try {
          await miniProgram.mockWxMethod("showModal", { confirm: true, cancel: false });
          modalMocked = true;
          rawResult.changedProduct = await completeChangedProductScenario(
            miniProgram,
            preparedChangedProduct
          );
        } catch (error) {
          addError(report, "changed-product", error);
        } finally {
          if (modalMocked) {
            await miniProgram.restoreWxMethod("showModal");
            modalMocked = false;
          }
        }
      }
      if (preparedChangedProduct) {
        try {
          await miniProgram.mockWxMethod("showModal", { confirm: false, cancel: true });
          modalMocked = true;
          rawResult.doubleSubmit = await runDoubleSubmitScenario(miniProgram);
        } catch (error) {
          addError(report, "double-submit", error);
        } finally {
          if (modalMocked) {
            await miniProgram.restoreWxMethod("showModal");
            modalMocked = false;
          }
        }
      }
      report.result = { ...report.result, ...sanitizeResult(rawResult) };
      report.checks = buildChecks(rawResult);
      const hasBlockedError = report.errors.some((entry) =>
        isBlockedError(new Error(entry.message))
      );
      if (hasBlockedError) {
        report.status = "blocked";
      } else if (report.errors.length > 0 || report.checks.some((check) => !check.ok)) {
        report.status = "fail";
      } else {
        report.status = "pass";
      }
    }
  } catch (error) {
    report.status = "blocked";
    addError(report, "unexpected", error);
  } finally {
    if (modalMocked && miniProgram) {
      try {
        await miniProgram.restoreWxMethod("showModal");
      } catch (error) {
        cleanupBlocked = true;
        addError(report, "modal-cleanup", error);
      }
    }
    if (setupCompleted && miniProgram) {
      try {
        report.result.cleanup = await cleanupRuntime(miniProgram);
      } catch (error) {
        cleanupBlocked = true;
        addError(report, "storage-cleanup", error);
      }
    } else if (miniProgram) {
      try {
        await cleanupRuntime(miniProgram);
      } catch {
        // 初始化未完成时仍尝试清理 DevTools 全局测试状态。
      }
    }
    if (miniProgram) {
      miniProgram.disconnect();
    }
    if (cleanupBlocked && report.status === "pass") {
      report.status = "blocked";
    }
  }
  return finish(report, report.status === "pass" ? 0 : report.status === "fail" ? 1 : 2);
}

function finish(report, exitCode) {
  if (!report.status || report.status === "blocked") {
    report.status = "blocked";
  }
  report.generatedAt = new Date().toISOString();
  const reportPath = path.join(reportsRoot, `pending-order-recovery-${nowStamp()}.json`);
  const payload = `${JSON.stringify(report, null, 2)}\n`;
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "pending-order-recovery-latest.json"), payload, "utf8");
  console.log(`MiniApp 待支付订单恢复复核 ${report.status}`);
  console.log(`报告：${reportPath}`);
  process.exitCode = exitCode;
  return report;
}

main().catch((error) => {
  console.error(safeError(error));
  process.exitCode = 1;
});
