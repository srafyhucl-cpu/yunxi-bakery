const DEFAULT_PICKUP_HOUR = 18;
const DEFAULT_PICKUP_MINUTE = "00";
const DEFAULT_BUSINESS_HOURS = "09:00-20:00";
const DATE_OFFSET_DAYS = 1;
const DATE_PICKER_DAYS = 7;
const MS_PER_DAY = 24 * 60 * 60 * 1000;
const BUSINESS_HOURS_PATTERN = /(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})/;

export const CHECKOUT_MINUTE_OPTIONS = ["00", "30"];

interface BusinessHourRange {
  startHour: number;
  endHour: number;
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

export function buildCheckoutHourOptions(businessHours: string): string[] {
  const { startHour, endHour } = parseBusinessHourRange(businessHours);
  return Array.from({ length: endHour - startHour + 1 }, (_, index) =>
    padDateNumber(startHour + index)
  );
}

export function getDefaultCheckoutHourIndex(hourOptions: string[]): number {
  const defaultHour = padDateNumber(DEFAULT_PICKUP_HOUR);
  const index = hourOptions.indexOf(defaultHour);
  return index >= 0 ? index : Math.max(hourOptions.length - 1, 0);
}

export function formatCheckoutDate(date: Date): string {
  const year = date.getFullYear();
  const month = padDateNumber(date.getMonth() + 1);
  const day = padDateNumber(date.getDate());
  return `${year}-${month}-${day}`;
}

export function getCheckoutDateStart(): string {
  return formatCheckoutDate(new Date(Date.now() + DATE_OFFSET_DAYS * MS_PER_DAY));
}

export function getCheckoutDateEnd(): string {
  return formatCheckoutDate(new Date(Date.now() + DATE_PICKER_DAYS * MS_PER_DAY));
}

export function buildDefaultExpectTime(businessHours = DEFAULT_BUSINESS_HOURS): string {
  const hourOptions = buildCheckoutHourOptions(businessHours);
  const hourValue = hourOptions[getDefaultCheckoutHourIndex(hourOptions)] || padDateNumber(DEFAULT_PICKUP_HOUR);
  return `${getCheckoutDateStart()} ${hourValue}:${DEFAULT_PICKUP_MINUTE}`;
}

export function buildExpectTime(dateValue: string, hourValue: string, minuteValue: string): string {
  return `${dateValue} ${hourValue}:${minuteValue}`;
}
