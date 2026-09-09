const DEFAULT_PICKUP_HOUR = 18;
const DEFAULT_PICKUP_MINUTE = "00";
const DEFAULT_BUSINESS_HOURS = "09:00-19:30";
const DATE_PICKER_DAYS = 7;
const SAME_DAY_ORDER_CUTOFF_HOUR = 17;
const BEIJING_TIME_ZONE = "Asia/Shanghai";
const BUSINESS_HOURS_PATTERN = /(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})/;

export const CHECKOUT_MINUTE_OPTIONS = ["00", "30"];

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
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: BEIJING_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23"
  }).formatToParts(now);
  const values = Object.fromEntries(
    parts
      .filter((part) => ["year", "month", "day", "hour", "minute"].includes(part.type))
      .map((part) => [part.type, Number(part.value)])
  );
  return {
    year: values.year || 0,
    month: values.month || 0,
    day: values.day || 0,
    hour: values.hour || 0,
    minute: values.minute || 0
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
  now = new Date()
): string[] {
  const { startHour, endHour } = parseBusinessHourRange(businessHours);
  const currentTime = getBeijingDateTimeParts(now);
  const earliestHour =
    isCheckoutDateToday(dateValue, now)
      ? Math.max(startHour, currentTime.hour + (currentTime.minute > 0 ? 1 : 0))
      : startHour;
  return Array.from({ length: Math.max(0, endHour - earliestHour + 1) }, (_, index) =>
    padDateNumber(earliestHour + index)
  );
}

export function getDefaultCheckoutHourIndex(hourOptions: string[]): number {
  const defaultHour = padDateNumber(DEFAULT_PICKUP_HOUR);
  const index = hourOptions.indexOf(defaultHour);
  return index >= 0 ? index : Math.max(hourOptions.length - 1, 0);
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
  now = new Date()
): string {
  const dateValue = getCheckoutDateStart(now);
  const hourOptions = buildCheckoutHourOptions(businessHours, dateValue, now);
  const hourValue = hourOptions[getDefaultCheckoutHourIndex(hourOptions)] || padDateNumber(DEFAULT_PICKUP_HOUR);
  return `${dateValue} ${hourValue}:${DEFAULT_PICKUP_MINUTE}`;
}

export function buildExpectTime(dateValue: string, hourValue: string, minuteValue: string): string {
  return `${dateValue} ${hourValue}:${minuteValue}`;
}
