const DEFAULT_PICKUP_HOUR = 18;
const DEFAULT_PICKUP_MINUTE = "00";
const DEFAULT_BUSINESS_HOURS = "09:00-19:30";
const DATE_PICKER_DAYS = 7;
const SAME_DAY_ORDER_CUTOFF_HOUR = 17;
// 北京时区固定为 UTC+8（中国无夏令时）；部分真机小程序 JS 引擎不提供 Intl，故用固定偏移手动换算。
const BEIJING_UTC_OFFSET_MINUTES = 8 * 60;
const BUSINESS_HOURS_PATTERN = /(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})/;

export const CHECKOUT_MINUTE_OPTIONS = ["00", "30"];
// 预订蛋糕后端硬性要求至少提前 4 小时，前端可选时间必须跟着抬起来，避免选完再被拒单。
export const PREORDER_MIN_ADVANCE_HOURS = 4;

interface BusinessHourRange {
  startHour: number;
  endHour: number;
}

interface BeijingDateTimeParts {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

function clampHour(value: number): number {
  return Math.max(0, Math.min(23, value));
}

function parseBusinessHourRange(businessHours: string): BusinessHourRange {
  const match = (businessHours || DEFAULT_BUSINESS_HOURS).match(BUSINESS_HOURS_PATTERN);
  if (!match) {
    return parseBusinessHourRange(DEFAULT_BUSINESS_HOURS);
  }
  const startHour = clampHour(Number(match[1]));
  const endHour = clampHour(Number(match[3]));
  if (endHour < startHour) {
    return parseBusinessHourRange(DEFAULT_BUSINESS_HOURS);
  }
  return { startHour, endHour };
}

export function padDateNumber(value: number): string {
  return String(value).padStart(2, "0");
}

function getBeijingDateTimeParts(now = new Date()): BeijingDateTimeParts {
  // 部分真机（尤其 Android）的小程序 JS 引擎不提供 Intl，Intl.DateTimeFormat 会在
  // 结算页模块加载期抛 ReferenceError 导致白屏；改用固定 UTC+8 偏移手动换算北京时间
  // （中国无夏令时，与 timeZone: "Asia/Shanghai" 等价）。
  const beijing = new Date(now.getTime() + BEIJING_UTC_OFFSET_MINUTES * 60 * 1000);
  return {
    year: beijing.getUTCFullYear(),
    month: beijing.getUTCMonth() + 1,
    day: beijing.getUTCDate(),
    hour: beijing.getUTCHours(),
    minute: beijing.getUTCMinutes()
  };
}

function formatBeijingDateWithOffset(now: Date, offsetDays: number): string {
  const { year, month, day } = getBeijingDateTimeParts(now);
  const value = new Date(Date.UTC(year, month - 1, day + offsetDays));
  return `${value.getUTCFullYear()}-${padDateNumber(value.getUTCMonth() + 1)}-${padDateNumber(value.getUTCDate())}`;
}

export function buildCheckoutHourOptions(
  businessHours: string,
  dateValue = getCheckoutDateStart(),
  now = new Date(),
  minAdvanceHours = 0
): string[] {
  const { startHour, endHour } = parseBusinessHourRange(businessHours);
  const currentTime = getBeijingDateTimeParts(now);
  let earliestHour =
    isCheckoutDateToday(dateValue, now)
      ? Math.max(startHour, currentTime.hour + (currentTime.minute > 0 ? 1 : 0))
      : startHour;
  if (minAdvanceHours > 0 && isCheckoutDateToday(dateValue, now)) {
    const earliestAllowed = getBeijingDateTimeParts(
      new Date(now.getTime() + minAdvanceHours * 60 * 60 * 1000)
    );
    earliestHour = Math.max(
      earliestHour,
      earliestAllowed.hour + (earliestAllowed.minute > 0 ? 1 : 0)
    );
  }
  return Array.from({ length: Math.max(0, endHour - earliestHour + 1) }, (_, index) =>
    padDateNumber(earliestHour + index)
  );
}

export function getDefaultCheckoutHourIndex(hourOptions: string[]): number {
  const defaultHour = padDateNumber(DEFAULT_PICKUP_HOUR);
  const index = hourOptions.indexOf(defaultHour);
  return index >= 0 ? index : Math.max(hourOptions.length - 1, 0);
}

export interface CheckoutExpectTimeParts {
  dateValue: string;
  hourValue: string;
  minuteValue: string;
}

export function parseExpectTime(expectTime: string): CheckoutExpectTimeParts | null {
  const match = (expectTime || "").trim().match(/^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})$/);
  if (!match) {
    return null;
  }
  return {
    dateValue: match[1],
    hourValue: padDateNumber(Number(match[2])),
    minuteValue: match[3]
  };
}

// 选择器显示值必须由提交值反推，否则重新进入结算页时控件与实际下单时间会不一致。
export function resolveCheckoutHourIndex(hourOptions: string[], expectTime: string): number {
  const parsed = parseExpectTime(expectTime);
  const index = parsed ? hourOptions.indexOf(parsed.hourValue) : -1;
  return index >= 0 ? index : getDefaultCheckoutHourIndex(hourOptions);
}

export function resolveCheckoutMinuteIndex(minuteOptions: string[], expectTime: string): number {
  const parsed = parseExpectTime(expectTime);
  const index = parsed ? minuteOptions.indexOf(parsed.minuteValue) : -1;
  return index >= 0 ? index : 0;
}

export function formatCheckoutDate(date: Date): string {
  return formatBeijingDateWithOffset(date, 0);
}

export function isCheckoutDateToday(dateValue: string, now = new Date()): boolean {
  return dateValue === formatCheckoutDate(now);
}

export function getCheckoutDateStart(now = new Date()): string {
  const { hour } = getBeijingDateTimeParts(now);
  return formatBeijingDateWithOffset(now, hour < SAME_DAY_ORDER_CUTOFF_HOUR ? 0 : 1);
}

export function getCheckoutDateEnd(now = new Date()): string {
  return formatBeijingDateWithOffset(now, DATE_PICKER_DAYS);
}

export function buildDefaultExpectTime(
  businessHours = DEFAULT_BUSINESS_HOURS,
  now = new Date(),
  minAdvanceHours = 0
): string {
  let dateValue = getCheckoutDateStart(now);
  let hourOptions = buildCheckoutHourOptions(businessHours, dateValue, now, minAdvanceHours);
  // 提前量把今天的可预约时段全部挤掉时，默认落到次日营业时段
  if (!hourOptions.length) {
    dateValue = formatBeijingDateWithOffset(now, 1);
    hourOptions = buildCheckoutHourOptions(businessHours, dateValue, now, minAdvanceHours);
  }
  const hourValue = hourOptions[getDefaultCheckoutHourIndex(hourOptions)] || padDateNumber(DEFAULT_PICKUP_HOUR);
  return `${dateValue} ${hourValue}:${DEFAULT_PICKUP_MINUTE}`;
}

export function buildExpectTime(dateValue: string, hourValue: string, minuteValue: string): string {
  return `${dateValue} ${hourValue}:${minuteValue}`;
}

export interface CheckoutScheduleState {
  expectTime: string;
  dateValue: string;
  hourOptions: string[];
  hourIndex: number;
  minuteIndex: number;
}

export function resolveCheckoutSchedule(
  businessHours: string,
  expectTime: string,
  minuteOptions: string[] = CHECKOUT_MINUTE_OPTIONS,
  now = new Date(),
  minAdvanceHours = 0
): CheckoutScheduleState {
  const fallbackExpectTime = buildDefaultExpectTime(businessHours, now, minAdvanceHours);
  const normalizedExpectTime = (expectTime || "").trim() || fallbackExpectTime;
  // 已过当天截单时间时，历史选择值必须抬到最早可预约日期，不能把过期时间原样带进下单。
  const requestedDateValue = parseExpectTime(normalizedExpectTime)?.dateValue || "";
  const earliestDateValue = getCheckoutDateStart(now);
  const dateValue =
    requestedDateValue && requestedDateValue >= earliestDateValue
      ? requestedDateValue
      : earliestDateValue;
  const hourOptions = buildCheckoutHourOptions(
    businessHours,
    dateValue,
    now,
    minAdvanceHours
  );
  const hourIndex = resolveCheckoutHourIndex(hourOptions, normalizedExpectTime);
  const minuteIndex = resolveCheckoutMinuteIndex(minuteOptions, normalizedExpectTime);
  return {
    expectTime: buildExpectTime(
      dateValue,
      hourOptions[hourIndex] || hourOptions[0] || padDateNumber(DEFAULT_PICKUP_HOUR),
      minuteOptions[minuteIndex] || DEFAULT_PICKUP_MINUTE
    ),
    dateValue,
    hourOptions,
    hourIndex,
    minuteIndex
  };
}
