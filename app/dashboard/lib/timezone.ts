/**
 * Mountain-Time helpers for the dashboard.
 *
 * Single source of truth so every component goes through the same
 * conversion logic. The model still receives UTC `hour_of_day`
 * values — these helpers exist purely for the display/input layer.
 *
 * Uses `date-fns-tz` v3 (`fromZonedTime` is the canonical name in
 * v3; `zonedTimeToUtc` was removed).
 */

import { formatInTimeZone, fromZonedTime } from "date-fns-tz";

/** Canonical IANA zone for Utah. America/Denver handles MST↔MDT automatically. */
export const TZ_MOUNTAIN = "America/Denver";

/** Format a UTC Date (or ISO string) as a wall-clock label in Mountain Time.
 *  e.g. mtFormat("2026-05-16T14:00:00Z", "h a") → "8 AM" */
export function mtFormat(input: Date | string, pattern: string): string {
  const d = typeof input === "string" ? new Date(input) : input;
  return formatInTimeZone(d, TZ_MOUNTAIN, pattern);
}

/** Format with the "MT" suffix so screen readers + visual readers
 *  both know the time zone. */
export function mtFormatLabeled(input: Date | string): string {
  return `${mtFormat(input, "h a")} MT`;
}

/** Convert a Mountain Time wall-clock (date + hour) to the UTC Date
 *  instant the model wants. Used by app/page.tsx when building the
 *  features-request payload from the user's picked range. */
export function mtWallClockToUtcDate(
  dateMT: string, // "2026-05-16"
  hourMT: number, // 8 (means 8:00 AM Mountain wall-clock time)
): Date {
  // fromZonedTime interprets the string as wall-clock time in the
  // named zone and returns the corresponding UTC Date.
  return fromZonedTime(
    `${dateMT} ${hourMT.toString().padStart(2, "0")}:00:00`,
    TZ_MOUNTAIN,
  );
}

/** Today's date in Mountain Time as YYYY-MM-DD (NOT UTC). The host
 *  laptop's TZ shouldn't influence what "today" means for a Utah
 *  principal. */
export function mtTodayIsoDate(): string {
  return mtFormat(new Date(), "yyyy-MM-dd");
}

/** Convert any Date to its Mountain-Time YYYY-MM-DD calendar date. */
export function mtIsoDate(d: Date): string {
  return mtFormat(d, "yyyy-MM-dd");
}

/** Convert a UTC hour-of-day (0–23) on a specific date into the
 *  corresponding Mountain wall-clock hour (0–23). Handles DST and
 *  date-shift correctly (e.g. UTC 02:00 on a winter day = MST 19:00
 *  the previous day). */
export function utcHourToMtHour(
  utcHour: number,
  isoDateUtc: string,
): { hour: number; date: string } {
  const utcDate = new Date(
    `${isoDateUtc}T${utcHour.toString().padStart(2, "0")}:00:00Z`,
  );
  return {
    hour: parseInt(mtFormat(utcDate, "H"), 10),
    date: mtFormat(utcDate, "yyyy-MM-dd"),
  };
}

/** Build the array of "next N days" the new DayPicker renders.
 *  Each entry is keyed by its Mountain-Time YYYY-MM-DD. */
export function nextNDaysMT(
  n: number,
  anchor?: Date,
): Array<{
  iso: string;
  weekday: string;
  monthDay: string;
  isToday: boolean;
}> {
  const start = anchor ?? new Date();
  const out: Array<{
    iso: string;
    weekday: string;
    monthDay: string;
    isToday: boolean;
  }> = [];
  const todayIso = mtIsoDate(start);
  for (let i = 0; i < n; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    const iso = mtIsoDate(d);
    out.push({
      iso,
      weekday: mtFormat(d, "EEE"),
      monthDay: mtFormat(d, "MMM d"),
      isToday: iso === todayIso,
    });
  }
  return out;
}
