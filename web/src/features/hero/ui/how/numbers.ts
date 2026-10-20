// The "Does it work?" chapter's numbers, computed from the committed results (never typed): the
// middle station of the v5 locked test, how many stations beat guessing the usual value (one rule
// throughout: reading.ts gainOver), and the test on rivers the model never saw. Pure, so the
// tests run it on the same files.
import { gainOver } from "../../../case/reading.ts";
import { riverResults, transferResults, type RiverResult } from "../../../case/rivers.ts";

/** The middle station of the locked test and the tally around it. */
export interface Headline {
  /** "About N times smaller", as the app words a gain (reading.ts). */
  readonly times: string;
  readonly site: string;
  /** Its median error and guessing the usual value's, %. */
  readonly satellite: number;
  readonly guess: number;
  readonly n: number;
  /** Stations that clearly beat guessing, show no clear gain, and do worse. */
  readonly good: number;
  readonly none: number;
  readonly worse: number;
}

/**
 * The middle station (by its gain over guessing) of the rated stations of the v5 locked test.
 *
 * @param levels - results/v5_levels.csv.
 * @param scores - results/v5_scores.csv.
 * @returns The headline, or null when no station was rated.
 */
export function headline(levels: string, scores: string): Headline | null {
  const rated = riverResults(levels, scores).filter(
    (r): r is RiverResult & { mdsa: number; nullMdsa: number } =>
      r.level !== null && r.mdsa !== null && r.nullMdsa !== null,
  );
  const byGain = [...rated].sort((a, b) => b.nullMdsa / b.mdsa - a.nullMdsa / a.mdsa);
  const middle = byGain[Math.floor(byGain.length / 2)];
  if (middle === undefined) {
    return null;
  }
  const gain = gainOver(middle.mdsa, middle.nullMdsa);
  const kinds = rated.map((r) => gainOver(r.mdsa, r.nullMdsa).kind);
  return {
    times: gain.kind === "times" ? gain.text : "1",
    site: middle.site,
    satellite: middle.mdsa,
    guess: middle.nullMdsa,
    n: rated.length,
    good: kinds.filter((k) => k === "times").length,
    none: kinds.filter((k) => k === "none").length,
    worse: kinds.filter((k) => k === "worse").length,
  };
}

/** A locked test's stations, as the chapter draws them. */
export interface StationSet {
  /** Every scored station, lowest error first. */
  readonly rows: readonly (RiverResult & { mdsa: number; nullMdsa: number })[];
  /** Stations with too few test passes to be scored. */
  readonly unscored: readonly RiverResult[];
  /** Stations that clearly beat guessing the usual value (the app's rule, reading.ts gainOver). */
  readonly beat: number;
  /** Stations that reached no level (they fail). */
  readonly fail: number;
}

function stationSet(results: readonly RiverResult[]): StationSet {
  const rows = results.filter(
    (r): r is RiverResult & { mdsa: number; nullMdsa: number } =>
      r.mdsa !== null && r.nullMdsa !== null,
  );
  return {
    rows,
    unscored: results.filter((r) => r.mdsa === null || r.nullMdsa === null),
    beat: rows.filter((r) => gainOver(r.mdsa, r.nullMdsa).kind === "times").length,
    fail: rows.filter((r) => r.level === "none").length,
  };
}

/**
 * The test on rivers the model never saw (results/transfer/transfer_scores.csv).
 *
 * @param scores - The CSV's text.
 * @returns Its stations and the two counts.
 */
export function neverSaw(scores: string): StationSet {
  return stationSet(transferResults(scores));
}

/**
 * The v5 locked test, each station scored by a model trained on its own river's earlier years
 * (results/v5_levels.csv and v5_scores.csv).
 *
 * @param levels - v5_levels.csv.
 * @param scores - v5_scores.csv.
 * @returns Its stations and the two counts.
 */
export function ownRiver(levels: string, scores: string): StationSet {
  return stationSet(riverResults(levels, scores));
}

/**
 * How many rivers the test on rivers the model never saw covered: its river groups, each held out
 * in turn (results/transfer/transfer_scores.csv, A4, the preregistered folds).
 *
 * @param scores - The CSV's text.
 * @returns The number of river groups.
 */
export function riversTested(scores: string): number {
  const [head, ...lines] = scores.trim().split(/\r?\n/);
  const columns = (head ?? "").split(",");
  const at = (name: string) => columns.indexOf(name);
  const groups = new Set(
    lines
      .map((line) => line.split(","))
      .filter((c) => c[at("candidate")] === "A4" && c[at("report_only")] === "false")
      .map((c) => c[at("group")] ?? ""),
  );
  return groups.size;
}
