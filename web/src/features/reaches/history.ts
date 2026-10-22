// A station window's earlier years (`history.json`, written by `climate-pipeline reach history`,
// preregistration-along-river.md, section 5): the turbidity chart of a year before the sealed
// records, read only, from the same frozen card.
import type { HistoryRow, ReachData, SeriesRow } from "./types.ts";

/**
 * The years a reach's turbidity chart can show: its earlier years, then its sealed year(s).
 *
 * @param reach - The reach.
 * @returns The years, newest first.
 */
export function chartYears(reach: ReachData): number[] {
  const years = new Set<number>();
  for (const row of reach.history ?? []) {
    years.add(Number(row.date.slice(0, 4)));
  }
  for (const row of reach.series) {
    years.add(Number(row.date.slice(0, 4)));
  }
  return [...years].sort((a, b) => b - a);
}

/**
 * The year of the reach's sealed records (the chart's default).
 *
 * @param reach - The reach.
 * @returns The latest pass's year.
 */
export function sealedYear(reach: ReachData): number {
  return Number((reach.series.at(-1)?.date ?? "2026-01-01").slice(0, 4));
}

/**
 * An earlier year as a series the turbidity chart can draw (read only: no map, no record).
 *
 * @param reach - The reach.
 * @param year - The year.
 * @returns The reach with that year's passes as its series.
 */
export function yearReach(reach: ReachData, year: number): ReachData {
  const rows = (reach.history ?? []).filter((r) => r.date.startsWith(String(year)));
  const unit = reach.card?.unit ?? "FNU";
  const level = reach.card?.levels.find((l) => l.predicted_range === "all")?.level ?? "none";
  const series: SeriesRow[] = rows.map((r) => ({
    date: r.date,
    sceneId: `${reach.info.site}:${r.key}`,
    file: "",
    recordSha256: "",
    indices: {
      ndti: { upstream: null, downstream: null, reach: null, delta: null },
      nirRed: null,
    },
    estimates: [
      {
        target: "turbidity",
        unit,
        level: r.fnuClass !== null ? "unvalidated" : level,
        value: r.value,
        interval:
          r.low !== null && r.high !== null
            ? { low: r.low, high: r.high, coverage: 0.9, method: "mondrian_split_conformal_log" }
            : null,
        fnuClass: r.fnuClass,
        abstainReason: r.reason,
      },
    ],
  }));
  return { ...reach, series, checks: [] };
}

/**
 * What a year's passes were to the model, for the chart's note.
 *
 * @param rows - The reach's earlier passes.
 * @param year - The year.
 * @returns Each phase the year's passes fall in, in date order.
 */
export function yearPhases(rows: readonly HistoryRow[], year: number): HistoryRow["phase"][] {
  const out: HistoryRow["phase"][] = [];
  for (const r of rows) {
    if (r.date.startsWith(String(year)) && !out.includes(r.phase)) {
      out.push(r.phase);
    }
  }
  return out;
}
