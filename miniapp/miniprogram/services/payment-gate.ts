import { IS_USING_LOCAL_API } from "./config";

/** 本地后端（mock 支付可用）：IS_USING_LOCAL_API 为 true 时 API_BASE_URL 指向 127.0.0.1:7001。 */
export const IS_LOCAL_BACKEND = IS_USING_LOCAL_API;
/** 充值 mock 确认依赖本地后端。 */
export const RECHARGE_READY = IS_LOCAL_BACKEND;
/** 在线支付路径（prepare-payment / 组合差额会话，需 mock 或微信）依赖本地后端。 */
export const ONLINE_PAYMENT_READY = IS_LOCAL_BACKEND;
