// Joins one pass of a reach across its files: the series row, its NDTI map, the gauge's value at
// the overpass and its turbidity estimate.
import type { Estimate, FnuClass, GaugeCheck, ReachData, SeriesRow, ThermalRow } from "./types.ts";

/**
 * A pass's acquisition key, from its scene id (`<site>:<key>`). Not from its record file: a pass
 * read again with a newer card is a second file of the same pass (`<date>_<key>.<hash>.json`).
 *
 * @param row - The series row.
 * @returns The key, e.g. `sentinel-2c_2026-10-11_R126`.
 */
export function sceneKey(row: Pick<SeriesRow, "sceneId">): string {
  return row.sceneId.split(":").at(-1) ?? row.sceneId;
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

/** The basis of a reach with no gauge outside the region the model was tested in. */
export const OUTSIDE_BASIS = "outside_tested_region";

/**
 * Whether a reach with no gauge lies outside the region the model was tested in
 * (docs/water-quality/preregistration-outside-us.md): a class, with no error estimate at all.
 *
 * @param reach - The reach (its card is enough).
 * @returns True for a card with the basis `outside_tested_region`.
 */
export function isOutside(reach: Pick<ReachData, "card">): boolean {
  return reach.card?.basis === OUTSIDE_BASIS;
}

/** The three classes of preregistration-transfer.md, lowest first (a card without classes). */
export const FNU_CLASSES = ["under_30", "30_to_100", "100_and_over"] as const;

// Each class's range in FNU (the upper end excluded; null: none).
const CLASS_RANGE: Readonly<Record<FnuClass, readonly [number, number | null]>> = {
  under_30: [0, 30],
  "30_to_50": [30, 50],
  "50_to_100": [50, 100],
  "30_to_100": [30, 100],
  "100_and_over": [100, null],
};

/**
 * A reach's class edges in FNU: its card's (four classes since preregistration-four-classes.md
 * passed), else the three classes' 30 and 100.
 *
 * @param reach - The reach (its card is enough).
 * @returns The edges, lowest first.
 */
export function classEdges(reach: Pick<ReachData, "card">): readonly number[] {
  return reach.card?.classes?.edgesFnu ?? [30, 100];
}

/**
 * Where a class sits on a reach's class scale, from 0 (the bottom of the lowest band) to the
 * number of bands. A class wider than one band (a record sealed with three classes, on a reach
 * that now has four) spans the bands it covers.
 *
 * @param cls - The class.
 * @param edges - The reach's class edges.
 * @returns Its lower and upper ends on the scale.
 */
export function classSpan(cls: FnuClass, edges: readonly number[]): readonly [number, number] {
  const [low, high] = CLASS_RANGE[cls];
  const index = (v: number) => edges.filter((e) => v >= e).length;
  return [index(low), high === null ? edges.length + 1 : index(high)];
}

/**
 * Whether the pass published a turbidity value, or, on a reach with no gauge, a class.
 *
 * @param row - The series row.
 * @returns True for a value with its interval, or a class.
 */
export function hasValue(row: SeriesRow): boolean {
  const estimate = turbidity(row);
  return (
    (typeof estimate?.value === "number" && estimate.interval != null) || estimate?.fnuClass != null
  );
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
