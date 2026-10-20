// The "How it works" flow chart's data: a station's daily flow through each satellite year, its
// low-flow and high-flow lines, and the days the satellite had a usable pass. Read from the
// committed files the pipeline counts the same days from (pipeline/src/climate_pipeline/reach/
// extremes.py, rule v1): the station's daily means (climate/daily.csv, USGS parameter 00060 in
// ft³/s), the two lines (climate.json, extremes.thresholds, in m³/s) and the usable passes of the
// v5 inputs (inputs/usgs-v5/turbidity.csv). `packStation` runs at build time (vite.config.ts), so
// the page carries a compact year, not the files; the tests run it on the full files and recount
// every year against climate.json.

/** Cubic feet to cubic metres, exactly as the pipeline converts them. */
export const FT3_TO_M3 = 0.028316846592;
/** The satellite years of the v5 inputs (extremes.py, V5_YEARS): the chart offers these. */
export const SATELLITE_YEARS: readonly number[] = [2019, 2020, 2021, 2022, 2023, 2024, 2025];

/** A day's kind, as rule v1 names it ("normal": neither). */
export type DayKind = "low" | "high" | "normal";

/** One day of the station's record. */
export interface FlowDay {
  /** ISO date. */
  readonly day: string;
  /** Daily mean discharge, m³/s (rounded to 0.1); null when the station has no value. */
  readonly flow: number | null;
  readonly kind: DayKind;
  /** The satellite had a usable pass that day. */
  readonly seen: boolean;
}

/** One year of one station, as the chart draws it. */
export interface FlowYear {
  readonly year: number;
  /** Every calendar day, 1 January first. */
  readonly days: readonly FlowDay[];
  /** Low-flow and high-flow days and the ones the satellite saw, as climate.json counts them. */
  readonly low: number;
  readonly lowSeen: number;
  readonly high: number;
  readonly highSeen: number;
}

/** A station across the satellite years. */
export interface FlowStation {
  readonly id: string;
  readonly name: string;
  /** Where the daily values come from, as climate.json names it. */
  readonly source: string;
  /** The low-flow and high-flow lines (m³/s): the 10th and 90th percentiles (rule v1). */
  readonly lowLine: number;
  readonly highLine: number;
  readonly years: readonly FlowYear[];
}

/** The same, packed for the page: a year is three strings and an array, not 365 objects. */
export interface PackedStation {
  readonly id: string;
  readonly name: string;
  readonly source: string;
  readonly lowLine: number;
  readonly highLine: number;
  readonly years: readonly {
    readonly year: number;
    readonly low: number;
    readonly lowSeen: number;
    readonly high: number;
    readonly highSeen: number;
    /** One flow per calendar day (m³/s, 0.1), null where the station has none. */
    readonly flows: readonly (number | null)[];
    /** One letter per day: l(ow), h(igh), n(ormal). */
    readonly kinds: string;
    /** One letter per day: 1 the satellite saw it, 0 not. */
    readonly seen: string;
  }[];
}

// A CSV's rows as records (no quoted commas in these files).
function rows(text: string): Record<string, string>[] {
  const [head, ...lines] = text.trim().split(/\r?\n/);
  if (head === undefined) {
    return [];
  }
  const columns = head.split(",");
  return lines.map((line) => {
    const cells = line.split(",");
    return Object.fromEntries(columns.map((c, k) => [c, cells[k] ?? ""]));
  });
}

interface Climate {
  readonly station: { readonly id: string; readonly name: string };
  readonly source: string;
  readonly extremes?: {
    readonly thresholds: { readonly low: number; readonly high: number };
    readonly years: readonly {
      readonly year: number;
      readonly low: number;
      readonly lowSeen: number | null;
      readonly high: number;
      readonly highSeen: number | null;
    }[];
  };
}

const DAY_MS = 86_400_000;
const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/**
 * A station's satellite years, packed: each day's flow and kind, and the satellite's usable passes.
 * A day the gauge publishes twice takes the mean of its values (extremes.py, one_per_day).
 *
 * @param climateJson - The reach's climate.json.
 * @param dailyCsv - The station's daily.csv (day, parameter, value, approval).
 * @param passesCsv - The v5 inputs' turbidity.csv (site_id, key, datetime_utc, …).
 * @returns The station, or null when climate.json has no extremes.
 */
export function packStation(
  climateJson: string,
  dailyCsv: string,
  passesCsv: string,
): PackedStation | null {
  const climate = JSON.parse(climateJson) as Climate;
  const extremes = climate.extremes;
  if (extremes === undefined) {
    return null;
  }
  const { low: lowLine, high: highLine } = extremes.thresholds;
  const seen = new Set(
    rows(passesCsv)
      .filter((r) => r.site_id === climate.station.id)
      .map((r) => (r.datetime_utc ?? "").slice(0, 10)),
  );
  const values = new Map<string, number[]>();
  for (const r of rows(dailyCsv)) {
    if (r.parameter === "00060" && r.value !== "" && r.day !== undefined) {
      values.set(r.day, [...(values.get(r.day) ?? []), Number(r.value) * FT3_TO_M3]);
    }
  }
  const years = SATELLITE_YEARS.flatMap((year) => {
    const counts = extremes.years.find((y) => y.year === year);
    if (counts === undefined) {
      return [];
    }
    const flows: (number | null)[] = [];
    let kinds = "";
    let saw = "";
    for (let ms = Date.UTC(year, 0, 1); ms < Date.UTC(year + 1, 0, 1); ms += DAY_MS) {
      const day = isoDay(ms);
      const v = values.get(day);
      const flow = v === undefined ? null : v.reduce((a, b) => a + b, 0) / v.length;
      flows.push(flow === null ? null : Math.round(flow * 10) / 10);
      kinds += flow === null ? "n" : flow <= lowLine ? "l" : flow >= highLine ? "h" : "n";
      saw += seen.has(day) ? "1" : "0";
    }
    return [
      {
        year,
        low: counts.low,
        lowSeen: counts.lowSeen ?? 0,
        high: counts.high,
        highSeen: counts.highSeen ?? 0,
        flows,
        kinds,
        seen: saw,
      },
    ];
  });
  return {
    id: climate.station.id,
    name: climate.station.name,
    source: climate.source,
    lowLine,
    highLine,
    years,
  };
}

const KIND: Readonly<Record<string, DayKind>> = { l: "low", h: "high", n: "normal" };

/**
 * A packed station, back as days.
 *
 * @param packed - From {@link packStation}.
 * @returns The station.
 */
export function unpackStation(packed: PackedStation): FlowStation {
  return {
    ...packed,
    years: packed.years.map((y) => ({
      year: y.year,
      low: y.low,
      lowSeen: y.lowSeen,
      high: y.high,
      highSeen: y.highSeen,
      days: y.flows.map((flow, k): FlowDay => ({
        day: isoDay(Date.UTC(y.year, 0, 1) + k * DAY_MS),
        flow,
        kind: KIND[y.kinds[k] ?? "n"] ?? "normal",
        seen: y.seen[k] === "1",
      })),
    })),
  };
}
