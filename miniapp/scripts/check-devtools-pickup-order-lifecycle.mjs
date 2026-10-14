import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import automator from "miniprogram-automator";

const TRACE_ID = "20260924-miniapp-pickup-order-lifecycle";
const RUN_ID = "20260924-miniapp-pickup-order-lifecycle-r6";
const LOCAL_API_BASE_URL = "http://127.0.0.1:7001";
const LOCAL_HEALTH_TIMEOUT_MS = 5_000;
const AUTOMATOR_CONNECT_TIMEOUT_MS = 8_000;
const PAGE_WAIT_TIMEOUT_MS = 15_000;
const EXPECTED_PICKUP_ADDRESS = "北京市东城区南竹杆胡同2号银河SOHO";
const root = process.cwd();
const reportsRoot = path.join(root, "reports", "button-runtime");
const wsEndpoint = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const runtimeStateKey = "__yunxiPickupOrderLifecycleTestState";

function nowStamp() {
  return new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
}

function safeError(error) {
  const message = error instanceof Error ? error.message : String(error);
  return message.replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer <redacted>").slice(0, 500);
}

function isBlockedError(error) {
  const message = safeError(error);
  return (
    message.startsWith("BLOCKED:") ||
    /timeout waiting for automator response|Connection closed|ECONNREFUSED|ETIMEDOUT/.test(message)
  );
}

function shortOrderId(orderId) {
  const value = String(orderId || "");
  if (!value) {
    return "";
  }
  return value.length <= 12 ? value : `${value.slice(0, 6)}...${value.slice(-4)}`;
}

function sanitizeSetup(setup) {
  return {
    envVersion: setup.envVersion,
    localApiStorage: setup.localApiStorage,
    session: setup.session,
    product: setup.product
      ? {
          id: setup.product.id,
          priceFen: setup.product.priceFen,
          stock: setup.product.stock
        }
      : null
  };
}

function sanitizeScenario(scenario) {
  if (!scenario) {
    return null;
  }
  const order = scenario.order || {};
  return {
    stage: scenario.stage || "",
    checkoutError: scenario.checkoutError || "",
    order: {
      id: shortOrderId(order.id),
      status: order.status || "",
      paymentStatus: order.paymentStatus || "",
      paymentMethod: order.paymentMethod || "",
      deliveryType: order.deliveryType || "",
      itemCount: Number(order.itemCount || 0),
      timelineCount: Number(order.timelineCount || 0)
    },
    cartItemCount: Number(scenario.cartItemCount || 0),
    hasPendingOrder: Boolean(scenario.hasPendingOrder),
    pendingBarVisibleAfterSubmit: Boolean(scenario.pendingBarVisibleAfterSubmit),
    pickupAddressMatches: Boolean(scenario.pickupAddressMatches ?? order.pickupAddressMatches),
    error: scenario.error || ""
  };
}

function probeLocalHealth() {
  return new Promise((resolve, reject) => {
    const request = http.request(
      `${LOCAL_API_BASE_URL}/health`,
      { method: "GET", timeout: LOCAL_HEALTH_TIMEOUT_MS },
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
      const timeoutError = new Error(`本地后端健康检查超时（${LOCAL_HEALTH_TIMEOUT_MS}ms）`);
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
            reject(new Error(`FAIL: 本地商品接口返回 HTTP ${response.statusCode || 0}`));
            return;
          }
          try {
            resolve(JSON.parse(body));
          } catch {
            reject(new Error("FAIL: 本地商品接口返回了无效 JSON"));
          }
        });
      }
    );
    request.on("timeout", () => {
      const timeoutError = new Error("本地商品接口请求超时（10000ms）");
      timeoutError.code = "ETIMEDOUT";
      request.destroy(timeoutError);
    });
    request.on("error", reject);
    request.end();
  });
}

async function connectAutomator() {
  return Promise.race([
    automator.connect({ wsEndpoint }),
    new Promise((_, reject) => {
      setTimeout(() => {
        reject(new Error(`DevTools Automator 连接超时（${AUTOMATOR_CONNECT_TIMEOUT_MS}ms）`));
      }, AUTOMATOR_CONNECT_TIMEOUT_MS);
    })
  ]);
}

function addError(report, stage, error) {
  report.errors.push({ stage, message: safeError(error) });
}

async function setupRuntime(miniProgram) {
  const login = await miniProgram.evaluate(async function (apiBaseUrl) {
    const stateKey = "__yunxiPickupOrderLifecycleTestState";
    const storageKeys = [
      "cartItems",
      "miniappSession",
      "miniappUserId",
      "yunxiPendingOrder",
      "yunxiUseLocalApi"
    ];

    function sleep(milliseconds) {
      return new Promise(function (resolve) {
        setTimeout(resolve, milliseconds);
      });
    }

    function readStorageSnapshot() {
      const existingKeys = wx.getStorageInfoSync().keys || [];
      const snapshot = {};
      storageKeys.forEach(function (key) {
        snapshot[key] = {
          exists: existingKeys.indexOf(key) !== -1,
          value: wx.getStorageSync(key)
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
                  expiresAt: Date.now() + expiresIn * 1000
                });
              },
              fail: function (error) {
                reject(new Error("BLOCKED: 本地登录请求失败：" + (error.errMsg || "未知错误")));
              }
            });
          },
          fail: function (error) {
            reject(new Error("BLOCKED: wx.login 失败：" + (error.errMsg || "未知错误")));
          }
        });
      });
    }

    const storageSnapshot = readStorageSnapshot();
    globalThis[stateKey] = { storageSnapshot: storageSnapshot, session: null, product: null };
    const accountInfo = wx.getAccountInfoSync();
    if (accountInfo.miniProgram.envVersion !== "develop") {
      throw new Error("BLOCKED: 生命周期测试只允许在 develop 环境运行");
    }
    const storedLocalApi = wx.getStorageSync("yunxiUseLocalApi");
    if (storedLocalApi === false || storedLocalApi === "false") {
      throw new Error("BLOCKED: DevTools 当前以生产 API 启动，请将 yunxiUseLocalApi 设为 true 后重编译");
    }

    const session = await loginWithWechat();
    globalThis[stateKey].session = session;
    wx.setStorageSync("yunxiUseLocalApi", true);
    wx.setStorageSync("miniappSession", session);
    wx.setStorageSync("miniappUserId", session.userId);
    wx.removeStorageSync("yunxiPendingOrder");
    return {
      envVersion: accountInfo.miniProgram.envVersion,
      session: session
    };
  }, LOCAL_API_BASE_URL);

  const productPayload = await requestLocalJson("/api/v1/miniapp/products?limit=100", login.session.accessToken);
  const products = Array.isArray(productPayload.data) ? productPayload.data : [];
  const product = products.find((item) =>
    item &&
    item.id &&
    item.isActive === true &&
    item.isPurchasable !== false &&
    Number(item.stock) >= 2 &&
    Number(item.priceFen) > 0
  );
  if (!product) {
    throw new Error("BLOCKED: 本地测试商品不足，需要至少一个在售、可购买且库存不少于 2 件的商品");
  }
  const selectedProduct = {
    id: String(product.id),
    title: String(product.title || product.id),
    imageUrl: String(product.imageUrl || ""),
    priceFen: Number(product.priceFen),
    stock: Number(product.stock)
  };
  await miniProgram.evaluate(function (options) {
    const stateKey = "__yunxiPickupOrderLifecycleTestState";
    if (!globalThis[stateKey]) {
      throw new Error("生命周期测试运行态已丢失");
    }
    globalThis[stateKey].product = options.product;
  }, { product: selectedProduct });
  return {
    envVersion: login.envVersion,
    localApiStorage: true,
    session: {
      hasAccessToken: true,
      tokenType: login.session.tokenType,
      expiresIn: login.session.expiresIn
    },
    product: selectedProduct
  };
}

async function prepareLifecycleScenario(miniProgram) {
  return miniProgram.evaluate(async function (options) {
    const stateKey = "__yunxiPickupOrderLifecycleTestState";
    const state = globalThis[stateKey];
    if (!state || !state.session || !state.product) {
      throw new Error("生命周期测试运行态尚未初始化");
    }

    function sleep(milliseconds) {
      return new Promise(function (resolve) {
        setTimeout(resolve, milliseconds);
      });
    }

    async function waitForPage(route, timeoutMilliseconds) {
      const startedAt = Date.now();
      while (Date.now() - startedAt < timeoutMilliseconds) {
        const pages = getCurrentPages();
        const page = pages[pages.length - 1];
        if (page && page.route === route) {
          return page;
        }
        await sleep(200);
      }
      throw new Error("等待页面超时：" + route);
    }

    async function waitFor(predicate, timeoutMilliseconds, message) {
      const startedAt = Date.now();
      while (Date.now() - startedAt < timeoutMilliseconds) {
        if (predicate()) {
          return;
        }
        await sleep(200);
      }
      throw new Error(message);
    }

    function switchTab(url) {
      return new Promise(function (resolve, reject) {
        wx.switchTab({
          url: url,
          success: resolve,
          fail: function (error) {
            reject(new Error(error.errMsg || "切换 Tab 失败"));
          }
        });
      });
    }

    const cartItem = {
      productId: state.product.id,
      title: state.product.title,
      imageUrl: state.product.imageUrl,
      priceFen: state.product.priceFen,
      quantity: 1,
      stock: state.product.stock
    };
    wx.setStorageSync("yunxiUseLocalApi", true);
    wx.setStorageSync("cartItems", [cartItem]);
    wx.removeStorageSync("yunxiPendingOrder");
    const app = getApp();
    app.globalData.cartItems = [cartItem];

    await switchTab("/pages/cart/index");
    const cartPage = await waitForPage("pages/cart/index", options.pageWaitTimeoutMs);
    await waitFor(
      function () {
        return cartPage.data && cartPage.data.hasItems === true;
      },
      options.pageWaitTimeoutMs,
      "购物车未加载测试商品"
    );
    cartPage.checkout();
    const checkoutPage = await waitForPage("pages/checkout/index", options.pageWaitTimeoutMs);
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
      "结算页未加载本地测试会话和购物车"
    );

    await new Promise(function (resolve) {
      checkoutPage.setData(
        {
          receiverName: "本地自提闭环",
          receiverPhone: "18800000021",
          deliveryType: "pickup",
          deliveryAddress: "",
          remark: "",
          pickupAddress: options.expectedPickupAddress,
          agreementAccepted: true,
          expectTime: "2099-01-02 18:00",
          isLoggedIn: true,
          selectedCouponId: "",
          pointsEnabled: false,
          balanceEnabled: false,
          pendingOrderId: "",
          pendingBarVisible: false,
          orderLocked: false,
          errorMessage: ""
        },
        function () {
          if (typeof checkoutPage.refreshEstimate === "function") {
            checkoutPage.refreshEstimate();
          }
          if (typeof checkoutPage.refreshSubmitState === "function") {
            checkoutPage.refreshSubmitState();
          }
          resolve();
        }
      );
    });
    return {
      stage: "prepared",
      checkoutError: checkoutPage.data.errorMessage || ""
    };
  }, {
    apiBaseUrl: LOCAL_API_BASE_URL,
    expectedPickupAddress: EXPECTED_PICKUP_ADDRESS,
    pageWaitTimeoutMs: PAGE_WAIT_TIMEOUT_MS
  });
}

async function completeLifecycleScenario(miniProgram, confirmPayment) {
  return miniProgram.evaluate(async function (options) {
    const stateKey = "__yunxiPickupOrderLifecycleTestState";
    const state = globalThis[stateKey];
    if (!state || !state.session || !state.product) {
      throw new Error("生命周期测试运行态尚未初始化");
    }

    function sleep(milliseconds) {
      return new Promise(function (resolve) {
        setTimeout(resolve, milliseconds);
      });
    }

    async function waitForPage(route, timeoutMilliseconds) {
      const startedAt = Date.now();
      while (Date.now() - startedAt < timeoutMilliseconds) {
        const pages = getCurrentPages();
        const page = pages[pages.length - 1];
        if (page && page.route === route) {
          return page;
        }
        await sleep(200);
      }
      throw new Error("等待页面超时：" + route);
    }

    async function waitFor(predicate, timeoutMilliseconds, message) {
      const startedAt = Date.now();
      while (Date.now() - startedAt < timeoutMilliseconds) {
        if (predicate()) {
          return;
        }
        await sleep(200);
      }
      throw new Error(message);
    }

    function getOrder(requestPath) {
      return new Promise(function (resolve, reject) {
        wx.request({
          url: options.apiBaseUrl + requestPath,
          method: "GET",
          timeout: 10000,
          header: {
            "content-type": "application/json",
            Authorization: state.session.tokenType + " " + state.session.accessToken
          },
          success: function (response) {
            if (response.statusCode < 200 || response.statusCode >= 300) {
              reject(new Error("读取订单状态返回 HTTP " + response.statusCode));
              return;
            }
            resolve(response.data && response.data.data ? response.data.data : response.data);
          },
          fail: function (error) {
            reject(new Error(error.errMsg || "读取订单状态失败"));
          }
        });
      });
    }

    const checkoutPage = await waitForPage("pages/checkout/index", options.pageWaitTimeoutMs);
    await checkoutPage.submitOrder();
    await sleep(options.confirmPayment ? 800 : 400);

    if (options.confirmPayment) {
      const detailPage = await waitForPage("pages/order-detail/index", options.pageWaitTimeoutMs);
      await waitFor(
        function () {
          return detailPage.data && detailPage.data.loading === false && detailPage.data.order;
        },
        options.pageWaitTimeoutMs,
        "支付成功后的订单详情未加载完成"
      );
      const detail = detailPage.data.order;
      const cartItemsAfterPayment = wx.getStorageSync("cartItems");
      return {
        stage: "payment-success",
        checkoutError: checkoutPage.data.errorMessage || "",
        order: {
          id: detail.id,
          status: detail.status,
          paymentStatus: detail.paymentStatus,
          paymentMethod: detail.paymentMethod,
          deliveryType: detail.deliveryType,
          pickupAddress: detail.pickupAddress,
          pickupAddressMatches: detail.pickupAddress === options.expectedPickupAddress,
          itemCount: Array.isArray(detail.itemsView) ? detail.itemsView.length : 0,
          timelineCount: Array.isArray(detail.timeline) ? detail.timeline.length : 0
        },
        cartItemCount: Array.isArray(cartItemsAfterPayment) ? cartItemsAfterPayment.length : -1,
        hasPendingOrder: Boolean(wx.getStorageSync("yunxiPendingOrder"))
      };
    }

    const pendingAfterSubmit = wx.getStorageSync("yunxiPendingOrder");
    const pendingOrderId = String((pendingAfterSubmit && pendingAfterSubmit.orderId) || "");
    const pendingBarVisibleAfterSubmit = Boolean(checkoutPage.data.pendingBarVisible);
    if (!pendingOrderId) {
      throw new Error("取消支付后未创建待支付订单");
    }
    await checkoutPage.cancelPendingOrder();
    await waitFor(
      function () {
        return !wx.getStorageSync("yunxiPendingOrder");
      },
      options.pageWaitTimeoutMs,
      "取消待支付订单后本地待支付记录未清理"
    );
    const cancelledOrder = await getOrder("/api/v1/miniapp/orders/" + encodeURIComponent(pendingOrderId));
    return {
      stage: "payment-cancel",
      checkoutError: checkoutPage.data.errorMessage || "",
      pendingBarVisibleAfterSubmit: pendingBarVisibleAfterSubmit,
      hasPendingOrder: false,
      order: {
        id: cancelledOrder.id,
        status: cancelledOrder.status,
        paymentStatus: cancelledOrder.paymentStatus,
        paymentMethod: cancelledOrder.paymentMethod || "",
        deliveryType: cancelledOrder.deliveryType
      }
    };
  }, {
    apiBaseUrl: LOCAL_API_BASE_URL,
    confirmPayment,
    expectedPickupAddress: EXPECTED_PICKUP_ADDRESS,
    pageWaitTimeoutMs: PAGE_WAIT_TIMEOUT_MS
  });
}

async function runLifecycleScenario(miniProgram, confirmPayment) {
  const prepared = await prepareLifecycleScenario(miniProgram);
  const completed = await completeLifecycleScenario(miniProgram, confirmPayment);
  return {
    ...completed,
    preparedStage: prepared.stage,
    preparedCheckoutError: prepared.checkoutError
  };
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
    const app = getApp();
    const restoredCartItems = snapshot.cartItems && snapshot.cartItems.value;
    app.globalData.cartItems = Array.isArray(restoredCartItems) ? restoredCartItems : [];
    delete globalThis[stateKey];
    return { restored: true, hadState: true };
  }, runtimeStateKey);
}

function buildChecks(result) {
  const paidOrder = result.paid && result.paid.order ? result.paid.order : {};
  const cancelledOrder = result.cancelled && result.cancelled.order ? result.cancelled.order : {};
  return [
    {
      name: "支付成功进入订单详情",
      ok:
        result.paid &&
        result.paid.stage === "payment-success" &&
        Boolean(result.paid.order) &&
        !result.paid.checkoutError,
      detail: result.paid ? { routeResult: "payment-success", checkoutError: result.paid.checkoutError } : {}
    },
    {
      name: "mock 支付状态和方式正确",
      ok: paidOrder.paymentStatus === "paid" && paidOrder.paymentMethod === "mock",
      detail: {
        orderId: shortOrderId(paidOrder.id),
        paymentStatus: paidOrder.paymentStatus || "",
        paymentMethod: paidOrder.paymentMethod || ""
      }
    },
    {
      name: "自提订单地址和商品明细正确",
      ok:
        paidOrder.deliveryType === "pickup" &&
        result.paid &&
        result.paid.pickupAddressMatches === true &&
        Number(paidOrder.itemCount) > 0,
      detail: {
        deliveryType: paidOrder.deliveryType || "",
        pickupAddressMatches: Boolean(result.paid && result.paid.pickupAddressMatches),
        itemCount: Number(paidOrder.itemCount || 0)
      }
    },
    {
      name: "支付成功后购物车和待支付记录已清理",
      ok:
        result.paid &&
        Number(result.paid.cartItemCount) === 0 &&
        result.paid.hasPendingOrder === false,
      detail: result.paid
        ? { cartItemCount: result.paid.cartItemCount, hasPendingOrder: result.paid.hasPendingOrder }
        : {}
    },
    {
      name: "取消支付后待支付条可见",
      ok: Boolean(result.cancelled && result.cancelled.pendingBarVisibleAfterSubmit),
      detail: result.cancelled
        ? { pendingBarVisibleAfterSubmit: Boolean(result.cancelled.pendingBarVisibleAfterSubmit) }
        : {}
    },
    {
      name: "待支付订单取消状态回写正确",
      ok:
        cancelledOrder.status === "cancelled" &&
        cancelledOrder.paymentStatus === "unpaid" &&
        result.cancelled &&
        result.cancelled.hasPendingOrder === false,
      detail: {
        orderId: shortOrderId(cancelledOrder.id),
        status: cancelledOrder.status || "",
        paymentStatus: cancelledOrder.paymentStatus || "",
        hasPendingOrder: result.cancelled ? result.cancelled.hasPendingOrder : null
      }
    }
  ];
}

async function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const report = {
    traceId: TRACE_ID,
    runId: RUN_ID,
    generatedAt: new Date().toISOString(),
    apiBaseUrl: LOCAL_API_BASE_URL,
    wsEndpoint,
    status: "blocked",
    checks: [],
    errors: [],
    result: {},
    notes: [
      "只使用本地后端、合成联系人和本地 DevTools 存储。",
      "不读取生产订单，不执行真实微信支付。",
      "报告不保存 accessToken、openid、手机号全文或请求头。"
    ]
  };
  let miniProgram;
  let setupCompleted = false;
  let modalMocked = false;
  let cleanupBlocked = false;
  let executionBlocked = false;
  try {
    let healthAvailable = true;
    try {
      report.result.health = await probeLocalHealth();
    } catch (error) {
      addError(report, "local-health", error);
      healthAvailable = false;
    }

    if (healthAvailable) {
      try {
        miniProgram = await connectAutomator();
      } catch (error) {
        addError(report, "devtools-connect", error);
      }
    }

    if (miniProgram) {
      try {
        report.result.setup = sanitizeSetup(await setupRuntime(miniProgram));
        setupCompleted = true;
      } catch (error) {
        addError(report, "runtime-setup", error);
        report.status = isBlockedError(error) ? "blocked" : "fail";
      }
    }

    if (setupCompleted) {
      await miniProgram.mockWxMethod("showModal", { confirm: true, cancel: false });
      modalMocked = true;
      try {
        report.result.paid = sanitizeScenario(await runLifecycleScenario(miniProgram, true));
      } catch (error) {
        addError(report, "payment-success", error);
        report.result.paid = sanitizeScenario({ stage: "payment-success", error: safeError(error) });
        executionBlocked = isBlockedError(error);
      } finally {
        if (!executionBlocked) {
          await miniProgram.restoreWxMethod("showModal");
          modalMocked = false;
        }
      }

      if (!executionBlocked) {
        await miniProgram.mockWxMethod("showModal", { confirm: false, cancel: true });
        modalMocked = true;
        try {
          report.result.cancelled = sanitizeScenario(await runLifecycleScenario(miniProgram, false));
        } catch (error) {
          addError(report, "payment-cancel", error);
          report.result.cancelled = sanitizeScenario({ stage: "payment-cancel", error: safeError(error) });
          executionBlocked = isBlockedError(error);
        } finally {
          if (!executionBlocked) {
            await miniProgram.restoreWxMethod("showModal");
            modalMocked = false;
          }
        }
      }

      if (!executionBlocked) {
        report.checks = buildChecks(report.result);
      }
      if (executionBlocked) {
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
        const cleanup = await cleanupRuntime(miniProgram);
        report.result.cleanup = cleanup;
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
  const stamp = nowStamp();
  const reportPath = path.join(reportsRoot, `pickup-order-lifecycle-${stamp}.json`);
  const payload = `${JSON.stringify(report, null, 2)}\n`;
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "pickup-order-lifecycle-latest.json"), payload, "utf8");
  console.log(`MiniApp 自提订单生命周期 ${report.status}`);
  console.log(`报告：${reportPath}`);
  process.exitCode = exitCode;
  return report;
}

main().catch((error) => {
  console.error(safeError(error));
  process.exitCode = 1;
});
