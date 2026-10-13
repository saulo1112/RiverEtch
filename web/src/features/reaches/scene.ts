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
