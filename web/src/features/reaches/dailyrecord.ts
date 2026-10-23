// The daily flow record (preregistration-daily-record.md): a year of the river's daily flow as its
// source published it, sealed. Here: its flow in m³/s, each day against the river's usual flow for
// that calendar day, and the year compared with what its source publishes now (fetched in the
// browser, from the source's own address, never one a record names).
import type { DailyRecord, UsualFlow } from "./types.ts";

/** USGS's ft³/s to m³/s ((0.3048 m)³, as the pipeline converts it). */
export const FT3_TO_M3 = 0.0283168466;

/** Where the sources publish the daily values, as the pipeline fetches them. */
export const SOURCE_API = {
  usgs: "https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items",
  glofas: "https://flood-api.open-meteo.com/v1/flood",
} as const;

/** The discharge's parameter at each source. */
const DISCHARGE = { usgs: "00060", glofas: "river_discharge" } as const;

/** One day of the record's flow. */
export interface FlowDay {
  readonly day: string;
  /** m³/s. */
  readonly value: number;
  /** As the source gave it ("Approved", "Provisional", "Modelled"...). */
  readonly status: string;
}

/**
 * A day's place in the calendar, as the usual flow indexes it: 0 is 1 January, 365 is 31
 * December, and 29 February is 28 February.
 *
 * @param day - "YYYY-MM-DD".
 * @returns The index.
 */
export function calendarIndex(day: string): number {
  const month = Number(day.slice(5, 7));
  const date = Number(day.slice(8, 10));
  const leap = Date.UTC(2000, month - 1, month === 2 && date === 29 ? 28 : date);
  return Math.round((leap - Date.UTC(2000, 0, 1)) / 86_400_000);
}

/**
 * The record's daily flow, in m³/s, in day order.
 *
 * @param record - A sealed daily record.
 * @returns Its discharge days (empty: none).
 */
export function flowDays(record: DailyRecord): FlowDay[] {
  const series = record.series.find((s) => s.parameter === DISCHARGE[record.source.kind]);
  const factor = series?.unit === "ft³/s" ? FT3_TO_M3 : 1;
  return (series?.days ?? []).map(([day, value, status]) => ({
    day,
    value: value * factor,
    status,
  }));
}

/** Where a day's flow sits against the usual flow for its calendar day. */
export type BandPosition = "below" | "within" | "above";

/**
 * Whether a day's flow is below, within or above the usual range (10th to 90th percentile).
 *
 * @param value - The day's flow, m³/s.
 * @param day - "YYYY-MM-DD".
 * @param usual - The usual flow.
 * @returns Its place (null: no usual range that day).
 */
export function bandPosition(value: number, day: string, usual: UsualFlow): BandPosition | null {
  const k = calendarIndex(day);
  const low = usual.p10[k];
  const high = usual.p90[k];
  if (low == null || high == null) {
    return null;
  }
  return value < low ? "below" : value > high ? "above" : "within";
}

/** What the source publishes now for the record's year: by parameter, by day, [value, status]. */
export type SourceYear = ReadonlyMap<string, ReadonlyMap<string, readonly [number, string]>>;

/** A day the source changed, or no longer publishes. */
export interface DayChange {
  readonly parameter: string;
  readonly day: string;
  readonly sealed: readonly [number, string];
  /** What the source publishes now (null: nothing). */
  readonly now: readonly [number, string] | null;
}

/** The sealed year against its source now. */
export interface Comparison {
  /** Days in the record. */
  readonly checked: number;
  /** Days the source still publishes the same (value and status). */
  readonly same: number;
  /** Days whose value or status the source has changed since. */
  readonly revised: readonly DayChange[];
  /** Days the source no longer publishes. */
  readonly gone: readonly DayChange[];
  /** Days the source publishes now that the record lacks, up to its last day (gaps filled). */
  readonly filled: number;
  /** Days the source has published since the record's last day. */
  readonly newer: number;
}

/**
 * Compares a sealed year with what its source publishes now, day by day.
 *
 * @param record - The sealed record.
 * @param now - The source's year now (`sourceYear`).
 * @returns The counts, and the days that differ.
 */
export function compareYear(record: DailyRecord, now: SourceYear): Comparison {
  let checked = 0;
  let same = 0;
  let filled = 0;
  let newer = 0;
  const revised: DayChange[] = [];
  const gone: DayChange[] = [];
  for (const series of record.series) {
    const published = now.get(series.parameter) ?? new Map<string, readonly [number, string]>();
    const held = new Set<string>();
    for (const [day, value, status] of series.days) {
      held.add(day);
      checked += 1;
      const current = published.get(day) ?? null;
      const sealed = [value, status] as const;
      if (current === null) {
        gone.push({ parameter: series.parameter, day, sealed, now: null });
      } else if (current[0] === value && current[1] === status) {
        same += 1;
      } else {
        revised.push({ parameter: series.parameter, day, sealed, now: current });
      }
    }
    for (const day of published.keys()) {
      if (!held.has(day)) {
        if (day > record.date) {
          newer += 1;
        } else {
          filled += 1;
        }
      }
    }
  }
  return { checked, same, revised, gone, filled, newer };
}

interface UsgsPage {
  readonly features?: readonly {
    readonly properties?: {
      readonly time?: string;
      readonly value?: string | number | null;
      readonly approval_status?: string | null;
    };
  }[];
  readonly links?: readonly { readonly rel?: string; readonly href?: string }[];
}

interface GlofasAnswer {
  readonly daily?: {
    readonly time?: readonly string[];
    readonly river_discharge?: readonly (number | null)[];
  };
}

/**
 * The record's year as its source publishes it now, fetched in the browser from the source's own
 * address: the USGS Water Data OGC API (each parameter, following its pages), or the Open-Meteo
 * flood API for GloFAS (its grid cell, as the record's query names it), up to yesterday.
 *
 * @param record - The sealed record.
 * @param fetcher - `fetch` (injectable).
 * @param today - Today (injectable): the flood API's later days are forecasts, never compared.
 * @returns By parameter, by day, [value, status].
 */
export async function sourceYear(
  record: DailyRecord,
  fetcher: typeof fetch = fetch,
  today: Date = new Date(),
): Promise<SourceYear> {
  const year = String(record.year);
  // Up to yesterday (UTC), as the pipeline fetches: the flood API also returns forecast days.
  const yesterday = new Date(today.getTime() - 86_400_000).toISOString().slice(0, 10);
  const last = `${year}-12-31` < yesterday ? `${year}-12-31` : yesterday;
  const out = new Map<string, Map<string, readonly [number, string]>>();
  if (record.source.kind === "glofas") {
    const { latitude = "", longitude = "" } = record.provenance.query;
    const query = new URLSearchParams({
      latitude,
      longitude,
      daily: DISCHARGE.glofas,
      start_date: `${year}-01-01`,
      end_date: last,
      cell_selection: "nearest",
    });
    const response = await fetcher(`${SOURCE_API.glofas}?${query.toString()}`);
    if (!response.ok) {
      throw new Error(`the flood API answered ${String(response.status)}`);
    }
    const answer = (await response.json()) as GlofasAnswer;
    const days = new Map<string, readonly [number, string]>();
    const values = answer.daily?.river_discharge ?? [];
    (answer.daily?.time ?? []).forEach((day, k) => {
      const value = values[k];
      if (typeof value === "number") {
        days.set(day, [value, "Modelled"]);
      }
    });
    out.set(DISCHARGE.glofas, days);
    return out;
  }
  for (const series of record.series) {
    const query = new URLSearchParams({
      monitoring_location_id: record.source.stationId,
      parameter_code: series.parameter,
      statistic_id: "00003",
      f: "json",
      datetime: `${year}-01-01/${last}`,
      limit: "1000",
      skipGeometry: "true",
      properties: "time,value,approval_status",
    });
    const days = new Map<string, readonly [number, string]>();
    let url: string | undefined = `${SOURCE_API.usgs}?${query.toString()}`;
    for (let page = 0; url !== undefined && page < 10; page += 1) {
      const response = await fetcher(url);
      if (!response.ok) {
        throw new Error(`USGS answered ${String(response.status)}`);
      }
      const body = (await response.json()) as UsgsPage;
      for (const feature of body.features ?? []) {
        const p = feature.properties;
        const value = p?.value == null ? NaN : Number(p.value);
        if (p?.time !== undefined && Number.isFinite(value)) {
          days.set(p.time.slice(0, 10), [value, p.approval_status ?? ""]);
        }
      }
      url = body.links?.find((l) => l.rel === "next")?.href;
    }
    out.set(series.parameter, days);
  }
  return out;
}
