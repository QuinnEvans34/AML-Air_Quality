/**
 * Node-side raw PM2.5 CSV reader.
 *
 * Reads pm25_{YYYY-MM-DD}.csv files from the pipeline's RAW_DATA_DIR
 * (see lib/constants.ts) and returns parsed rows. Used by /api/features
 * to build the recent-pattern lookup that drives Decision 8's hourly
 * feature prep.
 *
 * Source-of-truth for the CSV schema is Contract 1 in INTERFACE.md:
 *
 *   timestamp     datetime (ISO 8601, UTC)
 *   location_id   int
 *   pm25          float (μg/m³)
 *
 * This file MUST only run server-side (Next.js API routes). The
 * `fs` and `path` imports are Node built-ins; importing this from a
 * client component would break the build.
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import Papa from "papaparse";

import { RAW_DATA_DIR } from "./constants";

/** One row from a Contract 1 raw CSV. */
export interface RawPm25Row {
  /** ISO 8601 UTC timestamp string, as it appears in the CSV. */
  timestamp: string;
  location_id: number;
  pm25: number;
}

/**
 * Resolve the configured raw-data directory to an absolute path. If
 * `RAW_DATA_DIR` is already absolute it is returned as-is; otherwise
 * it is resolved relative to the Next.js process cwd (which is
 * `app/dashboard/` during `npm run dev`).
 */
export function resolveRawDataDir(): string {
  return path.isAbsolute(RAW_DATA_DIR)
    ? RAW_DATA_DIR
    : path.resolve(process.cwd(), RAW_DATA_DIR);
}

/**
 * Read a single pm25_{YYYY-MM-DD}.csv file from disk and parse it
 * into RawPm25Row objects. Returns an empty array if the file does
 * not exist — callers (the recent-pattern lookup) tolerate missing
 * days. Parse errors propagate so the API route can return a 500.
 *
 * @param isoDate YYYY-MM-DD UTC date string (e.g. "2026-05-13")
 */
export async function readRawCsvForDate(
  isoDate: string,
): Promise<RawPm25Row[]> {
  const filename = `pm25_${isoDate}.csv`;
  const fullPath = path.join(resolveRawDataDir(), filename);

  let text: string;
  try {
    text = await fs.readFile(fullPath, "utf8");
  } catch (err: unknown) {
    // Missing files are an expected case for the recent-pattern
    // lookup — e.g. an outage day in the reference window, or a
    // future date the dashboard knows we don't have. Other errors
    // (permission denied, etc.) are not expected and propagate.
    if (
      typeof err === "object" &&
      err !== null &&
      "code" in err &&
      (err as { code?: string }).code === "ENOENT"
    ) {
      return [];
    }
    throw err;
  }

  if (!text.trim()) return [];

  const parsed = Papa.parse<Record<string, string>>(text, {
    header: true,
    skipEmptyLines: true,
  });

  // Drop any row missing the three required columns. Contract 1
  // guarantees these are non-null in the CSV; if a row is missing
  // them the file is malformed and the caller will see fewer rows.
  const rows: RawPm25Row[] = [];
  for (const raw of parsed.data) {
    const timestamp = raw.timestamp;
    const locIdStr = raw.location_id;
    const pm25Str = raw.pm25;
    if (!timestamp || !locIdStr || !pm25Str) continue;
    const location_id = Number.parseInt(locIdStr, 10);
    const pm25 = Number.parseFloat(pm25Str);
    if (!Number.isFinite(location_id) || !Number.isFinite(pm25)) continue;
    rows.push({ timestamp, location_id, pm25 });
  }
  return rows;
}

/**
 * Read all pm25 files for the inclusive date range [fromIsoDate,
 * toIsoDate]. Missing days are silently skipped (consistent with the
 * single-day reader). Returns a flat array sorted by timestamp.
 */
export async function readRawCsvForRange(
  fromIsoDate: string,
  toIsoDate: string,
): Promise<RawPm25Row[]> {
  const dates = enumerateDates(fromIsoDate, toIsoDate);
  const arrays = await Promise.all(dates.map(readRawCsvForDate));
  const flat = arrays.flat();
  flat.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  return flat;
}

/**
 * Build the inclusive YYYY-MM-DD list between two UTC dates. Returns
 * an empty array if `from` is after `to`.
 */
export function enumerateDates(
  fromIsoDate: string,
  toIsoDate: string,
): string[] {
  const out: string[] = [];
  const from = new Date(`${fromIsoDate}T00:00:00Z`);
  const to = new Date(`${toIsoDate}T00:00:00Z`);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) return out;
  if (from > to) return out;

  const cursor = new Date(from);
  while (cursor <= to) {
    out.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return out;
}

/**
 * Return the YYYY-MM-DD UTC date `daysAgo` days strictly before the
 * supplied anchor date. ``daysAgo = 1`` for "yesterday".
 */
export function isoDateDaysBefore(
  anchorIsoDate: string,
  daysAgo: number,
): string {
  const d = new Date(`${anchorIsoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}
