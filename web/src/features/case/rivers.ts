// Every river the water-quality validation v5 evaluated (docs/water-quality/report.md): the lock
// box's turbidity error beside guessing the river's usual value, its pairs, coverage and level,
// read from the committed results (results/v5_levels.csv, the rows over the whole range, and
// results/v5_scores.csv for a river with too few pairs to be rated). Never typed by hand.
import type { Level } from "../reaches/types.ts";

/** One evaluated river. */
export interface RiverResult {
  /** The USGS gauge, e.g. "USGS-07374525". */
  readonly site: string;
  /** Lock-box pairs. */
  readonly n: number;
  /** Median symmetric accuracy, %; null when the river was not rated. */
  readonly mdsa: number | null;
  /** The same for guessing the river's usual value (the median of its past values). */
  readonly nullMdsa: number | null;
  readonly coverage90: number | null;
  /** Null: too few pairs to be rated. */
  readonly level: Level | null;
}

/** The demo reaches' gauges (the two the preregistered rule chose). */
export const DEMO_GAUGES: readonly string[] = ["USGS-07374525", "USGS-06805500"];

// A CSV line's cells; a quoted cell may hold commas.
function cells(line: string): string[] {
  const out: string[] = [];
  let cell = "";
  let quoted = false;
  for (const ch of line) {
    if (ch === '"') {
      quoted = !quoted;
    } else if (ch === "," && !quoted) {
      out.push(cell);
      cell = "";
    } else {
      cell += ch;
    }
  }
  out.push(cell);
  return out;
}

function rows(text: string): Record<string, string>[] {
  const [head, ...lines] = text.trim().split(/\r?\n/);
  if (head === undefined) {
    return [];
  }
  const columns = cells(head);
  return lines.map((line) => {
    const values = cells(line);
    return Object.fromEntries(columns.map((c, k) => [c, values[k] ?? ""]));
  });
}

const number = (cell: string | undefined) =>
  cell === undefined || cell === "" || !Number.isFinite(Number(cell)) ? null : Number(cell);

/**
 * The evaluated rivers, lowest error first, then those too thin to rate.
 *
 * @param levels - The text of results/v5_levels.csv.
 * @param scores - The text of results/v5_scores.csv.
 * @returns One row per river.
 */
export function riverResults(levels: string, scores: string): RiverResult[] {
  const rated = rows(levels)
    .filter((r) => r.target === "turbidity" && r.predicted_range === "all")
    .map((r): RiverResult => ({
      site: r.site ?? "",
      n: number(r.n) ?? 0,
      mdsa: number(r.mdsa),
      nullMdsa: number(r.null_mdsa),
      coverage90: number(r.coverage90),
      level: (r.level ?? "none") as Level,
    }))
    .sort((a, b) => (a.mdsa ?? Infinity) - (b.mdsa ?? Infinity));
  const thin = rows(scores)
    .filter(
      (r) =>
        r.target === "turbidity" &&
        r.status === "insufficient_data" &&
        !rated.some((x) => x.site === r.site),
    )
    .map((r): RiverResult => ({
      site: r.site ?? "",
      n: number(r.lockbox_pairs) ?? 0,
      mdsa: null,
      nullMdsa: null,
      coverage90: null,
      level: null,
    }));
  return [...rated, ...thin];
}

/**
 * One decimal, ties to even, as the pipeline's Python writes the report (46.25 reads "46.2").
 *
 * @param value - The number.
 * @returns E.g. "33.1".
 */
export function oneDecimal(value: number): string {
  const scaled = value * 10;
  const floor = Math.floor(scaled);
  const tie = Math.abs(scaled - floor - 0.5) < 1e-9;
  return ((tie ? floor + (floor % 2) : Math.round(scaled)) / 10).toFixed(1);
}

/**
 * The median error over the rated rivers: the honest summary of the method.
 *
 * @param rivers - {@link riverResults}.
 * @returns The median MdSA, %.
 */
export function medianError(rivers: readonly RiverResult[]): number {
  const values = rivers
    .map((r) => r.mdsa)
    .filter((v): v is number => v !== null)
    .sort((a, b) => a - b);
  const mid = Math.floor(values.length / 2);
  return values.length % 2 === 1
    ? (values[mid] ?? Number.NaN)
    : ((values[mid - 1] ?? Number.NaN) + (values[mid] ?? Number.NaN)) / 2;
}
