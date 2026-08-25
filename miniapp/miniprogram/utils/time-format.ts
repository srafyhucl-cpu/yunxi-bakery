/**
 * 聊天/消息时间格式化工具。
 */

/**
 * 将时间字符串格式化为 HH:MM。
 *
 * iOS 的 JS 引擎不解析 "yyyy-MM-dd HH:mm:ss"（空格分隔）格式的时间字符串，
 * new Date 会返回 Invalid Date；此处在解析前归一化为
 * "yyyy-MM-ddTHH:mm:ss"（ISO 格式），跨端行为一致。
 */
export function formatMsgTime(iso: string): string {
  if (!iso) return "";
  try {
    const normalized = normalizeTimeString(iso);
    const d = new Date(normalized);
    if (isNaN(d.getTime())) {
      return "";
    }
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  } catch {
    return "";
  }
}

/**
 * 把 "yyyy-MM-dd HH:mm:ss"（空格分隔）归一化为 "yyyy-MM-ddTHH:mm:ss"。
 * 已符合 ISO 格式的输入原样返回。
 */
export function normalizeTimeString(iso: string): string {
  if (!iso) return iso;
  // "yyyy-MM-dd HH:mm:ss"：位置约定 0-3 年 / 5-6 月 / 8-9 日 / 10 空格 / 11-12 时
  if (iso.length >= 19 && iso[10] === " " && iso[13] === ":" && iso[16] === ":") {
    return iso.slice(0, 10) + "T" + iso.slice(11);
  }
  return iso;
}
