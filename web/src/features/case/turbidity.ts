// The turbidity a place shows (preregistration-values.md): its value in FNU where the model's value
// is sealed, beside its typical error on the US reaches (the transfer test's) or its class's range
// outside the tested region; a record sealed before that shows its class alone.
import { isOutside } from "../reaches/scene.ts";
import type { Estimate, FnuClass, ReachData, SeriesRow } from "../reaches/types.ts";
import { CASE_COPY, formatValue } from "./content.ts";
import { alongPassOf } from "./spot.ts";

/** A turbidity estimate as the app shows it. */
export interface TurbidityShown {
  /** In FNU (null: a class only). */
  readonly value: number | null;
  readonly cls: FnuClass | null;
  /** The typical error shown beside the value, in percent (null: none is shown). */
  readonly errorPercent: number | null;
}

/**
 * An estimate of a reach with no station, or of a stretch along a reach, as the app shows it.
 *
 * @param reach - The reach (outside the tested region, no error is shown).
 * @param value - Its value in FNU (null: none sealed).
 * @param cls - Its class (null: none).
 * @param transferMdsa - The transfer test's typical error (MdSA, %).
 * @returns What to show (null: no reading).
 */
export function shownOf(
  reach: Pick<ReachData, "card">,
  value: number | null | undefined,
  cls: FnuClass | null | undefined,
  transferMdsa: number,
): TurbidityShown | null {
  if (cls == null && value == null) {
    return null;
  }
  return {
    value: value ?? null,
    cls: cls ?? null,
    errorPercent: value == null || isOutside(reach) ? null : Math.round(transferMdsa),
  };
}

/**
 * A pass's estimate at a reach's reading spot with no station.
 *
 * @param reach - The reach.
 * @param estimate - The pass's turbidity estimate.
 * @param transferMdsa - The transfer test's typical error.
 * @returns What to show (null: no reading).
 */
export function spotShown(
  reach: Pick<ReachData, "card">,
  estimate: Estimate | null | undefined,
  transferMdsa: number,
): TurbidityShown | null {
  return shownOf(reach, estimate?.value, estimate?.fnuClass, transferMdsa);
}

/**
 * A stretch's estimate on a pass, from its along-river record.
 *
 * @param reach - The reach.
 * @param sceneId - The pass.
 * @param index - The window.
 * @param transferMdsa - The transfer test's typical error.
 * @returns What to show (null: no reading).
 */
export function stretchShown(
  reach: ReachData,
  sceneId: string | undefined,
  index: number,
  transferMdsa: number,
): TurbidityShown | null {
  const pass = alongPassOf(reach, sceneId);
  return shownOf(reach, pass?.values?.[index], pass?.classes[index], transferMdsa);
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
 * The estimate's second line beside its value: its typical error and range, or its range.
 *
 * @param shown - The estimate.
 * @returns E.g. "Typical error 37 % · range 50 to 100 FNU" (null: a class alone, nothing beside).
 */
export function secondaryText(shown: TurbidityShown | null): string | null {
  if (shown?.value == null) {
    return null;
  }
  const range =
    shown.cls === null ? null : CASE_COPY.value.range(CASE_COPY.ungauged.classes[shown.cls]);
  const error =
    shown.errorPercent === null ? null : CASE_COPY.value.typicalError(shown.errorPercent);
  // After the error, the range goes on in lower case ("· range 50 to 100 FNU").
  const after =
    range === null || error === null ? range : `${range.charAt(0).toLowerCase()}${range.slice(1)}`;
  const parts = [error, after];
  const text = parts.filter((p) => p !== null).join(" · ");
  return text === "" ? null : text;
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
