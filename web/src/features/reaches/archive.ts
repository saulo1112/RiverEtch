// The earlier years, 2019 to 2025 (`archive/<year>.json` and `archive-temperature/<year>.json`,
// written once by `climate-pipeline reach archive`, preregistration-archive.md): recomputed from
// the public images with the frozen models, never sealed. An earlier year becomes a reach the case
// view shows like its sealed year: the start's estimate as its series, the classes along the river
// as its along-river passes, the station's water temperature as its temperature series; with what
// each pass was to the model, and no record, map image, check or station reading of its own.
import type {
  AlongTemperaturePass,
  ArchivePhase,
  Estimate,
  FnuClass,
  Level,
  ReachData,
  SeriesRow,
  TemperatureClass,
  ThermalRow,
} from "./types.ts";

/** One earlier Sentinel-2 pass: the start's estimate and every window's class. */
export interface ArchivePass {
  readonly sceneId: string;
  readonly date: string;
  readonly phase: ArchivePhase;
  readonly station: {
    readonly level: Level;
    readonly value: number | null;
    readonly low: number | null;
    readonly high: number | null;
    readonly fnuClass: FnuClass | null;
    readonly reason: string | null;
  } | null;
  readonly classes: readonly (FnuClass | null)[];
  readonly reasons: readonly (string | null)[];
}

/** One earlier Landsat pass: the station's water temperature and every window's class. */
export interface ArchiveTemperaturePass {
  readonly sceneId: string;
  readonly date: string;
  readonly platform: string;
  readonly phase: ArchivePhase;
  readonly station: {
    readonly level: Level;
    readonly value: number | null;
    readonly low: number | null;
    readonly high: number | null;
    readonly waterPixels: number;
  } | null;
  readonly classes: readonly (TemperatureClass | null)[];
  readonly reasons: readonly (string | null)[];
}

/** A year's file. */
export interface ArchiveYear<P> {
  readonly year: number;
  readonly codeCommit: string;
  readonly passes: readonly P[];
}

const NO_INDEX = { upstream: null, downstream: null, reach: null, delta: null };

/**
 * An earlier year as a reach the case view can show.
 *
 * @param reach - The reach (its sealed year).
 * @param year - The year's Sentinel-2 file.
 * @param temperature - The year's Landsat file (null: none, or a reach without one).
 * @param outline - The 2026 map whose water outline the classes are painted on.
 * @returns The reach, its year's passes in place of its records.
 */
export function archiveReach(
  reach: ReachData,
  year: ArchiveYear<ArchivePass>,
  temperature: ArchiveYear<ArchiveTemperaturePass> | null,
  outline: string | null,
): ReachData {
  const unit = reach.card?.unit ?? "FNU";
  const series: SeriesRow[] = year.passes.map((p) => {
    const s = p.station;
    const estimate = {
      target: "turbidity",
      unit,
      level: s?.level ?? "none",
      value: s?.value ?? null,
      interval:
        s?.low != null && s.high != null
          ? { low: s.low, high: s.high, coverage: 0.9, method: "mondrian_split_conformal_log" }
          : null,
      fnuClass: s?.fnuClass ?? null,
      abstainReason: s?.reason ?? null,
    } as unknown as Estimate;
    return {
      date: p.date,
      sceneId: p.sceneId,
      file: "",
      recordSha256: "",
      indices: { ndti: NO_INDEX, nirRed: null },
      estimates: [estimate],
    };
  });
  const phases: Record<string, ArchivePhase> = {};
  for (const p of year.passes) {
    phases[p.sceneId] = p.phase;
  }
  const thermal: ThermalRow[] = (temperature?.passes ?? []).map((p) => {
    phases[p.sceneId] = p.phase;
    return {
      date: p.date,
      sceneId: p.sceneId,
      file: "",
      recordSha256: "",
      platform: p.platform,
      waterPixels: p.station?.waterPixels ?? 0,
      estimate: {
        level: p.station?.level ?? "none",
        value: p.station?.value ?? null,
        interval:
          p.station?.low != null && p.station.high != null
            ? { low: p.station.low, high: p.station.high, coverage: 0.9, method: "conformal" }
            : null,
        unit: "°C",
      },
    };
  });
  const alongTemperature: AlongTemperaturePass[] = (temperature?.passes ?? []).map((p) => ({
    sceneId: p.sceneId,
    date: p.date,
    recordSha256: "",
    classes: p.classes,
    reasons: p.reasons,
  }));
  return {
    ...reach,
    series,
    checks: [],
    context: [],
    outcomes: [],
    thermal:
      reach.thermal === null ? null : { series: thermal, checks: [], card: reach.thermal.card },
    along:
      reach.along == null
        ? null
        : {
            plan: reach.along.plan,
            passes: year.passes.map((p) => ({
              sceneId: p.sceneId,
              date: p.date,
              recordSha256: "",
              classes: p.classes,
              reasons: p.reasons,
            })),
          },
    alongTemperature: reach.thermal === null ? null : alongTemperature,
    archive: { year: year.year, file: `archive/${String(year.year)}.json`, phases, outline },
  };
}

/**
 * The phases of a year's passes, in date order, each once.
 *
 * @param reach - An earlier year's reach.
 * @returns Its phases (empty for the sealed year).
 */
export function yearPhases(reach: ReachData): ArchivePhase[] {
  const out: ArchivePhase[] = [];
  for (const row of reach.series) {
    const phase = reach.archive?.phases[row.sceneId];
    if (phase !== undefined && !out.includes(phase)) {
      out.push(phase);
    }
  }
  return out;
}

/**
 * The year of a reach's sealed records (or of an earlier year's reach, its year).
 *
 * @param reach - The reach.
 * @returns The year.
 */
export function reachYear(reach: ReachData): number {
  return reach.archive?.year ?? Number((reach.series.at(-1)?.date ?? "2026-01-01").slice(0, 4));
}

/**
 * The years a reach can show: the sealed year, then each earlier year with passes.
 *
 * @param reach - The reach.
 * @returns The years, newest first.
 */
export function caseYears(reach: ReachData): number[] {
  const sealed = reachYear(reach);
  return [sealed, ...(reach.archiveYears ?? []).filter((y) => y < sealed)].sort((a, b) => b - a);
}
