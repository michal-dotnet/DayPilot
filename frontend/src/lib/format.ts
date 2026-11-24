// תצוגת תאריכים ושעות בשעון ישראל, בשפת הממשק.
import i18n from "../i18n";

const TZ = "Asia/Jerusalem";

function locale() {
  return i18n.language === "en" ? "en-GB" : "he-IL";
}

export function fmtTime(iso: string) {
  return new Intl.DateTimeFormat(locale(), { hour: "2-digit", minute: "2-digit", timeZone: TZ }).format(new Date(iso));
}

export function fmtDate(iso: string, withWeekday = true) {
  const d = iso.length === 10 ? new Date(iso + "T12:00:00") : new Date(iso);
  return new Intl.DateTimeFormat(locale(), {
    weekday: withWeekday ? "long" : undefined,
    day: "numeric",
    month: "long",
    timeZone: TZ,
  }).format(d);
}

export function fmtShortDay(isoDate: string) {
  return new Intl.DateTimeFormat(locale(), { weekday: "short", day: "numeric", timeZone: TZ }).format(
    new Date(isoDate + "T12:00:00"),
  );
}

export function fmtHours(minutes: number) {
  const h = minutes / 60;
  if (h === 1) return i18n.t("common.hour");
  const value = Number.isInteger(h) ? String(h) : h.toFixed(1);
  return i18n.t("common.hours", { value });
}

export function tList(key: string): string[] {
  return i18n.t(key, { returnObjects: true }) as unknown as string[];
}

export function daysUntil(iso: string) {
  const ms = new Date(iso).getTime() - Date.now();
  return Math.ceil(ms / 86_400_000);
}

export function todayIso() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
}

export function addDays(isoDate: string, n: number) {
  const d = new Date(isoDate + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

// צבע קבוע לכל משימה, כדי שתזוהה בכל המסכים
const PALETTE = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6", "#ef4444"];
export function taskColor(taskId: number) {
  return PALETTE[taskId % PALETTE.length];
}

export function fmtShortDayOf(isoDateTime: string) {
  return new Intl.DateTimeFormat(locale(), { weekday: "short", day: "numeric", timeZone: TZ }).format(new Date(isoDateTime));
}
