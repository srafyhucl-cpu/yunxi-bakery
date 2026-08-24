const PRODUCTION_API_BASE_URL = "https://yunxifood.cn";
const LOCAL_API_BASE_URL = "http://127.0.0.1:7001";
const USE_LOCAL_API_STORAGE_KEY = "yunxiUseLocalApi";

function getApiBaseUrl(): string {
  return wx.getStorageSync(USE_LOCAL_API_STORAGE_KEY)
    ? LOCAL_API_BASE_URL
    : PRODUCTION_API_BASE_URL;
}

export const API_BASE_URL = getApiBaseUrl();
export const API_ENVIRONMENT = wx.getAccountInfoSync().miniProgram.envVersion;
export const IS_USING_LOCAL_API = API_BASE_URL === LOCAL_API_BASE_URL;
