// The climate context of a reach (`climate.json`, written by `climate-pipeline reach climate`): the
// gauge's own daily record, year by year. Pure: which measures a reach has, each year's value of
// one, and each measure's record year. Nothing here is a satellite estimate.
import type { ClimateRecord } from "./types.ts";

/** What the climate chart shows: the annual peak flow, the 7-day low flow or the warmest day. */
export type ClimateMeasure = "peak" | "low" | "warm";

/** One year of a measure. */
export interface ClimatePoint {
  readonly year: number;
  /** The year's value (null: no full week for the 7-day low). */
  readonly value: number | null;
  /** The day of the peak or of the warmest day; the last day of the 7-day low. */
  readonly day: string | null;
  /** 1 = the most extreme of the ranked years (null: not ranked). */
  readonly rank: number | null;
  /** How many years are ranked. */
  readonly ranked: number;
  readonly complete: boolean;
  readonly toDate: boolean;
  readonly provisional: boolean;
}

/**
 * The measures a reach's gauge record supports.
 *
 * @param record - The reach's climate context.
 * @returns The flows always, the warmest day where the gauge measures water temperature.
 */
export function climateMeasures(record: ClimateRecord): ClimateMeasure[] {
  return record.temperature === null ? ["peak", "low"] : ["peak", "low", "warm"];
}

/**
 * Every year of one measure, oldest first.
 *
 * @param record - The reach's climate context.
 * @param measure - The measure.
 * @returns The years (empty for the warmest day where the gauge has no temperature).
 */
export function climatePoints(record: ClimateRecord, measure: ClimateMeasure): ClimatePoint[] {
  if (measure === "warm") {
    const heat = record.temperature;
    return (heat?.years ?? []).map((y) => ({
      year: y.year,
      value: y.warmest,
      day: y.warmestDay,
      rank: y.warmestRank,
      ranked: heat?.rankedYears ?? 0,
      complete: y.complete,
      toDate: y.toDate,
      provisional: y.provisional,
    }));
  }
  const flow = record.discharge;
  return flow.years.map((y) => ({
    year: y.year,
    value: measure === "peak" ? y.peak : y.low7,
    day: measure === "peak" ? y.peakDay : y.low7Day,
    rank: measure === "peak" ? y.peakRank : y.low7Rank,
    ranked: flow.rankedYears,
    complete: y.complete,
    toDate: y.toDate,
    provisional: y.provisional,
  }));
}

/** A kind of extreme day (rule v1): low flow, high flow, warm water. */
export type ExtremeKind = "low" | "high" | "warm";

/**
 * The kinds of extreme day a reach's record counts.
 *
 * @param record - The reach's climate context.
 * @returns Low and high flow, and warm water where the gauge measures temperature (none without
 *   the extremes block).
 */
export function extremeKinds(record: ClimateRecord): ExtremeKind[] {
  const e = record.extremes;
  if (e === undefined) {
    return [];
  }
  return e.thresholds.warm === null ? ["low", "high"] : ["low", "high", "warm"];
}

/**
 * Every year's count of one kind of extreme day, oldest first, as chart points.
 *
 * @param record - The reach's climate context.
 * @param kind - The kind.
 * @returns The years (warm water: only the years with a summer temperature).
 */
export function extremePoints(record: ClimateRecord, kind: ExtremeKind): ClimatePoint[] {
  const e = record.extremes;
  if (e === undefined) {
    return [];
  }
  return e.years.flatMap((y) => {
    const value = y[kind];
    if (value === null) {
      return [];
    }
    return [
      {
        year: y.year,
        value,
        day: null,
        rank: y[`${kind}Rank`],
        ranked: kind === "warm" ? e.rankedYears.warm : e.rankedYears.flow,
        complete: kind === "warm" ? y.warmComplete : y.complete,
        toDate: y.toDate,
        provisional: false,
      },
    ];
  });
}

/**
 * A measure's record year: ranked first (the latest of a tie).
 *
 * @param points - The measure's years ({@link climatePoints}).
 * @returns The year, or null when no year is ranked.
 */
export function recordYear(points: readonly ClimatePoint[]): ClimatePoint | null {
  return points.filter((p) => p.rank === 1).at(-1) ?? null;
}

/**
 * An English ordinal.
 *
 * @param n - A positive whole number.
 * @returns E.g. "1st", "2nd", "13th", "72nd".
 */
export function ordinal(n: number): string {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : (["th", "st", "nd", "rd"][n % 10] ?? "th");
  return `${String(n)}${suffix}`;
}
