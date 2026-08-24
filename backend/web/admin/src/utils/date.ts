/**
 * 日期/时间格式化工具。
 *
 * 全局复用的时间展示函数，支持"刚刚/昨天/周几/月日"的中文友好格式。
 */

/** 毫秒常量 */
const MS_PER_DAY = 86_400_000;
const MS_PER_WEEK = 604_800_000;

const DAY_NAMES = ["日", "一", "二", "三", "四", "五", "六"];

/**
 * 将 ISO / SQLite 时间字符串格式化为中文友好的简短展示。
 *
 * - 今天 → "HH:mm"
 * - 昨天 → "昨天"
 * - 7 天内 → "周X"
 * - 更早 → "M/D"
 */
export function fmtTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < MS_PER_DAY && d.getDate() === now.getDate()) {
    return d.toTimeString().slice(0, 5);
  }
  if (diff < MS_PER_DAY * 2) return "昨天";
  if (diff < MS_PER_WEEK) return "周" + DAY_NAMES[d.getDay()];
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
