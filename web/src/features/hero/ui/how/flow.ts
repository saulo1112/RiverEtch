// The "How it works" flow chart's data: one station's daily flow through one year, its low-flow
// line, and the days the satellite had a usable pass. Read from the committed files the pipeline
// uses for the same counts (pipeline/src/climate_pipeline/reach/extremes.py): the station's daily
// means (climate/daily.csv, USGS parameter 00060 in ft³/s), the low-flow line of rule v1
// (climate.json, extremes.thresholds.low, in m³/s) and the satellite's usable passes of the v5
// inputs (inputs/usgs-v5/turbidity.csv). Pure, so the tests run it on the full files.

/** Cubic feet to cubic metres, exactly as the pipeline converts them. */
export const FT3_TO_M3 = 0.028316846592;

/** One day of the station's record. */
export interface FlowDay {
  /** ISO date. */
  readonly day: string;
  /** Daily mean discharge, m³/s. */
  readonly flow: number;
  /** The day is at or below the low-flow line. */
  readonly low: boolean;
  /** The satellite had a usable pass that day. */
  readonly seen: boolean;
}

/** One year of one station, as the chart draws it. */
export interface FlowYear {
  readonly year: number;
  readonly station: { readonly id: string; readonly name: string };
  /** Where the daily values come from, as climate.json names it. */
  readonly source: string;
  /** The low-flow line (m³/s): the station's 10th percentile of daily means (rule v1). */
  readonly lowLine: number;
  readonly days: readonly FlowDay[];
  /** Low-flow days and the ones the satellite saw, as climate.json counts them. */
  readonly lowDays: number;
  readonly lowSeen: number;
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
    readonly thresholds: { readonly low: number };
    readonly years: readonly {
      readonly year: number;
      readonly low: number;
      readonly lowSeen: number;
    }[];
  };
}

/**
 * One year of a station's flow, its low-flow line and the satellite's usable passes.
 *
 * @param climateJson - The reach's climate.json.
 * @param dailyCsv - The station's daily.csv (day, parameter, value, approval).
 * @param passesCsv - The v5 inputs' turbidity.csv (site_id, key, datetime_utc, …).
 * @param year - The year.
 * @returns The year, or null when the files lack it.
 */
export function flowYear(
  climateJson: string,
  dailyCsv: string,
  passesCsv: string,
  year: number,
): FlowYear | null {
  const climate = JSON.parse(climateJson) as Climate;
  const counts = climate.extremes?.years.find((y) => y.year === year);
  if (climate.extremes === undefined || counts === undefined) {
    return null;
  }
  const lowLine = climate.extremes.thresholds.low;
  const prefix = `${String(year)}-`;
  const seen = new Set(
    rows(passesCsv)
      .filter((r) => r.site_id === climate.station.id && (r.datetime_utc ?? "").startsWith(prefix))
      .map((r) => (r.datetime_utc ?? "").slice(0, 10)),
  );
  const days = rows(dailyCsv)
    .filter((r) => r.parameter === "00060" && (r.day ?? "").startsWith(prefix) && r.value !== "")
    .map((r): FlowDay => {
      const flow = Number(r.value) * FT3_TO_M3;
      const day = r.day ?? "";
      return { day, flow, low: flow <= lowLine, seen: seen.has(day) };
    });
  return {
    year,
    station: climate.station,
    source: climate.source,
    lowLine,
    days,
    lowDays: counts.low,
    lowSeen: counts.lowSeen,
  };
}
