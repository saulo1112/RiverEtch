// The turbidity a place shows (preregistration-values.md): its value in FNU where the model's value
// is sealed, beside its class's range; a record sealed before that shows its class alone.
import { isUngauged, turbidity } from "../reaches/scene.ts";
import type { Estimate, FnuClass, ReachData, SeriesRow } from "../reaches/types.ts";
import { CASE_COPY, formatValue } from "./content.ts";
import { alongPassOf } from "./spot.ts";

/** A turbidity estimate as the app shows it. */
export interface TurbidityShown {
  /** In FNU (null: a class only). */
  readonly value: number | null;
  readonly cls: FnuClass | null;
}

/**
 * An estimate of a reach with no station, or of a stretch along a reach, as the app shows it.
 *
 * @param value - Its value in FNU (null: none sealed).
 * @param cls - Its class (null: none).
 * @returns What to show (null: no reading).
 */
export function shownOf(
  value: number | null | undefined,
  cls: FnuClass | null | undefined,
): TurbidityShown | null {
  if (cls == null && value == null) {
    return null;
  }
  return { value: value ?? null, cls: cls ?? null };
}

/**
 * A pass's estimate at a reach's reading spot with no station.
 *
 * @param estimate - The pass's turbidity estimate.
 * @returns What to show (null: no reading).
 */
export function spotShown(estimate: Estimate | null | undefined): TurbidityShown | null {
  return shownOf(estimate?.value, estimate?.fnuClass);
}

/**
 * A stretch's estimate on a pass, from its along-river record.
 *
 * @param reach - The reach.
 * @param sceneId - The pass.
 * @param index - The window.
 * @returns What to show (null: no reading).
 */
export function stretchShown(
  reach: ReachData,
  sceneId: string | undefined,
  index: number,
): TurbidityShown | null {
  const pass = alongPassOf(reach, sceneId);
  return shownOf(pass?.values?.[index], pass?.classes[index]);
}

/**
 * The estimate's first line: its value with its unit, or its class.
 *
 * @param shown - The estimate (null: none).
 * @returns E.g. "62.3 FNU", "Under 30 FNU" or "No reading".
 */
export function primaryText(shown: TurbidityShown | null): string {
  if (shown === null) {
    return CASE_COPY.noReading;
  }
  if (shown.value !== null) {
    return `${formatValue(shown.value)} FNU`;
  }
  return shown.cls === null ? CASE_COPY.noReading : CASE_COPY.ungauged.classes[shown.cls];
}

/**
 * The estimate's second line beside its value: its class's range (docs/decisions.md, D26).
 *
 * @param shown - The estimate.
 * @returns E.g. "Range 50 to 100 FNU" (null: a class alone, nothing beside).
 */
export function secondaryText(shown: TurbidityShown | null): string | null {
  if (shown?.value == null || shown.cls === null) {
    return null;
  }
  return CASE_COPY.value.range(CASE_COPY.ungauged.classes[shown.cls]);
}

/** How far apart the station's value and its own stretch's may be before the pass is called unclear. */
export const UNCLEAR_FACTOR = 3;

/**
 * Whether a pass at a station's reach is unclear: the station's value and the value of the stretch
 * it stands in differ by more than a factor of three (decided after seeing 29 Dec 2025 at the
 * Platte, 431 FNU against 40.6; the same rule for every pass of every reach with a station).
 *
 * @param reach - The reach.
 * @param row - The pass.
 * @returns True when both values exist and differ by more than the factor.
 */
export function unclearAtStation(reach: ReachData, row: SeriesRow | null): boolean {
  if (row === null || isUngauged(reach)) {
    return false;
  }
  const station = turbidity(row)?.value;
  // The station stands in the plan's first window.
  const stretch = alongPassOf(reach, row.sceneId)?.values?.[0];
  if (typeof station !== "number" || typeof stretch !== "number" || station <= 0 || stretch <= 0) {
    return false;
  }
  const ratio = stretch / station;
  return ratio > UNCLEAR_FACTOR || ratio < 1 / UNCLEAR_FACTOR;
}

/**
 * Whether a stretch's along-river records carry values (preregistration-values.md).
 *
 * @param reach - The reach.
 * @returns True once any pass has them.
 */
export function stretchValued(reach: ReachData): boolean {
  return reach.along?.passes.some((p) => p.values !== undefined) ?? false;
}

/**
 * A stretch as a reach of its own for the value chart: each pass's estimate is the stretch's value
 * and class on it, with no station beside it.
 *
 * @param reach - The reach.
 * @param index - The window.
 * @returns The reach, its series' estimates the stretch's.
 */
export function stretchReach(reach: ReachData, index: number): ReachData {
  return {
    ...reach,
    checks: [],
    series: reach.series.map((row): SeriesRow => {
      const pass = alongPassOf(reach, row.sceneId);
      const estimate: Estimate = {
        target: "turbidity",
        unit: "FNU",
        level: "unvalidated",
        value: pass?.values?.[index] ?? null,
        interval: null,
        fnuClass: pass?.classes[index] ?? null,
      };
      return { ...row, estimates: [estimate] };
    }),
  };
}
