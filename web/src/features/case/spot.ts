// The reading spot that moves (preregistration-along-temperature.md, section 3): where it is, and
// what each stretch of river reads on each pass, for the panels that follow it. Away from the
// start a stretch shows a class from the along-river records, never a value.
import { stretchKm } from "../reaches/along.ts";
import { isOutside } from "../reaches/scene.ts";
import type {
  AlongPass,
  AlongTemperaturePass,
  FnuClass,
  ReachData,
  TemperatureClass,
} from "../reaches/types.ts";
import { CASE_COPY } from "./content.ts";

/** One pass on a stretch's chart: its index in the series it selects, its day and its class. */
export interface BandPoint {
  readonly index: number;
  readonly date: string;
  /** Its class (null: no reading, so no mark). */
  readonly cls: string | null;
}

/** The reading spot, away from the start: its window and its stretch of river in words. */
export interface Spot {
  /** The window's index in the reach's plan. */
  readonly index: number;
  /** The window's id, e.g. `w07`. */
  readonly id: string;
  /** E.g. "km 3.0 to 3.6". */
  readonly stretch: string;
}

/**
 * The reading spot at a window.
 *
 * @param reach - The reach.
 * @param index - The window's index (null: the start).
 * @returns The spot (null at the start, or for a window the plan does not have).
 */
export function spotOf(reach: ReachData, index: number | null): Spot | null {
  const along = reach.along;
  if (index === null || along == null) {
    return null;
  }
  const window = along.plan.windows[index];
  const km = stretchKm(along, index);
  return window === undefined || km === null
    ? null
    : { index, id: window.id, stretch: CASE_COPY.spot.stretch(km[0], km[1]) };
}

/**
 * A Sentinel-2 pass's along-river record.
 *
 * @param reach - The reach.
 * @param sceneId - The pass.
 * @returns Its classes along the river (null: none for that pass).
 */
export function alongPassOf(reach: ReachData, sceneId: string | undefined): AlongPass | null {
  return reach.along?.passes.find((p) => p.sceneId === sceneId) ?? null;
}

/**
 * A Landsat pass's along-river temperature record.
 *
 * @param reach - The reach.
 * @param sceneId - The pass.
 * @returns Its classes along the river (null: none for that pass).
 */
export function temperaturePassOf(
  reach: ReachData,
  sceneId: string | undefined,
): AlongTemperaturePass | null {
  return reach.alongTemperature?.find((p) => p.sceneId === sceneId) ?? null;
}

/**
 * A stretch's turbidity class on a pass.
 *
 * @param reach - The reach.
 * @param sceneId - The Sentinel-2 pass.
 * @param index - The window's index.
 * @returns The class (null: no reading).
 */
export function turbidityAt(
  reach: ReachData,
  sceneId: string | undefined,
  index: number,
): FnuClass | null {
  return alongPassOf(reach, sceneId)?.classes[index] ?? null;
}

/**
 * A stretch's water-temperature class on a Landsat pass.
 *
 * @param reach - The reach.
 * @param sceneId - The Landsat pass.
 * @param index - The window's index.
 * @returns The class (null: no reading).
 */
export function temperatureAt(
  reach: ReachData,
  sceneId: string | undefined,
  index: number,
): TemperatureClass | null {
  return temperaturePassOf(reach, sceneId)?.classes[index] ?? null;
}

/**
 * A stretch's turbidity classes over the year, one point per pass of the reach's series.
 *
 * @param reach - The reach.
 * @param index - The window's index.
 * @returns The points, in the series' order.
 */
export function turbidityPoints(reach: ReachData, index: number): BandPoint[] {
  return reach.series.map((row, k) => ({
    index: k,
    date: row.date,
    cls: turbidityAt(reach, row.sceneId, index),
  }));
}

/**
 * A stretch's water-temperature classes over the year, one point per Landsat pass.
 *
 * @param reach - The reach.
 * @param index - The window's index.
 * @returns The points, in the temperature series' order.
 */
export function temperaturePoints(reach: ReachData, index: number): BandPoint[] {
  return (reach.thermal?.series ?? []).map((row, k) => ({
    index: k,
    date: row.date,
    cls: temperatureAt(reach, row.sceneId, index),
  }));
}

/**
 * What a stretch's turbidity class is worth, as section 3 words it: the test on rivers the model
 * never saw on a US reach (its counts from the four-class test's result file), or that its error
 * has not been measured outside the United States.
 *
 * @param reach - The reach.
 * @param four - The four-class test's counts (`__FOUR_CLASSES__`; null before it ran).
 * @returns The sentence behind the class's (?) (empty when the test's result is missing).
 */
export function turbidityHelp(
  reach: ReachData,
  four: { readonly model_matched: number; readonly n: number } | null,
): string {
  if (isOutside(reach)) {
    return CASE_COPY.spot.outsideHelp;
  }
  return four === null ? "" : CASE_COPY.spot.usHelp(four.model_matched, four.n);
}
