// Joins one pass of a reach across its files: the series row, its NDTI map, the gauge's value at
// the overpass and its turbidity estimate.
import type { Estimate, GaugeCheck, ReachData, SeriesRow, ThermalRow } from "./types.ts";

/**
 * A pass's acquisition key, from its record file (`records/<date>_<key>.json`).
 *
 * @param row - The series row.
 * @returns The key, e.g. `sentinel-2c_2026-10-11_R126`.
 */
export function sceneKey(row: SeriesRow): string {
  const name = row.file.split("/").at(-1) ?? "";
  return name
    .replace(/\.json$/, "")
    .split("_")
    .slice(1)
    .join("_");
}

/**
 * The pass's turbidity estimate.
 *
 * @param row - The series row.
 * @returns The estimate (null when the record has none).
 */
export function turbidity(row: SeriesRow): Estimate | null {
  return row.estimates.find((e) => e.target === "turbidity") ?? null;
}

/**
 * Whether the reach has no gauge: its passes carry a class only, and nothing is ever scored.
 *
 * @param reach - The reach.
 * @returns True for an ungauged reach (preregistration-transfer.md, section 5).
 */
export function isUngauged(reach: ReachData): boolean {
  return reach.info.station.source === "ungauged";
}

/** The order of the turbidity classes, lowest first. */
export const FNU_CLASSES = ["under_30", "30_to_100", "100_and_over"] as const;

/**
 * Whether the pass published a turbidity value.
 *
 * @param row - The series row.
 * @returns True for a value with its interval.
 */
export function hasValue(row: SeriesRow): boolean {
  const estimate = turbidity(row);
  return typeof estimate?.value === "number" && estimate.interval != null;
}

/**
 * The pass's NDTI map.
 *
 * @param reach - The reach.
 * @param row - The series row.
 * @returns The map's path in the reach's folder, or null when it was not drawn.
 */
export function mapFile(reach: ReachData, row: SeriesRow): string | null {
  const key = sceneKey(row);
  return reach.maps?.maps.find((m) => m.key === key)?.file ?? null;
}

/**
 * The pass in true color (the same box as its NDTI map).
 *
 * @param reach - The reach.
 * @param row - The series row.
 * @returns The image's path in the reach's folder, or null when it was not drawn.
 */
export function photoFile(reach: ReachData, row: SeriesRow): string | null {
  const key = sceneKey(row);
  return reach.maps?.maps.find((m) => m.key === key)?.trueColor ?? null;
}

/**
 * The gauge's value at the pass's overpass.
 *
 * @param reach - The reach.
 * @param row - The series row.
 * @returns The check row with a value, or null.
 */
export function gaugeAt(reach: ReachData, row: SeriesRow): GaugeCheck | null {
  const key = sceneKey(row);
  const found = reach.checks.find((c) => c.key === key);
  return found !== undefined && found.value !== null ? found : null;
}

/**
 * The pass a case opens on: the latest with a turbidity value, else the latest.
 *
 * @param series - The reach's series, by date.
 * @returns Its index (-1 for an empty series).
 */
export function defaultScene(series: readonly SeriesRow[]): number {
  for (let k = series.length - 1; k >= 0; k -= 1) {
    const row = series[k];
    if (row !== undefined && hasValue(row)) {
      return k;
    }
  }
  return series.length - 1;
}

/**
 * The NDTI medians of every pass (both sub-reaches), for the ramp's domain.
 *
 * @param series - The reach's series.
 * @returns The finite values.
 */
export function ndtiMedians(series: readonly SeriesRow[]): number[] {
  return series
    .flatMap((row) => [row.indices.ndti.upstream, row.indices.ndti.downstream])
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
}

/**
 * The water-temperature pass a case shows first: the latest with a value, else the latest.
 *
 * @param series - The reach's Landsat passes, by date (`thermal/series.json`).
 * @returns Its index (null for none).
 */
export function defaultThermal(series: readonly ThermalRow[]): number | null {
  for (let k = series.length - 1; k >= 0; k -= 1) {
    if (typeof series[k]?.estimate.value === "number") {
      return k;
    }
  }
  return series.length > 0 ? series.length - 1 : null;
}

/**
 * The place a reach's water-temperature card was validated, when it is not the reach's own gauge.
 *
 * @param reach - The reach.
 * @returns E.g. "Baton Rouge", or null.
 */
export function thermalValidatedAt(reach: ReachData): string | null {
  const name = reach.thermal?.card?.validationSiteName;
  if (name === undefined) {
    return null;
  }
  const place = name.split(",")[0] ?? name;
  return place.replace(/^.* at /, "");
}

// A Landsat pass counts as "at" a Sentinel-2 pass within this many days.
const NEAREST_DAYS = 16;
const DAY_MS = 86_400_000;

/**
 * The Landsat pass nearest to a day that has a temperature value.
 *
 * @param series - The reach's Landsat passes.
 * @param date - The day (ISO).
 * @returns Its index, or null when none lies within 16 days.
 */
export function nearestThermal(series: readonly ThermalRow[], date: string): number | null {
  let best: number | null = null;
  let gap = Infinity;
  series.forEach((row, index) => {
    const days =
      Math.abs(Date.parse(`${row.date}T00:00:00Z`) - Date.parse(`${date}T00:00:00Z`)) / DAY_MS;
    if (typeof row.estimate.value === "number" && days < gap) {
      best = index;
      gap = days;
    }
  });
  return gap <= NEAREST_DAYS ? best : null;
}
