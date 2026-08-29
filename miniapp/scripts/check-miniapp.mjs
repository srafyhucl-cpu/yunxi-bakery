import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const miniappRoot = path.join(root, "miniprogram");
const appJsonPath = path.join(miniappRoot, "app.json");
const appTsPath = path.join(miniappRoot, "app.ts");
const routesPath = path.join(miniappRoot, "constants", "routes.ts");
const authServicePath = path.join(miniappRoot, "services", "auth.ts");
const httpServicePath = path.join(miniappRoot, "services", "http.ts");
const transportServicePath = path.join(miniappRoot, "services", "transport.ts");
const sessionStorePath = path.join(miniappRoot, "services", "session-store.ts");
const devtoolsSmokePath = path.join(root, "scripts", "check-devtools-service-smoke.mjs");
const devtoolsAuthProbePaths = [
  devtoolsSmokePath,
  path.join(root, "scripts", "check-devtools-cart-checkout-real-product.mjs"),
  path.join(root, "scripts", "check-devtools-product-buy-now.mjs"),
];
const sessionUtilPath = path.join(miniappRoot, "utils", "session.ts");
const navigationUtilPath = path.join(miniappRoot, "utils", "navigation.ts");
const productServicePath = path.join(miniappRoot, "services", "products.ts");
const productDetailPagePath = path.join(miniappRoot, "pages", "product-detail", "index.ts");
const checkoutPagePath = path.join(miniappRoot, "pages", "checkout", "index.ts");
const orderDetailPagePath = path.join(miniappRoot, "pages", "order-detail", "index.ts");
const pageExtensions = [".json", ".ts", ".wxml", ".wxss"];
const eventAttributes = ["bindtap", "catchtap", "bind:tap", "catch:tap"];
const wxmlReservedRoots = new Set([
  "true",
  "false",
  "null",
  "undefined",
  "item",
  "index",
  "category",
  "product",
  "notice",
  "link",
  "service",
  "action",
  "option",
]);

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function readJson(filePath) {
  return JSON.parse(readText(filePath));
}

function toPosix(value) {
  return value.replaceAll(path.sep, "/");
}

function fail(message) {
  failures.push(message);
}

function extractRoutes(source) {
  return Array.from(source.matchAll(/(\w+):\s*"([^"]+)"/g)).map((match) => ({
    key: match[1],
    route: match[2],
  }));
}

function extractPageMethods(source) {
  const pageBody = source.match(/Page\s*\(\s*\{([\s\S]*)\}\s*\)\s*;?\s*$/);
  const target = pageBody ? pageBody[1] : source;
  return new Set(
    Array.from(target.matchAll(/^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{/gm))
      .map((match) => match[1])
      .filter((name) => !["if", "for", "while", "switch", "catch", "function"].includes(name)),
  );
}

function extractPageMethodBodies(source) {
  const pageBody = source.match(/Page(?:<[^>]+>)?\s*\(\s*\{([\s\S]*)\}\s*\)\s*;?\s*$/);
  const target = pageBody ? pageBody[1] : source;
  const bodies = new Map();
  const methodPattern = /^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{/gm;
  for (const match of target.matchAll(methodPattern)) {
    const name = match[1];
    if (["if", "for", "while", "switch", "catch", "function"].includes(name)) {
      continue;
    }
    const openBraceIndex = match.index + match[0].lastIndexOf("{");
    let depth = 0;
    let endIndex = -1;
    for (let index = openBraceIndex; index < target.length; index += 1) {
      const char = target[index];
      if (char === "{") {
        depth += 1;
      } else if (char === "}") {
        depth -= 1;
        if (depth === 0) {
          endIndex = index;
          break;
        }
      }
    }
    if (endIndex !== -1) {
      bodies.set(name, target.slice(openBraceIndex + 1, endIndex));
    }
  }
  return bodies;
}

function extractPageDataKeys(source) {
  const dataStart = source.match(/\bdata\s*:\s*\{/);
  if (!dataStart) {
    return new Set();
  }
  const openBraceIndex = dataStart.index + dataStart[0].lastIndexOf("{");
  let depth = 0;
  let endIndex = -1;
  for (let index = openBraceIndex; index < source.length; index += 1) {
    const char = source[index];
    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        endIndex = index;
        break;
      }
    }
  }
  if (endIndex === -1) {
    return new Set();
  }
  const dataBody = source.slice(openBraceIndex + 1, endIndex);
  return new Set(Array.from(dataBody.matchAll(/^\s*([A-Za-z_$][\w$]*)\s*:/gm)).map((match) => match[1]));
}

function extractWxmlHandlers(source) {
  const attrs = eventAttributes.join("|").replaceAll(":", "\\:");
  const pattern = new RegExp(`(?:${attrs})="([^"]+)"`, "g");
  return Array.from(source.matchAll(pattern))
    .map((match) => match[1].trim())
    .filter(Boolean)
    .filter((handler) => !handler.startsWith("{{"));
}

function extractButtonTags(source) {
  return Array.from(source.matchAll(/<button\b[^>]*>/g)).map((match) => ({
    tag: match[0],
    line: source.slice(0, match.index).split(/\r?\n/).length,
  }));
}

function extractWxmlDataRoots(source) {
  const localRoots = new Set(wxmlReservedRoots);
  for (const match of source.matchAll(/wx:for-item="([^"]+)"/g)) {
    localRoots.add(match[1].trim());
  }
  for (const match of source.matchAll(/wx:for-index="([^"]+)"/g)) {
    localRoots.add(match[1].trim());
  }
  const roots = new Set();
  const moustaches = Array.from(source.matchAll(/\{\{([^}]+)\}\}/g)).map((match) => match[1]);
  for (const expression of moustaches) {
    const withoutStrings = expression.replace(/"[^"]*"|'[^']*'/g, "");
    for (const match of withoutStrings.matchAll(/\b([A-Za-z_$][\w$]*)\b/g)) {
      const token = match[1];
      const previousChar = withoutStrings[match.index - 1];
      const nextChar = withoutStrings[match.index + token.length];
      if (localRoots.has(token) || previousChar === "." || nextChar === ":") {
        continue;
      }
      roots.add(token);
    }
  }
  return roots;
}

function checkWxmlTagBalance(source, pagePath) {
  const singleTags = new Set(["import", "include", "wxs"]);
  const stack = [];
  const tagPattern = /<\s*(\/?)([A-Za-z][\w-]*)([^>]*)>/g;
  for (const match of source.matchAll(tagPattern)) {
    const [, closingSlash, tagName, rawAttributes] = match;
    if (rawAttributes.trim().endsWith("/") || rawAttributes.includes("</") || singleTags.has(tagName)) {
      continue;
    }
    const before = source.slice(0, match.index);
    const line = before.split(/\r?\n/).length;
    if (closingSlash) {
      const opening = stack.pop();
      if (!opening) {
        fail(`${pagePath}.wxml closes </${tagName}> at line ${line} without a matching opening tag`);
        continue;
      }
      if (opening.tagName !== tagName) {
        fail(
          `${pagePath}.wxml closes </${tagName}> at line ${line}, but the latest unclosed tag is <${opening.tagName}> from line ${opening.line}`,
        );
      }
      continue;
    }
    stack.push({ tagName, line });
  }
  for (const opening of stack.reverse()) {
    fail(`${pagePath}.wxml leaves <${opening.tagName}> from line ${opening.line} unclosed`);
  }
}

function checkButtonLoadingDisabled(source, pagePath) {
  for (const { tag, line } of extractButtonTags(source)) {
    if (/\sloading=/.test(tag) && !/\sdisabled=/.test(tag)) {
      fail(`${pagePath}.wxml button at line ${line} has loading but no disabled guard`);
    }
  }
}

function checkButtonHasAction(source, pagePath) {
  for (const { tag, line } of extractButtonTags(source)) {
    if (!/\s(bindtap|catchtap|bind:tap|catch:tap|form-type|open-type)=/.test(tag)) {
      fail(`${pagePath}.wxml button at line ${line} has no tap handler, form-type, or open-type`);
    }
  }
}

function getMethodCalls(body) {
  return new Set(
    Array.from(body.matchAll(/\b(?:this\.)?([A-Za-z_$][\w$]*)\s*\(/g))
      .map((match) => match[1])
      .filter((name) => !["if", "for", "while", "switch", "catch", "function", "setData"].includes(name)),
  );
}

function methodHasObservableEffect(methodName, methodBodies, visited = new Set()) {
  if (visited.has(methodName)) {
    return false;
  }
  visited.add(methodName);
  const body = methodBodies.get(methodName);
  if (!body) {
    return false;
  }
  if (
    /\bwx\.\w+\s*\(/.test(body) ||
    /\bthis\.setData\s*\(/.test(body) ||
    /\bsetData\s*\(/.test(body) ||
    /\b(goBackOrHome|navigateByLink|addCartItem|clearCartItems|setSelectedAddress)\s*\(/.test(body)
  ) {
    return true;
  }
  for (const calledMethod of getMethodCalls(body)) {
    if (methodBodies.has(calledMethod) && methodHasObservableEffect(calledMethod, methodBodies, visited)) {
      return true;
    }
  }
  return false;
}

function checkTapHandlersHaveObservableEffect(handlers, methodBodies, pagePath) {
  for (const handler of handlers) {
    if (!methodHasObservableEffect(handler, methodBodies)) {
      fail(`${pagePath}.wxml binds "${handler}" but ${pagePath}.ts does not give it an observable effect`);
    }
  }
}

function checkNavigationToTabBar(tsSource, routeKey, routeValue, pagePath) {
  const escapedKey = routeKey.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const wrongNavigation = new RegExp(`wx\\.(navigateTo|redirectTo|reLaunch)\\s*\\(\\s*\\{[^}]*url\\s*:\\s*ROUTES\\.${escapedKey}`, "s");
  if (wrongNavigation.test(tsSource)) {
    fail(`${pagePath}.ts uses non-switchTab navigation for tabBar route ROUTES.${routeKey} (${routeValue})`);
  }
}

function checkSwitchTabToNonTabBar(tsSource, routeKey, routeValue, pagePath) {
  const escapedKey = routeKey.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const wrongSwitchTab = new RegExp(`wx\\.switchTab\\s*\\(\\s*\\{[^}]*url\\s*:\\s*ROUTES\\.${escapedKey}`, "s");
  if (wrongSwitchTab.test(tsSource)) {
    fail(`${pagePath}.ts uses switchTab for non-tabBar route ROUTES.${routeKey} (${routeValue})`);
  }
}

function checkNonTabPageBackNavigation(wxmlSource, methods, pagePath) {
  if (!wxmlSource.includes('bindtap="goBack"') && !wxmlSource.includes('catchtap="goBack"')) {
    fail(`${pagePath}.wxml is a non-tabBar page but does not expose a goBack tap target`);
  }
  if (!methods.has("goBack")) {
    fail(`${pagePath}.ts is a non-tabBar page but does not define goBack`);
  }
}

function checkFixedSafeHomeAction(wxmlSource, methods, pagePath) {
  if (!wxmlSource.includes("page-fixed-safe__home")) {
    return;
  }
  if (!wxmlSource.includes('bindtap="goHome"') && !wxmlSource.includes('catchtap="goHome"')) {
    fail(`${pagePath}.wxml shows page-fixed-safe__home but does not bind it to goHome`);
  }
  if (!methods.has("goHome")) {
    fail(`${pagePath}.ts shows page-fixed-safe__home but does not define goHome`);
  }
}

function checkDynamicLinksUseUnifiedNavigation(tsSource, wxmlSource, pagePath) {
  if (!/\sdata-link-(type|target)=/.test(wxmlSource)) {
    return;
  }
  if (!/\bnavigateByLink\s*\(/.test(tsSource)) {
    fail(`${pagePath}.wxml declares dynamic data-link-* targets but ${pagePath}.ts does not route them through navigateByLink`);
  }
}

function checkUnifiedNavigationCoverage() {
  const navigationSource = readText(navigationUtilPath);
  const requiredTargets = [
    "home",
    "products",
    "cart",
    "chat",
    "profile",
    "orders",
    "address",
  ];
  const requiredTypes = ["page", "product", "category", "policy", "contact", "phone", "wechat"];
  if (!/\bexport\s+function\s+navigateByLink\s*\(/.test(navigationSource)) {
    fail("miniprogram/utils/navigation.ts must export navigateByLink for dynamic decoration/service links");
  }
  for (const target of requiredTargets) {
    if (!new RegExp(`linkTarget\\s*===\\s*["']${target}["']`).test(navigationSource)) {
      fail(`navigateByLink must handle page linkTarget="${target}"`);
    }
  }
  for (const type of requiredTypes) {
    if (!new RegExp(`linkType\\s*===\\s*["']${type}["']`).test(navigationSource)) {
      fail(`navigateByLink must handle linkType="${type}"`);
    }
  }
  if (!/fallbackToast\s*\|\|\s*["']功能建设中["']/.test(navigationSource)) {
    fail('navigateByLink must keep a fallback toast for linkType="none" or unknown targets');
  }
  if (/linkType\s*===\s*["']contact["']\s*\|\|\s*linkType\s*===\s*["']none["']/.test(navigationSource)) {
    fail('navigateByLink must not route linkType="none" to customer service; use contact for that behavior');
  }
}

// wx.request 超时守卫：必须显式设置 timeout，且 REQUEST_TIMEOUT_MS 必须出现在兜底位置。
// 允许单请求覆盖写法 `timeout: options.timeoutMs ?? REQUEST_TIMEOUT_MS`（AI 聊天等慢接口需要），
// 但不允许完全不设 timeout，也不允许只有覆盖值而没有 REQUEST_TIMEOUT_MS 兜底——那会架空默认超时。
const REQUEST_TIMEOUT_GUARD_PATTERN =
  /\bwx\.request\s*\(\s*\{[\s\S]*\btimeout\s*:\s*(?:\w+\.timeoutMs\s*\?\?\s*)?REQUEST_TIMEOUT_MS/;

// 守卫回归固定件：把上述正则对下列写法的行为钉死（2 组正例 + 3 组反例），
// 防止后续放宽覆盖面时把守卫架空——尤其是「完全没有 timeout」必须继续被拦截。
const REQUEST_TIMEOUT_GUARD_FIXTURES = [
  {
    name: "固定默认超时",
    source: "wx.request({\n  url,\n  timeout: REQUEST_TIMEOUT_MS,\n});",
    mustMatch: true,
  },
  {
    name: "单请求覆盖 + 默认兜底",
    source: "wx.request({\n  url,\n  timeout: options.timeoutMs ?? REQUEST_TIMEOUT_MS,\n});",
    mustMatch: true,
  },
  {
    name: "完全没有 timeout",
    source: "wx.request({\n  url,\n  method: \"GET\",\n});",
    mustMatch: false,
  },
  {
    name: "只有覆盖值没有默认兜底",
    source: "wx.request({\n  url,\n  timeout: options.timeoutMs,\n});",
    mustMatch: false,
  },
  {
    name: "键名写成 timeoutMs 而非 timeout",
    source: "wx.request({\n  url,\n  timeoutMs: 60000,\n});",
    mustMatch: false,
  },
];

function checkRequestTimeoutGuardRegression() {
  for (const fixture of REQUEST_TIMEOUT_GUARD_FIXTURES) {
    const matched = REQUEST_TIMEOUT_GUARD_PATTERN.test(fixture.source);
    if (matched === fixture.mustMatch) {
      continue;
    }
    const expected = fixture.mustMatch ? "放行" : "拦截";
    const actual = matched ? "放行" : "拦截";
    fail(`超时守卫正则回归失败：「${fixture.name}」期望${expected}，实际${actual}`);
  }
}

function checkUnifiedHttpRequestTimeout() {
  const transportSource = readText(transportServicePath);
  checkRequestTimeoutGuardRegression();
  if (!/\bconst\s+REQUEST_TIMEOUT_MS\s*=\s*\d+/.test(transportSource)) {
    fail("miniprogram/services/transport.ts must define REQUEST_TIMEOUT_MS for wx.request timeout guard");
  }
  if (!REQUEST_TIMEOUT_GUARD_PATTERN.test(transportSource)) {
    fail("miniprogram/services/transport.ts wx.request must set timeout: REQUEST_TIMEOUT_MS");
  }
}

function checkPageUsingComponents(pagePath) {
  const pageJsonPath = path.join(miniappRoot, `${pagePath}.json`);
  const pageConfig = readJson(pageJsonPath);
  const usingComponents = pageConfig.usingComponents ?? {};
  for (const [componentName, componentPath] of Object.entries(usingComponents)) {
    if (typeof componentPath !== "string" || !componentPath) {
      fail(`${pagePath}.json declares invalid usingComponents entry for ${componentName}`);
      continue;
    }
    const componentBasePath = componentPath.startsWith("/")
      ? path.join(miniappRoot, componentPath.slice(1))
      : path.resolve(path.dirname(pageJsonPath), componentPath);
    for (const extension of pageExtensions) {
      const componentFilePath = `${componentBasePath}${extension}`;
      if (!fs.existsSync(componentFilePath)) {
        fail(
          `${pagePath}.json usingComponents.${componentName} points to missing component file: ${toPosix(
            path.relative(root, componentFilePath),
          )}`,
        );
      }
    }
    const componentJsonPath = `${componentBasePath}.json`;
    if (fs.existsSync(componentJsonPath) && readJson(componentJsonPath).component !== true) {
      fail(`${pagePath}.json usingComponents.${componentName} must point to a component with component=true`);
    }
  }
}

function checkDemoSessionFallbackPersists() {
  const appSource = readText(appTsPath);
  const authSource = readText(authServicePath);
  const httpSource = readText(httpServicePath);
  const sessionUtilSource = readText(sessionUtilPath);
  const sessionStoreSource = readText(sessionStorePath);
  if (!/\bpersistDemoMiniappSession\b/.test(authSource) || !/\bpersistDemoMiniappSession\s*\(/.test(sessionStoreSource)) {
    fail("Miniapp auth must keep persistDemoMiniappSession for explicit developer demo sessions");
  }
  if (/ensureMiniappSession[\s\S]*catch\s*\{[\s\S]*\bpersistDemoMiniappSession\s*\(/.test(authSource)) {
    fail("miniprogram auth must not persist demo session when login request fails");
  }
  if (/onLaunch[\s\S]*catch\s*\{[\s\S]*\bpersistDemoMiniappSession\s*\(/.test(appSource)) {
    fail("miniprogram/app.ts onLaunch login fallback must not persist demo session automatically");
  }
  if (!/isUsableMiniappSession\s*\(\s*storedSession\s*\)/.test(authSource)) {
    fail("miniprogram auth ensureMiniappSession must not reuse expired or demo sessions");
  }
  if (!/isUsableMiniappSession\s*\(\s*session\s*\)[\s\S]*Authorization/.test(httpSource)) {
    fail("miniprogram/services/http.ts must inject Authorization only for usable sessions");
  }
  if (!/isUsableMiniappSession\s*\(\s*session\s*\)/.test(sessionUtilSource)) {
    fail("miniprogram/utils/session.ts isMiniappLoggedIn must require a usable Bearer session");
  }
}

function checkStorefrontAuthContract() {
  const authSource = readText(authServicePath);
  const httpSource = readText(httpServicePath);
  const sessionStoreSource = readText(sessionStorePath);
  const transportSource = readText(transportServicePath);
  const authSources = [authSource, httpSource, sessionStoreSource];
  const sources = [...authSources, transportSource];
  if (!authSources.every((source) => /accessToken/.test(source))) {
    fail("storefront auth sources must define and use accessToken");
  }
  if (!/tokenType/.test(sessionStoreSource) || !/expiresIn/.test(sessionStoreSource) || !/expiresAt/.test(sessionStoreSource)) {
    fail("session-store.ts must persist tokenType, expiresIn and expiresAt");
  }
  if (!/Authorization\s*=\s*`\$\{session\.tokenType\} \$\{session\.accessToken\}`/.test(httpSource)) {
    fail("http.ts must inject Authorization with the persisted Bearer token");
  }
  if (!/statusCode\s*===\s*401/.test(httpSource) || !/forceRefresh\s*:\s*true/.test(httpSource)) {
    fail("http.ts must force a session refresh after the first 401");
  }
  if (!/retryOnUnauthorized\s*:\s*false/.test(httpSource)) {
    fail("http.ts must disable unauthorized retry on the replayed request");
  }
  if (/from\s+["']\.\/http["']/.test(authSource)) {
    fail("auth.ts must use transport.ts instead of importing the authenticated http client");
  }
  if (sources.some((source) => /x-miniapp-user-id/.test(source))) {
    fail("Miniapp runtime services must not send x-miniapp-user-id");
  }
}

function checkDevtoolsSmokeRedaction() {
  const smokeSource = readText(devtoolsSmokePath);
  if (!/hasAccessToken/.test(smokeSource) || !/safeLogin/.test(smokeSource)) {
    fail("DevTools smoke must expose only safe token metadata in its report");
  }
  if (/runtimeResult\.(userId|openid|storage)/.test(smokeSource)) {
    fail("DevTools smoke must not copy user identity or raw storage into its report");
  }
  if (!/summary:\s*check\.summary/.test(smokeSource)) {
    fail("DevTools smoke report must use response summaries instead of raw payloads");
  }
}

function checkDevtoolsProbesUseBearer() {
  for (const probePath of devtoolsAuthProbePaths) {
    const probeSource = readText(probePath);
    if (/x-miniapp-user-id/.test(probeSource)) {
      fail(`${path.basename(probePath)} must not send x-miniapp-user-id`);
    }
    if (!/Authorization/.test(probeSource) || !/accessToken/.test(probeSource)) {
      fail(`${path.basename(probePath)} must use a Bearer access token`);
    }
  }
}

function checkProductDetailDoesNotUseDemoFallback() {
  const productDetailSource = readText(productDetailPagePath);
  const productServiceSource = readText(productServicePath);
  const checkoutSource = readText(checkoutPagePath);
  if (/getProductDetail\s*\([^)]*\)\s*\?\?\s*getProductById\s*\(\s*["']p_001["']\s*\)/.test(productDetailSource)) {
    fail("product-detail must not replace a missing remote product with demo product p_001");
  }
  if (/const\s+productId\s*=[^;]*["']p_001["']/.test(productDetailSource)) {
    fail("product-detail must not default a missing route id to demo product p_001");
  }
  if (!/isWrappedCatalogProduct\s*\(\s*response\s*\)[\s\S]*return\s+response\.data\s*\?\s*normalizeRemoteProduct\s*\(\s*response\.data\s*\)\s*:\s*null/.test(productServiceSource)) {
    fail("products service must return null for a wrapped product-detail response with data=null");
  }
  if (!/\bvalidateCartProducts\s*\(/.test(checkoutSource) || !/\bgetProductDetail\s*\([^)]*forceRefresh\s*:\s*true/.test(checkoutSource)) {
    fail("checkout must validate cart products with a fresh product-detail lookup before createOrder");
  }
  if (!/const\s+cartStillValid\s*=\s*await\s+this\.validateCartProducts\s*\(\s*cartItems\s*\)[\s\S]*if\s*\(\s*!cartStillValid\s*\)[\s\S]*return[\s\S]*createOrder\s*\(/.test(checkoutSource)) {
    fail("checkout must stop before createOrder when cart product validation fails");
  }
}

function checkOrderDetailActions() {
  const orderDetailSource = readText(orderDetailPagePath);
  const methodBodies = extractPageMethodBodies(orderDetailSource);
  if (
    !/goOrders\(\)\s*\{[\s\S]*?wx\.reLaunch\s*\(\s*\{\s*url\s*:\s*ROUTES\.orders\s*\}/.test(
      orderDetailSource,
    )
  ) {
    fail("order-detail goOrders must use wx.reLaunch({ url: ROUTES.orders }) for deterministic non-tab navigation");
  }
  for (const methodName of ["goOrders", "goChat"]) {
    const body = methodBodies.get(methodName) || "";
    if (
      !/this\.data\.loading/.test(body) ||
      !/this\.data\.paying/.test(body) ||
      !/this\.data\.cancelling/.test(body)
    ) {
      fail(`order-detail ${methodName} must guard loading/paying/cancelling before navigation`);
    }
  }
}

const failures = [];
const appConfig = readJson(appJsonPath);
const appPages = new Set(appConfig.pages ?? []);
const tabBarPages = new Set((appConfig.tabBar?.list ?? []).map((item) => item.pagePath));

checkUnifiedHttpRequestTimeout();
checkDemoSessionFallbackPersists();
checkStorefrontAuthContract();
checkDevtoolsSmokeRedaction();
checkDevtoolsProbesUseBearer();
checkProductDetailDoesNotUseDemoFallback();
checkOrderDetailActions();
checkUnifiedNavigationCoverage();

for (const pagePath of appPages) {
  for (const extension of pageExtensions) {
    const filePath = path.join(miniappRoot, `${pagePath}${extension}`);
    if (!fs.existsSync(filePath)) {
      fail(`missing page file: ${toPosix(path.relative(root, filePath))}`);
    }
  }
  checkPageUsingComponents(pagePath);
}

for (const tabPage of tabBarPages) {
  if (!appPages.has(tabPage)) {
    fail(`tabBar page is not registered in app.json pages: ${tabPage}`);
  }
}

const routes = extractRoutes(readText(routesPath));
for (const { key, route } of routes) {
  const normalized = route.replace(/^\//, "");
  if (!appPages.has(normalized)) {
    fail(`ROUTES.${key} points to unregistered page: ${route}`);
  }
}

const routeByKey = new Map(routes.map((item) => [item.key, item.route.replace(/^\//, "")]));
const tabRouteKeys = Array.from(routeByKey.entries())
  .filter(([, route]) => tabBarPages.has(route))
  .map(([key, route]) => ({ key, route }));
const nonTabRouteKeys = Array.from(routeByKey.entries())
  .filter(([, route]) => !tabBarPages.has(route))
  .map(([key, route]) => ({ key, route }));

for (const pagePath of appPages) {
  const tsPath = path.join(miniappRoot, `${pagePath}.ts`);
  const wxmlPath = path.join(miniappRoot, `${pagePath}.wxml`);
  if (!fs.existsSync(tsPath) || !fs.existsSync(wxmlPath)) {
    continue;
  }
  const tsSource = readText(tsPath);
  const wxmlSource = readText(wxmlPath);
  const methods = extractPageMethods(tsSource);
  const methodBodies = extractPageMethodBodies(tsSource);
  const dataKeys = extractPageDataKeys(tsSource);
  const handlers = extractWxmlHandlers(wxmlSource);
  checkWxmlTagBalance(wxmlSource, pagePath);
  checkButtonHasAction(wxmlSource, pagePath);
  checkButtonLoadingDisabled(wxmlSource, pagePath);
  checkFixedSafeHomeAction(wxmlSource, methods, pagePath);
  checkDynamicLinksUseUnifiedNavigation(tsSource, wxmlSource, pagePath);
  for (const handler of handlers) {
    if (!methods.has(handler)) {
      fail(`${pagePath}.wxml binds "${handler}" but ${pagePath}.ts does not define it`);
    }
  }
  checkTapHandlersHaveObservableEffect(handlers, methodBodies, pagePath);
  for (const root of extractWxmlDataRoots(wxmlSource)) {
    if (!dataKeys.has(root)) {
      fail(`${pagePath}.wxml references "{{${root}}}" but ${pagePath}.ts data does not initialize it`);
    }
  }
  for (const { key, route } of tabRouteKeys) {
    checkNavigationToTabBar(tsSource, key, route, pagePath);
  }
  for (const { key, route } of nonTabRouteKeys) {
    checkSwitchTabToNonTabBar(tsSource, key, route, pagePath);
  }
  if (!tabBarPages.has(pagePath)) {
    checkNonTabPageBackNavigation(wxmlSource, methods, pagePath);
  }
}

if (failures.length) {
  console.error(failures.map((item) => `- ${item}`).join("\n"));
  process.exit(1);
}

console.log(`Miniapp static checks passed: ${appPages.size} pages, ${routes.length} routes.`);
