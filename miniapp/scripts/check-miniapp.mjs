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
const productsPagePath = path.join(miniappRoot, "pages", "products", "index");
const checkoutPagePath = path.join(miniappRoot, "pages", "checkout", "index.ts");
const ordersPagePath = path.join(miniappRoot, "pages", "orders", "index");
const orderDetailPagePath = path.join(miniappRoot, "pages", "order-detail", "index.ts");
const rechargePagePath = path.join(miniappRoot, "pages", "recharge", "index");
const pageExtensions = [".json", ".ts", ".wxml", ".wxss"];
// 群内登记页的日期起点、可选时段与当天标记必须按当前北京时间重建（见 checkRegistrationScheduleRefresh）。
const groupRegistrationPagePath = path.join(miniappRoot, "pages", "group-registration", "index.ts");
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
  // 必须锁定行首的 Page 定义（可选泛型）：未锚定的 Page\s*\( 会误匹配 listXxxPage({ 之类的调用，导致方法扫描区域从调用处开始。
  const pageBody = source.match(/^\s*Page(?:<[^>]+>)?\s*\(\s*\{([\s\S]*)\}\s*\)\s*;?\s*$/m);
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

// data 支持“...buildXxx()”批量初始化字段：从同文件函数的返回对象里解析键名，
// 仍能守住 WXML 引用，而不是对带展开的页面直接豁免。
function extractFunctionReturnKeys(source, functionName) {
  const functionStart = source.search(new RegExp(`function\\s+${functionName}\\s*\\(`));
  if (functionStart === -1) {
    return [];
  }
  const returnMatch = source.slice(functionStart).match(/return\s*\{/);
  if (!returnMatch) {
    return [];
  }
  const openBraceIndex = functionStart + returnMatch.index + returnMatch[0].lastIndexOf("{");
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
    return [];
  }
  const body = source.slice(openBraceIndex + 1, endIndex);
  return Array.from(body.matchAll(/^\s*([A-Za-z_$][\w$]*)\s*:/gm)).map((match) => match[1]);
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
  const keys = new Set(
    Array.from(dataBody.matchAll(/^\s*([A-Za-z_$][\w$]*)\s*:/gm)).map((match) => match[1])
  );
  for (const match of dataBody.matchAll(/^\s*\.\.\.\s*([A-Za-z_$][\w$]*)\s*\(/gm)) {
    for (const key of extractFunctionReturnKeys(source, match[1])) {
      keys.add(key);
    }
  }
  return keys;
}

function extractWxmlHandlers(source) {
  const attrs = eventAttributes.join("|").replaceAll(":", "\\:");
  const pattern = new RegExp(`(?:${attrs})="([^"]+)"`, "g");
  return Array.from(source.matchAll(pattern))
    .map((match) => match[1].trim())
    .filter(Boolean)
    .filter((handler) => !handler.startsWith("{{"));
}

function scanWxmlTags(source) {
  const tags = [];
  const tagStartPattern = /<\s*(\/?)\s*([A-Za-z][\w-]*)/g;
  let match = tagStartPattern.exec(source);
  while (match) {
    const startIndex = match.index;
    const attributesStartIndex = tagStartPattern.lastIndex;
    let index = attributesStartIndex;
    let quote = "";
    let endIndex = -1;
    for (; index < source.length; index += 1) {
      const char = source[index];
      if (quote) {
        if (char === quote) {
          quote = "";
        }
        continue;
      }
      if (char === '"' || char === "'") {
        quote = char;
        continue;
      }
      if (char === ">") {
        endIndex = index;
        break;
      }
    }
    if (endIndex === -1) {
      break;
    }
    tags.push({
      closingSlash: match[1],
      tagName: match[2],
      rawAttributes: source.slice(attributesStartIndex, endIndex),
      text: source.slice(startIndex, endIndex + 1),
      line: source.slice(0, startIndex).split(/\r?\n/).length,
    });
    tagStartPattern.lastIndex = endIndex + 1;
    match = tagStartPattern.exec(source);
  }
  return tags;
}

function extractButtonTags(source) {
  return scanWxmlTags(source)
    .filter((tag) => tag.tagName === "button" && !tag.closingSlash)
    .map((tag) => ({ tag: tag.text, line: tag.line }));
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
  for (const tag of scanWxmlTags(source)) {
    const { closingSlash, tagName, rawAttributes, line } = tag;
    if (rawAttributes.trim().endsWith("/") || rawAttributes.includes("</") || singleTags.has(tagName)) {
      continue;
    }
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

// 图片加载失败必须有降级回调：首页/商品/购物车/详情统一避免破图与空白占位。
function checkImageErrorFallback(source, pagePath) {
  for (const match of source.matchAll(/<image\b[^>]*?\/?>/gs)) {
    if (/\bbinderror\s*=/.test(match[0])) {
      continue;
    }
    const lineNumber = source.slice(0, match.index).split("\n").length;
    fail(`${pagePath}.wxml:${lineNumber} 的 <image> 缺少 binderror 加载失败降级`);
  }
}

// 表单页输入控件必须带常驻标签：placeholder 不能独自承担字段含义。
const LABELED_FORM_PAGES = new Set([
  "pages/checkout/index",
  "pages/address/index",
  "pages/group-registration/index",
]);

const FORBIDDEN_CUSTOMER_COPY = [
  { text: "真实登录态", hint: "应改为顾客可理解的登录或微信身份文案" },
  { text: "演示会话", hint: "应改为体验账号等顾客语言" },
  { text: "VIP 会员", hint: "会员等级必须来自 memberSummary 配置" },
  { text: "8888 6666", hint: "不得展示虚假会员编号" },
  { text: "MVP 模拟支付", hint: "订单支付方式必须使用顾客可理解的业务文案" },
  { text: "模拟支付", hint: "不得向顾客暴露开发环境的模拟支付口径" },
  { text: "与客服通话", hint: "客服页是文字沟通，不得暗示电话能力；电话入口在个人中心" }
];

// 顾客可见文案不得泄露实现细节，也不得用硬编码伪装会员等级或编号。
function checkCustomerFacingCopy(source, pagePath) {
  for (const item of FORBIDDEN_CUSTOMER_COPY) {
    if (source.includes(item.text)) {
      fail(`${pagePath} 包含不应面向顾客展示的文案“${item.text}”：${item.hint}`);
    }
  }
}

function checkFormFieldLabels(source, pagePath) {
  if (!LABELED_FORM_PAGES.has(pagePath)) {
    return;
  }
  const controlCount = Array.from(source.matchAll(/<(?:input|textarea)\b/g)).length;
  const labelCount = Array.from(source.matchAll(/class="(?:form-field__label|quantity-field__label)[^"]*"/g)).length;
  if (controlCount > 0 && labelCount < controlCount) {
    fail(`${pagePath}.wxml 有 ${controlCount} 个输入控件但只有 ${labelCount} 个常驻字段标签`);
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
  // 返回控件必须复用全局 .page-nav-back：商品详情曾单独实现 88rpx 圆角方块并覆盖圆形容器，导致与其它子页不一致。
  if (!/class="[^"]*\bpage-nav-back\b[^"]*"/.test(wxmlSource)) {
    fail(`${pagePath}.wxml is a non-tabBar page but does not use the shared page-nav-back control`);
  }
}

function checkNoHeaderHomeControl(wxmlSource, pagePath) {
  if (!wxmlSource.includes("page-fixed-safe__home")) {
    return;
  }
  // 商品目录曾用无图标、无文字的主页控件占位，真机渲染为不可见点击区，且与自定义 TabBar 的首页入口重复。
  fail(`${pagePath}.wxml renders page-fixed-safe__home; use the custom tab bar for home navigation instead of a hidden header control`);
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

// 门店自提地址唯一来源是 miniprogram/config/shop.ts：页面不得写死其它地址，也不得出现品牌错字。
function listMiniappSourceFiles(dir = miniappRoot) {
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name === "miniprogram_npm") {
      continue;
    }
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...listMiniappSourceFiles(fullPath));
    } else if (/\.(ts|wxml|wxss|js|json)$/.test(entry.name)) {
      files.push(fullPath);
    }
  }
  return files;
}

function checkPickupAddressSourceOfTruth() {
  const shopConfigPath = path.join(miniappRoot, "config", "shop.ts");
  const canonicalMatch = /pickupAddress:\s*"([^"]+)"/.exec(readText(shopConfigPath));
  if (!canonicalMatch) {
    fail("miniprogram/config/shop.ts must define pickupAddress as the single source of truth");
    return;
  }
  const canonicalAddress = canonicalMatch[1];
  checkBackendPickupAddressSources(canonicalAddress);
  const addressPattern = /北京市[\u4e00-\u9fa5A-Za-z0-9]{4,}/g;
  for (const filePath of listMiniappSourceFiles()) {
    if (path.resolve(filePath) === path.resolve(shopConfigPath)) {
      continue;
    }
    const relative = toPosix(path.relative(root, filePath));
    const source = readText(filePath);
    if (source.includes("具体地址请联系客服确认")) {
      fail(`${relative} 不得包含后台占位自提地址文案，地址空值应回落 config/shop.ts`);
    }
    if (source.includes("云熙")) {
      fail(`${relative} 出现品牌错字「云熙」，应使用「芸熙」`);
    }
    for (const literal of source.match(addressPattern) ?? []) {
      if (!literal.startsWith(canonicalAddress)) {
        fail(`${relative} 写死了非门店自提地址「${literal}」，请改用 config/shop.ts 的 pickupAddress`);
      }
    }
  }
}

// 后台默认配置与小程序门店地址必须指向同一家店，避免后台占位文案成为闪送报价起点。
function checkBackendPickupAddressSources(canonicalAddress) {
  const repoTargets = [
    {
      relative: "backend/app/models/config.py",
      pattern: /DEFAULT_PICKUP_ADDRESS\s*=\s*"([^"]+)"/,
    },
    {
      relative: "backend/web/admin/src/services/shopSettings.ts",
      pattern: /pickupAddress:\s*"([^"]+)"/,
    },
  ];
  for (const target of repoTargets) {
    const filePath = path.resolve(root, "..", target.relative);
    if (!fs.existsSync(filePath)) {
      fail(`缺少门店地址来源文件 ${target.relative}`);
      continue;
    }
    const matched = target.pattern.exec(readText(filePath));
    if (!matched || matched[1] !== canonicalAddress) {
      fail(`${target.relative} 的门店自提地址默认值必须与 config/shop.ts 一致`);
    }
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
  const orderSummarySource = readText(path.join(miniappRoot, "utils", "order-summary.ts"));
  if (!orderSummarySource.includes("formatPaymentMethodText") || !orderSummarySource.includes('return "门店确认"')) {
    fail("order payment method must map mock to customer-facing \"门店确认\"");
  }
  if (!orderDetailSource.includes("formatPaymentMethodText(order.paymentMethod)")) {
    fail("order-detail must render payment method through formatPaymentMethodText");
  }
}

function checkOrderFulfillmentPresentation() {
  const ordersWxml = readText(`${ordersPagePath}.wxml`);
  const orderDetailWxml = readText(`${orderDetailPagePath.replace(/\.ts$/, "")}.wxml`);
  if (!/fulfillmentTypeText/.test(ordersWxml) || !/receiverLabel/.test(ordersWxml)) {
    fail("orders list must expose fulfillment method and fulfillment-specific contact label");
  }
  if (!/wx:if="\{\{order\.hasDeliveryFee\}\}"[^>]*order-total-row--delivery/.test(orderDetailWxml)) {
    fail("order-detail delivery fee row must only render for Beijing delivery orders");
  }
  if (!/order-row--pickup-address/.test(orderDetailWxml) || !/order\.pickupAddress/.test(orderDetailWxml)) {
    fail("order-detail pickup orders must expose the snapshotted pickup address");
  }
}

function checkCatalogHeadlineAndScheduleConsistency() {
  const productsWxml = readText(`${productsPagePath}.wxml`);
  const productsTs = readText(`${productsPagePath}.ts`);
  if (/products-heading__service/.test(productsWxml)) {
    fail("products heading must not render a non-interactive pricing chip");
  }
  if (!/按销量排序/.test(productsWxml)) {
    fail("products heading must state the real sort basis");
  }
  for (const decorative of ["人气汇聚", "匠心手作", "麦香现烤", "层层甜蜜", "生活美学"]) {
    if (productsTs.includes(decorative)) {
      fail(`products page must not invent marketing subtitles: ${decorative}`);
    }
  }
  const checkoutTs = readText(checkoutPagePath);
  if (!/syncExpectTimeSchedule\(/.test(checkoutTs) || !/resolveCheckoutSchedule/.test(checkoutTs)) {
    fail("checkout must rebuild schedule pickers from the submitted expectTime");
  }
}

function checkCatalogIncrementalLoading() {
  const productsWxml = readText(`${productsPagePath}.wxml`);
  const productsTs = readText(`${productsPagePath}.ts`);
  if (!/bindscrolltolower="loadMoreProducts"/.test(productsWxml)) {
    fail("products catalog scroll-view must trigger loadMoreProducts when scrolled to the bottom");
  }
  if (!/bindscrolltolower="loadMoreSearchResults"/.test(productsWxml)) {
    fail("products search scroll-view must trigger loadMoreSearchResults when scrolled to the bottom");
  }
  if (!/wx:if="\{\{searchHasMore\}\}"[^>]*bindtap="loadMoreSearchResults"/.test(productsWxml)) {
    fail("products search must keep a manual load-more fallback while results remain hidden");
  }
  if (!/const CATALOG_PAGE_SIZE = 12;/.test(productsTs)) {
    fail("products catalog must request a bounded first page instead of the full catalog");
  }
  if (!/const SEARCH_PAGE_SIZE = 30;/.test(productsTs)) {
    fail("products search must request 30 items per server page (M-20260913-141)");
  }
  if (/FULL_CATALOG_LIMIT|allProducts|matchedProducts/.test(productsTs)) {
    fail(
      "products page must not keep or locally refilter a full catalog snapshot; search must stay server-side"
    );
  }
  if (
    !/keyword:\s*activeKeyword/.test(productsTs) ||
    !/searchMatchCount:\s*page\.meta\.total/.test(productsTs) ||
    !/searchRenderedCount:\s*globalSearchResults\.length/.test(productsTs) ||
    !/searchHasMore:\s*page\.meta\.hasMore/.test(productsTs)
  ) {
    fail("products search must page on the server and expose the server total, rendered count and hasMore");
  }
  if (
    !/offset:\s*this\.data\.searchOffset/.test(productsTs) ||
    !/offset:\s*this\.data\.catalogOffset/.test(productsTs)
  ) {
    fail("products load-more must continue from the server-reported offset instead of the rendered list length");
  }
  if (!/catalogOffset:\s*page\.meta\.offset \+ page\.meta\.limit/.test(productsTs)) {
    fail("products catalog must advance its offset from the server meta, not from the deduped list length");
  }
  if (
    !/scroll-into-view="\{\{searchScrollAnchor\}\}"/.test(productsWxml) ||
    !/id="products-search-top"/.test(productsWxml)
  ) {
    fail("products search panel must scroll back to its top anchor when the keyword changes");
  }
  if (
    !/scroll-into-view="\{\{catalogScrollAnchor\}\}"/.test(productsWxml) ||
    !/id="products-catalog-top"/.test(productsWxml)
  ) {
    fail("products catalog must scroll back to its top anchor when the category changes");
  }
  const searchResetCalls = productsTs.match(/resetSearchScrollPosition\(\)/g) || [];
  const catalogResetCalls = productsTs.match(/resetCatalogScrollPosition\(\)/g) || [];
  if (searchResetCalls.length < 2 || catalogResetCalls.length < 2) {
    fail("products page must define and invoke the scroll reset helpers for search and catalog");
  }
}

function checkRechargeRecordsEmptyState() {
  const rechargeWxml = readText(`${rechargePagePath}.wxml`);
  const emptyMatch = rechargeWxml.match(/<view[^>]*records-empty[^>]*>([\s\S]*?)<\/view>/);
  if (!emptyMatch) {
    fail("recharge records empty state must render a records-empty container");
  }
  const emptyBlock = emptyMatch[1];
  if (!/yunxi-state__title/.test(emptyBlock) || !/yunxi-state__hint/.test(emptyBlock)) {
    fail("recharge records empty state must use the unified yunxi-state title and hint structure");
  }
  if (!/充值记录/.test(rechargeWxml)) {
    fail("recharge page must keep the records section heading");
  }
}

function checkProductListCacheKeyIncludesLimit() {
  const productsTs = readText(productServicePath);
  const keyMatch = productsTs.match(/function buildProductsCacheKey[\s\S]*?\n}/);
  if (!keyMatch) {
    fail("products service must keep buildProductsCacheKey for list caching");
    return;
  }
  if (!/limit:\s*options\.limit/.test(keyMatch[0])) {
    fail("products list cache key must include limit: 首页货架/购物车推荐/详情关联限流不同，复用同一缓存会导致条数漂移");
  }
  if (!/offset:\s*options\.offset/.test(keyMatch[0]) || !/keyword:\s*options\.keyword/.test(keyMatch[0])) {
    fail("products list cache key must include offset and keyword: 分页与搜索复用同一缓存会导致串页");
  }
}

function checkGroupRegistrationDeliveryCopy() {
  const registrationWxml = readText(path.join(miniappRoot, "pages", "group-registration", "index.wxml"));
  if (registrationWxml.includes("门店配送")) {
    fail("群内登记页不得把北京闪送写成“门店配送”，两者运费与责任主体不同");
  }
  if (!registrationWxml.includes("北京闪送")) {
    fail("群内登记页配送方式必须使用“北京闪送”口径");
  }
  if (
    !registrationWxml.includes("delivery-fee-hint") ||
    !registrationWxml.includes("运费按收货地址实测") ||
    !registrationWxml.includes("由顾客承担")
  ) {
    fail("群内登记页选择闪送时必须说明运费按地址实测且由顾客承担");
  }
}

function checkRegistrationScheduleRefresh() {
  const registrationTs = readText(groupRegistrationPagePath);
  if (!/resolveCheckoutSchedule\(/.test(registrationTs)) {
    fail(
      "群内登记页必须用 resolveCheckoutSchedule 重建可选日期与时段，不得沿用模块加载时的旧时间快照"
    );
  }
  if (!/onShow\s*\(/.test(registrationTs)) {
    fail("群内登记页必须在 onShow 按当前北京时间重建可选时间，跨过 17:00 截单点后不得保留旧日期起点");
  }
  if (!/REGISTRATION_BUSINESS_HOURS/.test(registrationTs)) {
    fail("群内登记页的营业时段必须来自单一常量，禁止在多个方法里散落硬编码");
  }
}

function checkHomePromiseCardReadability() {
  const homeWxml = readText(path.join(miniappRoot, "pages", "home", "index.wxml"));
  const homeWxss = readText(path.join(miniappRoot, "pages", "home", "index.wxss"));
  if (!homeWxml.includes("当天订单 17:00 截单")) {
    fail("首页服务承诺必须声明真实截单时间“当天订单 17:00 截单”");
  }
  if (homeWxml.includes("17:00 前咨询")) {
    fail("首页服务承诺不得把截单规则写成“前咨询”");
  }
  const descMatch = homeWxss.match(/\.shop-promise-desc\s*\{([\s\S]*?)\n}/);
  if (!descMatch) {
    fail("home page must keep .shop-promise-desc for shop promise copy");
    return;
  }
  const descBlock = descMatch[1];
  if (/white-space:\s*nowrap/.test(descBlock)) {
    fail("首页服务承诺说明不得单行 nowrap 截断，关键规则必须完整可读");
  }
  const descFont = Number.parseFloat((descBlock.match(/font-size:\s*(\d+(?:\.\d+)?)rpx/) || [])[1] || "0");
  if (descFont < 20) {
    fail(`首页服务承诺说明字号过小：${descFont}rpx（下限 20rpx）`);
  }
  if (!/-webkit-line-clamp:\s*2/.test(descBlock)) {
    fail("首页服务承诺说明必须允许两行展示");
  }
}

function checkProductDetailFooterSpace() {
  const detailWxss = readText(path.join(miniappRoot, "pages", "product-detail", "index.wxss"));
  const pageMatch = detailWxss.match(/\.detail-page\s*\{([\s\S]*?)\n}/);
  if (!pageMatch) {
    fail("product detail page must keep the .detail-page content container");
    return;
  }
  const paddingBottom = pageMatch[1].match(/padding-bottom:\s*([^;]+);/);
  if (!paddingBottom) {
    fail("商品详情内容区缺少底部留白，固定操作栏会遮挡最后一段内容");
    return;
  }
  if (!/safe-area-inset-bottom/.test(paddingBottom[1])) {
    fail("商品详情底部留白必须叠加 env(safe-area-inset-bottom)，否则无安全区机型会留大片空白");
  }
}

// 商品详情悬浮导航栏在滚动后必须切实底，否则正文会穿透到状态栏与返回控件下方形成文字重叠。
function checkProductDetailScrollNav() {
  const detailDir = path.join(miniappRoot, "pages", "product-detail");
  const detailWxml = readText(path.join(detailDir, "index.wxml"));
  const detailTs = readText(path.join(detailDir, "index.ts"));
  const detailWxss = readText(path.join(detailDir, "index.wxss"));
  if (!detailWxml.includes('bindscroll="onScroll"')) {
    fail("商品详情滚动容器必须绑定 bindscroll=\"onScroll\"，用于切换悬浮栏实底状态");
  }
  if (!detailWxml.includes("detail-nav--solid")) {
    fail("商品详情悬浮栏必须按滚动状态切换 detail-nav--solid");
  }
  if (!detailTs.includes("navSolid") || !/onScroll\s*\(/.test(detailTs)) {
    fail("商品详情页面必须维护 navSolid 状态并在 onScroll 中更新");
  }
  const navMatch = detailWxss.match(/\.detail-nav\s*\{([\s\S]*?)\n}/);
  if (!navMatch) {
    fail("product detail page must keep .detail-nav for transparent/solid switching");
    return;
  }
  if (/transition:[^;]*background/.test(navMatch[1])) {
    fail("商品详情悬浮栏背景色不得参与过渡动画，DevTools 与低端机会读到半透明中间值");
  }
  const solidMatch = detailWxss.match(/\.detail-nav\.detail-nav--solid\s*\{([\s\S]*?)\n}/);
  if (!solidMatch) {
    fail("product detail page must keep .detail-nav.detail-nav--solid");
    return;
  }
  if (!/background:\s*#/.test(solidMatch[1])) {
    fail("商品详情滚动后的悬浮栏必须使用不透明背景，透明背景会让正文与状态栏文字重叠");
  }
  // 沉浸态标题压在商家上传的商品大图上，明暗不可控：必须有自带底衬，不能依赖图片恰好够浅。
  const immersiveTitleMatch = detailWxss.match(
    /\.detail-nav\s+\.page-fixed-safe__title\s*\{([\s\S]*?)\n}/
  );
  if (!immersiveTitleMatch) {
    fail("商品详情沉浸态必须为导航标题定义独立样式，否则深色标题直接压在深色商品图上不可读");
  } else {
    const immersiveTitleRule = immersiveTitleMatch[1];
    const titleSurfaceMatch = immersiveTitleRule.match(
      /background:\s*rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*(0(?:\.\d+)?|1(?:\.0+)?)\s*\)/
    );
    if (!titleSurfaceMatch || Number(titleSurfaceMatch[1]) < 0.8) {
      fail("商品详情沉浸态标题必须有不低于 0.8 不透明度的白色底衬，否则深色商品图上标题不可读");
    }
    if (/transition:[^;]*background/.test(immersiveTitleRule)) {
      fail("商品详情标题底衬不得参与过渡动画，DevTools 与低端机会读到半透明中间值");
    }
  }
  const solidTitleMatch = detailWxss.match(
    /\.detail-nav\.detail-nav--solid\s+\.page-fixed-safe__title\s*\{([\s\S]*?)\n}/
  );
  if (!solidTitleMatch || !/background:\s*transparent\s*;/.test(solidTitleMatch[1])) {
    fail("商品详情滚动实底后必须移除标题底衬，避免白底叠白底");
  }
}

// 商品卡购买说明必须完整可读：字号不小于 22rpx，且允许两行展示，不用单行 nowrap 截断关键运费口径。
function checkProductCardHintReadability() {
  const productsWxss = readText(path.join(miniappRoot, "pages", "products", "index.wxss"));
  const hintMatch = productsWxss.match(/\.product-hint\s*\{([\s\S]*?)\n}/);
  if (!hintMatch) {
    fail("products page must keep .product-hint for card purchase hints");
    return;
  }
  const hintBlock = hintMatch[1];
  const hintFont = Number.parseFloat((hintBlock.match(/font-size:\s*(\d+(?:\.\d+)?)rpx/) || [])[1] || "0");
  if (hintFont < 22) {
    fail(`商品卡购买说明字号过小：${hintFont}rpx（下限 22rpx）`);
  }
  if (/white-space:\s*nowrap/.test(hintBlock)) {
    fail("商品卡购买说明不得单行 nowrap 截断，长文案必须允许两行展示");
  }
  if (!/-webkit-line-clamp:\s*2/.test(hintBlock)) {
    fail("商品卡购买说明必须允许两行展示");
  }
  const homeWxss = readText(path.join(miniappRoot, "pages", "home", "index.wxss"));
  const homeTipMatch = homeWxss.match(/\.product-tip\s*\{([\s\S]*?)\n}/);
  if (!homeTipMatch) {
    fail("home page must keep .product-tip for card purchase hints");
    return;
  }
  const homeTipBlock = homeTipMatch[1];
  const homeTipFont = Number.parseFloat((homeTipBlock.match(/font-size:\s*(\d+(?:\.\d+)?)rpx/) || [])[1] || "0");
  if (homeTipFont < 22) {
    fail(`首页商品卡购买说明字号过小：${homeTipFont}rpx（下限 22rpx）`);
  }
  if (/white-space:\s*nowrap/.test(homeTipBlock)) {
    fail("首页商品卡购买说明不得单行 nowrap 截断");
  }
  if (!/max-width:\s*100%/.test(homeTipBlock)) {
    fail("首页商品卡购买说明必须限制在卡片宽度内换行");
  }
}

// 购物车状态胶囊只放短事实：长运费口径留在底部合计说明，否则会在窄胶囊内被省略号截断。
// “非卖品仅展示”商品只能查阅，不能被首页、商品列表、购物车推荐或详情页带入下单链路。
function checkDisplayOnlyProductGuard() {
  const bakeryTs = readText(path.join(miniappRoot, "utils", "bakery.ts"));
  const homeTs = readText(path.join(miniappRoot, "pages", "home", "index.ts"));
  const productsTs = readText(path.join(miniappRoot, "pages", "products", "index.ts"));
  const cartTs = readText(path.join(miniappRoot, "pages", "cart", "index.ts"));
  const detailTs = readText(path.join(miniappRoot, "pages", "product-detail", "index.ts"));
  const detailWxml = readText(path.join(miniappRoot, "pages", "product-detail", "index.wxml"));
  const homeWxml = readText(path.join(miniappRoot, "pages", "home", "index.wxml"));
  const productsWxml = readText(path.join(miniappRoot, "pages", "products", "index.wxml"));
  const cartWxml = readText(path.join(miniappRoot, "pages", "cart", "index.wxml"));
  const priceFn = bakeryTs.match(/export function getProductPriceText\s*\([\s\S]*?\n}/);
  if (!priceFn || !priceFn[0].includes("非卖品")) {
    fail("非卖品必须通过 getProductPriceText 输出“非卖品”，不得把同步占位价当作售价展示");
  }
  for (const [label, source] of [
    ["首页", homeTs],
    ["商品列表", productsTs],
    ["购物车推荐", cartTs],
  ]) {
    if (!source.includes("getProductPriceText")) {
      fail(`${label}价格必须走 getProductPriceText，非卖品不得显示虚拟占位价`);
    }
  }
  for (const [label, source] of [
    ["首页", homeWxml],
    ["商品列表", productsWxml],
    ["购物车推荐", cartWxml],
  ]) {
    if (!source.includes("is-display-only")) {
      fail(`${label}非卖品价格必须带 is-display-only 样式，避免与真实售价混淆`);
    }
  }
  if (!productsWxml.includes("product.stockText && !product.isDisplayOnly")) {
    fail("商品列表非卖品不得展示同步占位库存文案");
  }
  if (!detailTs.includes("getProductPriceText") || !detailTs.includes("isProductPurchasable(item)")) {
    fail("商品详情搭配推荐必须过滤非卖品并走 getProductPriceText，避免推荐位展示虚拟占位价");
  }
  if (!detailWxml.includes('wx:if="{{!isDisplayOnly}}" class="detail-meta"')) {
    fail("商品详情非卖品不得展示自提价与库存元信息");
  }
  if (!bakeryTs.includes("product.isPurchasable !== false")) {
    fail("商品工具必须把 isPurchasable=false 识别为仅供展示，不得按普通商品生成动作");
  }
  for (const [label, source] of [
    ["首页", homeTs],
    ["购物车推荐", cartTs],
    ["商品详情", detailTs],
  ]) {
    if (!source.includes("isPurchasable === false") && !source.includes("isProductPurchasable")) {
      fail(`${label}必须拦截 isPurchasable=false 商品，不允许加入购物车或立即购买`);
    }
  }
  if (!productsTs.includes("isPurchasable === false")) {
    fail("商品列表必须拦截 isPurchasable=false 商品，不允许快捷预订");
  }
  if (!detailWxml.includes("detail-display-only-card") || !detailWxml.includes("不提供直接购买")) {
    fail("商品详情必须为仅供展示商品说明不可购买，而不是继续显示履约与下单引导");
  }
}

function checkCartTagCopy() {
  const cartTs = readText(path.join(miniappRoot, "pages", "cart", "index.ts"));
  const cartWxml = readText(path.join(miniappRoot, "pages", "cart", "index.wxml"));
  const stockTextFn = cartTs.match(/function getCartStockText\s*\([\s\S]*?\n}/);
  if (!stockTextFn) {
    fail("cart page must keep getCartStockText for the item status chip");
    return;
  }
  if (stockTextFn[0].includes("getProductPurchaseHint")) {
    fail("购物车状态胶囊不得直接使用长购买提示（会被省略号截断），长运费口径应留在底部合计说明");
  }
  if (!stockTextFn[0].includes("getProductAvailabilityLabel")) {
    fail("购物车库存充足时应使用 getProductAvailabilityLabel 输出短事实标签");
  }
  if (!cartWxml.includes('wx:if="{{item.stockText}}"')) {
    fail("购物车状态胶囊必须按 stockText 是否为空条件渲染");
  }
}

// 购物车推荐卡复用统一动作口径：现做商品走预订、现货配件加入购物车，提示语必须与动作一致。
function checkCartRecommendedActionCopy() {
  const cartTs = readText(path.join(miniappRoot, "pages", "cart", "index.ts"));
  const recommendFn = cartTs.match(/function toRecommendedProductView\s*\([\s\S]*?\n}/);
  if (!recommendFn) {
    fail("cart page must keep toRecommendedProductView for recommendation cards");
    return;
  }
  if (!recommendFn[0].includes("getProductActionLabel")) {
    fail("购物车推荐卡必须复用 getProductActionLabel，保持与首页和商品列表一致的动作文案");
  }
  if (!recommendFn[0].includes("getProductCardTip")) {
    fail("购物车推荐卡必须复用 getProductCardTip，避免长运费口径挤爆窄卡片");
  }
  if (!cartTs.includes("getProductAddToastLabel")) {
    fail("购物车推荐加购提示必须复用 getProductAddToastLabel，避免动作与提示口径不一致");
  }
  if (/wx\.showToast\(\{\s*title:\s*"已加入/.test(cartTs)) {
    fail("购物车加购提示不得写死文案，必须复用统一提示口径");
  }
}

// 收货地址不能只存行政区：旧数据要提示补充，新保存数据必须包含小区、楼栋或门牌号。
function checkAddressDetailCompleteness() {
  const addressUtil = readText(path.join(miniappRoot, "utils", "address.ts"));
  const addressBook = readText(path.join(miniappRoot, "utils", "address-book.ts"));
  const addressPage = readText(path.join(miniappRoot, "pages", "address", "index.ts"));
  const addressWxml = readText(path.join(miniappRoot, "pages", "address", "index.wxml"));
  if (!addressUtil.includes("isAddressDetailedEnough")) {
    fail("地址工具必须保留 isAddressDetailedEnough，禁止只填写行政区就保存");
  }
  if (!addressBook.includes("isAddressDetailedEnough(address)")) {
    fail("地址保存校验必须补充小区、楼栋或门牌号");
  }
  if (!addressPage.includes("needsDetailHint")) {
    fail("地址列表必须标记信息不完整的历史地址");
  }
  if (!addressWxml.includes("address-card-warning")) {
    fail("地址列表必须展示信息不完整提示");
  }
}

// 商品详情底部服务入口必须使用可辨识图标，不能继续用“询/购”单汉字充当占位图标。
function checkProductDetailServiceIcons() {
  const detailWxml = readText(path.join(miniappRoot, "pages", "product-detail", "index.wxml"));
  const detailWxss = readText(path.join(miniappRoot, "pages", "product-detail", "index.wxss"));
  if (/>\s*[询购]\s*</.test(detailWxml)) {
    fail("商品详情底部服务入口不得使用“询/购”单汉字作为图标");
  }
  for (const modifier of ["detail-service__icon--chat", "detail-service__icon--cart"]) {
    if (!detailWxml.includes(modifier) || !detailWxss.includes(`.${modifier}`)) {
      fail(`商品详情底部服务入口缺少标准图标：${modifier}`);
    }
  }
  if (!detailWxml.includes('aria-label="联系客服"') || !detailWxml.includes('aria-label="查看购物车"')) {
    fail("商品详情底部服务入口必须保留可访问名称");
  }
}

// 结算与群内登记的日期/时分是 picker 控件，必须给出可点击指示；只读的期望时间不能长成同一个样子。

// 空态与登录引导图标必须是可渲染的线性图标，禁止用单汉字/标点充当占位图标。
function checkEmptyStateIcons() {
  const appWxss = readText(path.join(miniappRoot, "app.wxss"));
  const pagesRoot = path.join(miniappRoot, "pages");
  const usedKeys = new Set();
  for (const dirName of fs.readdirSync(pagesRoot)) {
    const wxmlPath = path.join(pagesRoot, dirName, "index.wxml");
    if (!fs.existsSync(wxmlPath)) {
      continue;
    }
    const wxml = readText(wxmlPath);
    const iconTags = wxml.match(/<view[^>]*class="yunxi-state__icon[^"]*"[^>]*>[\s\S]*?<\/view>/g) || [];
    for (const tag of iconTags) {
      const inner = tag.replace(/^<view[^>]*>/, "").replace(/<\/view>$/, "").trim();
      if (inner) {
        fail(`${dirName} 空态图标不得用文字占位（${inner}）`);
      }
      if (!tag.includes('aria-hidden="true"')) {
        fail(`${dirName} 空态图标是装饰元素，必须标记 aria-hidden`);
      }
      if (!/yunxi-state__icon--/.test(tag)) {
        fail(`${dirName} 空态图标必须声明 iconKey 修饰类`);
      }
      for (const key of tag.match(/yunxi-state__icon--[a-z-]+/g) || []) {
        usedKeys.add(key.replace("yunxi-state__icon--", ""));
      }
      const classAttr = (tag.match(/class="[^"]*"/) || [""])[0];
      if (classAttr.includes("{{")) {
        for (const literal of classAttr.match(/'[a-z-]+'/g) || []) {
          usedKeys.add(literal.replaceAll("'", ""));
        }
      }
    }
  }
  if (!usedKeys.size) {
    fail("未找到任何空态图标，页面结构可能已被意外删除");
  }
  for (const key of usedKeys) {
    const rulePattern = new RegExp(`\\.yunxi-state__icon--${key}\\s*\\{[^}]*\\}`);
    const rule = appWxss.match(rulePattern);
    if (!rule || !rule[0].includes("background-image")) {
      fail(`app.wxss 缺少空态图标背景图规则：${key}`);
    }
  }
  const noticeWxml = readText(path.join(miniappRoot, "components", "session-notice", "index.wxml"));
  const noticeTs = readText(path.join(miniappRoot, "components", "session-notice", "index.ts"));
  const noticeWxss = readText(path.join(miniappRoot, "components", "session-notice", "index.wxss"));
  if (noticeWxml.includes("iconText") || noticeTs.includes("iconText")) {
    fail("会话提示徽标不得使用 iconText 文字占位");
  }
  for (const key of ["log-in", "user-check"]) {
    if (!noticeWxss.includes(`.session-notice__icon--${key}`)) {
      fail(`会话提示徽标缺少图标样式：${key}`);
    }
  }
  for (const dirName of fs.readdirSync(pagesRoot)) {
    const wxmlPath = path.join(pagesRoot, dirName, "index.wxml");
    if (!fs.existsSync(wxmlPath)) {
      continue;
    }
    if (readText(wxmlPath).includes("icon-text=")) {
      fail(`${dirName} 不得向会话提示传入 icon-text 文字徽标`);
    }
  }
}

// 工具输出可能把内联 SVG 折叠成脱敏占位符；禁止把展示层文本写回 WXSS。
function checkWxssDataUriIntegrity() {
  const pending = [miniappRoot];
  while (pending.length > 0) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const target = path.join(current, entry.name);
      if (entry.isDirectory()) {
        pending.push(target);
      } else if (entry.isFile() && entry.name.endsWith(".wxss")) {
        const source = readText(target);
        if (source.includes("[image omitted]")) {
          fail(`${toPosix(path.relative(root, target))} 写入了工具输出的脱敏占位符，必须恢复真实 data URI`);
        }
      }
    }
  }
}

// 装饰图标只能承载图形，不得把“客服 / 预 / 送 / 时”等文字塞进图标底座。
function checkIconSurfaceConsistency() {
  const homeDir = path.join(miniappRoot, "pages", "home");
  const homeWxml = readText(path.join(homeDir, "index.wxml"));
  const homeWxss = readText(path.join(homeDir, "index.wxss"));
  const homeTs = readText(path.join(homeDir, "index.ts"));
  if (!homeTs.includes("/^(points|recharge|link)$/")) {
    fail("首页快捷入口图标 key 必须限制在已定义样式内，未知 key 回退为 link");
  }
  if (homeWxml.includes("{{link.iconText}}")) {
    fail("首页快捷入口不得把 iconText 渲染进图标底座");
  }
  if (!homeWxml.includes("quick-link-card__icon--{{link.iconKey}}")) {
    fail("首页快捷入口必须按 iconKey 渲染图形图标");
  }
  const quickIconTags = homeWxml.match(/<view[^>]*class="quick-link-card__icon[^"]*"[^>]*>\s*<\/view>/g) || [];
  if (quickIconTags.length !== 1 || !quickIconTags[0].includes('aria-hidden="true"')) {
    fail("首页快捷入口图标必须是单个无文字且 aria-hidden 的图形节点");
  }
  const promiseIconTags = homeWxml.match(/<view[^>]*class="shop-promise-icon[^"]*"[^>]*>\s*<\/view>/g) || [];
  if (promiseIconTags.length !== 3 || promiseIconTags.some((tag) => !tag.includes('aria-hidden="true"'))) {
    fail("首页履约说明必须使用 3 个无文字的 aria-hidden 图形图标");
  }
  for (const key of ["points", "recharge", "link", "booking", "delivery", "hours"]) {
    const modifier = key === "points" || key === "recharge" || key === "link"
      ? `.quick-link-card__icon--${key}`
      : `.shop-promise-icon--${key}`;
    if (!homeWxss.includes(modifier) || !homeWxss.includes("background-image")) {
      fail(`首页图标缺少可渲染样式：${modifier}`);
    }
  }

  const chatDir = path.join(miniappRoot, "pages", "chat");
  const chatWxml = readText(path.join(chatDir, "index.wxml"));
  const chatWxss = readText(path.join(chatDir, "index.wxss"));
  const chatIconTags = chatWxml.match(/<view[^>]*class="empty-login__icon[^"]*"[^>]*>\s*<\/view>/g) || [];
  if (chatIconTags.length !== 1 || !chatIconTags[0].includes('aria-hidden="true"')) {
    fail("客服登录空态图标必须是单个无文字且 aria-hidden 的图形节点");
  }
  if (!chatWxml.includes("empty-login__icon--support") || !chatWxss.includes(".empty-login__icon--support")) {
    fail("客服登录空态缺少可渲染的 support 图标样式");
  }
}

// 会员中心订单与服务入口同样不得用单汉字冒充图标，必须按 iconKey 渲染可识别线性图标。
function checkProfileShortcutIcons() {
  const profileDir = path.join(miniappRoot, "pages", "profile");
  const wxml = readText(path.join(profileDir, "index.wxml"));
  const wxss = readText(path.join(profileDir, "index.wxss"));
  if (wxml.includes("order.iconText") || wxml.includes("service.iconText")) {
    fail("会员中心订单与服务入口不得使用 iconText 文字占位");
  }
  for (const token of ["order-nav-icon--{{order.iconKey}}", "service-cell__icon--{{service.iconKey}}"]) {
    if (!wxml.includes(token)) {
      fail(`会员中心缺少按 iconKey 渲染的图标节点：${token}`);
    }
  }
  const decorativeIcons = wxml.match(/class="(?:order-nav-icon|service-cell__icon)(?:\s[^"]*)?"[^>]*/g) || [];
  if (!decorativeIcons.length || decorativeIcons.some((snippet) => !snippet.includes('aria-hidden="true"'))) {
    fail("会员中心入口图标是装饰元素，必须标记 aria-hidden");
  }
  const iconKeys = [
    "wallet",
    "clock",
    "truck",
    "rotate-ccw",
    "phone",
    "message-circle",
    "shield-check",
    "file-text",
    "lock"
  ];
  for (const key of iconKeys) {
    const hasOrderModifier = wxss.includes(`.order-nav-icon--${key}`);
    const hasServiceModifier = wxss.includes(`.service-cell__icon--${key}`);
    if (!hasOrderModifier && !hasServiceModifier) {
      fail(`会员中心缺少标准图标样式：${key}`);
    }
  }
}
function checkTimePickerAffordance() {
  for (const pageName of ["checkout", "group-registration"]) {
    const pageDir = path.join(miniappRoot, "pages", pageName);
    const wxml = readText(path.join(pageDir, "index.wxml"));
    const wxss = readText(path.join(pageDir, "index.wxss"));
    const faces = wxml.match(/class="time-picker"/g) || [];
    const chevrons = wxml.match(/class="time-picker__chevron"/g) || [];
    if (faces.length !== 3) {
      fail(`${pageName} 必须保留日期/小时/分钟三个时间选择器`);
    }
    if (chevrons.length !== faces.length) {
      fail(`${pageName} 每个时间选择器都要渲染 time-picker__chevron 下拉指示`);
    }
    if (!wxss.includes(".time-picker__chevron")) {
      fail(`${pageName} 缺少 .time-picker__chevron 样式`);
    }
    const previewBlock = wxss.match(/\.time-preview\s*\{[\s\S]*?\}/);
    if (!previewBlock || /background\s*:/.test(previewBlock[0])) {
      fail(`${pageName} 的期望时间预览必须去掉底色，避免被当成可点击控件`);
    }
  }
}

// 没有实际抵扣时统一显示 “-”，不得出现“-¥0.00”这种既非零元也不代表未使用的中间态。
function checkDeductionPlaceholder() {
  const moneyTs = readText(path.join(miniappRoot, "utils", "money.ts"));
  const checkoutTs = readText(path.join(miniappRoot, "pages", "checkout", "index.ts"));
  if (!moneyTs.includes("formatDeductionFen")) {
    fail("金额工具必须提供 formatDeductionFen 统一抵扣占位符");
  }
  if (/`-\$\{formatFen\(/.test(checkoutTs)) {
    fail("结算页不得用模板字符串拼接抵扣金额，必须走 formatDeductionFen");
  }
  if (!checkoutTs.includes("formatDeductionFen(couponFen)")) {
    fail("结算页优惠券抵扣必须走 formatDeductionFen");
  }
}

// 登录引导空态的副文案必须补充信息，不能只是把标题重复一遍。
function checkLoginStateHintCopy() {
  const sources = [
    ["pages/orders/index.ts", path.join(miniappRoot, "pages", "orders", "index.ts")],
    ["pages/order-detail/index.ts", path.join(miniappRoot, "pages", "order-detail", "index.ts")],
    ["pages/address/index.ts", path.join(miniappRoot, "pages", "address", "index.ts")]
  ];
  for (const [label, filePath] of sources) {
    if (/loginStateText:\s*"请先登录后/.test(readText(filePath))) {
      fail(`${label} 的登录空态副文案不得只是“请先登录后……”的标题改写`);
    }
  }
  const couponsWxml = readText(path.join(miniappRoot, "pages", "coupons", "index.wxml"));
  const pointsWxml = readText(path.join(miniappRoot, "pages", "points", "index.wxml"));
  if (couponsWxml.includes("登录后查看可用与已用优惠券")) {
    fail("优惠券登录空态副文案必须补充券面、有效期等具体信息");
  }
  if (pointsWxml.includes("登录后查看积分余额与变动明细")) {
    fail("积分登录空态副文案必须补充获取、抵扣等具体信息");
  }
}

// 购物车数量为 1 时减号必须保持减号语义：改成“✕”会让顾客误以为点击直接删除。
function checkCartDecreaseButtonSemantics() {
  const cartWxml = readText(path.join(miniappRoot, "pages", "cart", "index.wxml"));
  const minusBlock = cartWxml.match(/<view[^>]*stepper-btn--minus[^>]*>[\s\S]*?<\/view>/);
  if (!minusBlock) {
    fail("cart page must keep the stepper minus control for quantity decrease");
    return;
  }
  if (minusBlock[0].includes("✕")) {
    fail("购物车减号不得在数量为 1 时改成“✕”，移除语义应由减号后的确认弹窗承担");
  }
  if (!/>\s*-\s*<\/view>/.test(minusBlock[0])) {
    fail("购物车减号控件必须固定渲染“-”字符");
  }
}

// 未登录个人中心不得用“我/微”这类单字充当头像，必须渲染可辨认的人像线性图标。
function checkProfileGuestAvatar() {
  const profileWxml = readText(path.join(miniappRoot, "pages", "profile", "index.wxml"));
  const profileWxss = readText(path.join(miniappRoot, "pages", "profile", "index.wxss"));
  if (!profileWxml.includes("profile-avatar--guest")) {
    fail("个人中心头像必须按登录态区分 profile-avatar--guest 占位");
  }
  if (profileWxml.includes("'我'") || profileWxml.includes("'微'")) {
    fail("个人中心不得用单个汉字充当占位头像");
  }
  const guestRule = profileWxss.match(/\.profile-avatar--guest\s*\{[^}]*\}/);
  if (!guestRule || !guestRule[0].includes("background-image")) {
    fail("个人中心未登录头像缺少可渲染的人像图标样式");
  }
}

// 结算固定栏必须说明估算金额是否已含闪送费，避免顾客只看到总额却不知道金额来源。
function checkCheckoutFooterAmountSource() {
  const checkoutWxml = readText(path.join(miniappRoot, "pages", "checkout", "index.wxml"));
  const checkoutTs = readText(path.join(miniappRoot, "pages", "checkout", "index.ts"));
  if (!checkoutWxml.includes("checkout-footer__note")) {
    fail("结算底栏必须展示 checkout-footer__note 金额来源说明");
  }
  if (!checkoutWxml.includes("{{footerAmountNote}}")) {
    fail("结算底栏金额来源说明必须绑定 footerAmountNote");
  }
  if (!checkoutTs.includes("buildFooterAmountNote")) {
    fail("结算页必须保留 buildFooterAmountNote 生成底栏金额来源说明");
  }
}

function checkTabBarLabels(appConfig) {

  const customItems = Array.from(
    readText(path.join(miniappRoot, "constants", "tab-bar.ts")).matchAll(
      /pagePath:\s*ROUTES\.(\w+),\s*text:\s*"([^"]+)"/g,
    ),
  ).map((match) => ({ route: match[1], text: match[2] }));
  const appItems = (appConfig.tabBar?.list ?? []).map((item) => ({
    route: item.pagePath.replace(/^pages\//, "").replace(/\/index$/, ""),
    text: item.text,
  }));
  for (const customItem of customItems) {
    const appItem = appItems.find((item) => item.route === customItem.route);
    if (!appItem || appItem.text !== customItem.text) {
      fail(`tabBar label mismatch for ${customItem.route}: ${appItem?.text || "missing"} != ${customItem.text}`);
    }
  }
}

const failures = [];
const appConfig = readJson(appJsonPath);
const appPages = new Set(appConfig.pages ?? []);
const tabBarPages = new Set((appConfig.tabBar?.list ?? []).map((item) => item.pagePath));

checkUnifiedHttpRequestTimeout();
checkPickupAddressSourceOfTruth();
checkDemoSessionFallbackPersists();
checkStorefrontAuthContract();
checkDevtoolsSmokeRedaction();
checkDevtoolsProbesUseBearer();
checkProductDetailDoesNotUseDemoFallback();
checkOrderDetailActions();
checkOrderFulfillmentPresentation();
checkCatalogHeadlineAndScheduleConsistency();
checkCatalogIncrementalLoading();
checkRechargeRecordsEmptyState();
checkProductListCacheKeyIncludesLimit();
checkProductDetailFooterSpace();
checkHomePromiseCardReadability();
checkGroupRegistrationDeliveryCopy();
checkRegistrationScheduleRefresh();
checkProductDetailScrollNav();
checkProductCardHintReadability();
checkDisplayOnlyProductGuard();
checkCartTagCopy();
checkCartRecommendedActionCopy();
checkProductDetailServiceIcons();
checkProfileShortcutIcons();
checkProfileGuestAvatar();
checkEmptyStateIcons();
checkWxssDataUriIntegrity();
checkIconSurfaceConsistency();
checkTimePickerAffordance();
checkDeductionPlaceholder();
checkLoginStateHintCopy();
checkCartDecreaseButtonSemantics();
checkAddressDetailCompleteness();
checkCheckoutFooterAmountSource();
checkTabBarLabels(appConfig);
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
  checkImageErrorFallback(wxmlSource, pagePath);
  checkFormFieldLabels(wxmlSource, pagePath);
  checkCustomerFacingCopy(tsSource, `${pagePath}.ts`);
  checkCustomerFacingCopy(wxmlSource, `${pagePath}.wxml`);
  checkNoHeaderHomeControl(wxmlSource, pagePath);
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
