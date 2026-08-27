const PRODUCTION_API_BASE_URL = "https://yunxifood.cn";
const LOCAL_API_BASE_URL = "http://127.0.0.1:7001";
const USE_LOCAL_API_STORAGE_KEY = "yunxiUseLocalApi";

function getApiBaseUrl(): string {
  const stored = wx.getStorageSync(USE_LOCAL_API_STORAGE_KEY);
  // 显式设置过时以用户选择为准
  if (stored === true || stored === "true") {
    return LOCAL_API_BASE_URL;
  }
  if (stored === false || stored === "false") {
    return PRODUCTION_API_BASE_URL;
  }
  // 未设置时：开发/预览版默认连本地后端（P2 试运行阶段必须避开线上配置），体验版/正式版连线上
  // 注释：试运行阶段开发者版连本地，避免误用未就绪的线上配置
  const envVersion = wx.getAccountInfoSync().miniProgram.envVersion;
  return envVersion === "develop" ? LOCAL_API_BASE_URL : PRODUCTION_API_BASE_URL;
}

export const API_BASE_URL = getApiBaseUrl();
export const API_ENVIRONMENT = wx.getAccountInfoSync().miniProgram.envVersion;
export const IS_USING_LOCAL_API = API_BASE_URL === LOCAL_API_BASE_URL;
