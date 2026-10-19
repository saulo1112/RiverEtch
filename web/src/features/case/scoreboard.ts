// The scoreboard's counts (docs/water-quality/prospective.md, rule v1): the prospective outcomes of
// anchored claims, and two retrospective counts (the 2026 passes sealed after their gauge value
// was public, and the locked test) from the sealed series and the cards. Counts only, never
// percentages: the view shows "k of n".
import { sceneKey, turbidity } from "../reaches/scene.ts";
import type { Outcome, ReachData } from "../reaches/types.ts";
import { insideCount } from "./reading.ts";

/** How many of n compared passes fell inside their expected range. */
export interface Hits {
  readonly inside: number;
  readonly n: number;
}

/** What a prospective claim came to (headline counts use the first read). */
export type ClaimResult = "inside" | "outside" | "pending" | "none" | "abstained" | "noRange";

/** One prospective claim as the scoreboard lists it. */
export interface ClaimRow {
  readonly claim: string;
  readonly sceneId: string;
  readonly target: string;
  readonly unit: string;
  readonly estimate: number | null;
  readonly interval: Outcome["interval"];
  readonly overpassUtc: string;
  readonly result: ClaimResult;
  /** The first read's gauge value (normally provisional). */
  readonly gauge: Outcome["gauge"];
  /** An approved re-read after a provisional first read: listed, never replacing it. */
  readonly approved: Outcome | null;
}

/**
 * Groups the outcomes ledger by claim: one row per claim, its first read, and an approved re-read
 * if one came later. Latest pass first.
 *
 * @param outcomes - The ledger's lines, in order.
 * @returns The rows.
 */
export function claimRows(outcomes: readonly Outcome[]): ClaimRow[] {
  const byClaim = new Map<string, Outcome[]>();
  for (const line of outcomes) {
    const lines = byClaim.get(line.claimRecordSha256) ?? [];
    lines.push(line);
    byClaim.set(line.claimRecordSha256, lines);
  }
  const rows = [...byClaim.entries()].flatMap(([claim, lines]): ClaimRow[] => {
    const head = lines[0];
    if (head === undefined) {
      return [];
    }
    const first = lines.find((l) => l.status === "scored") ?? null;
    const approved =
      first === null || first.gauge?.approval === "Approved"
        ? null
        : (lines.find(
            (l) => l !== first && l.status === "scored" && l.gauge?.approval === "Approved",
          ) ?? null);
    const result: ClaimResult =
      head.status === "abstained"
        ? "abstained"
        : first === null
          ? lines.some((l) => l.final)
            ? "none"
            : "pending"
          : first.inside === null
            ? "noRange"
            : first.inside
              ? "inside"
              : "outside";
    return [
      {
        claim,
        sceneId: head.sceneId,
        target: head.target,
        unit: head.unit,
        estimate: head.estimate,
        interval: head.interval,
        overpassUtc: head.overpassUtc,
        result,
        gauge: first?.gauge ?? null,
        approved,
      },
    ];
  });
  return rows.sort((a, b) => b.overpassUtc.localeCompare(a.overpassUtc));
}

/**
 * The prospective count of one target: claims whose first read fell inside, of those compared.
 *
 * @param rows - {@link claimRows}.
 * @param target - "turbidity" or "water_temperature".
 * @returns The count.
 */
export function prospectiveHits(rows: readonly ClaimRow[], target: string): Hits {
  const compared = rows.filter(
    (r) => r.target === target && (r.result === "inside" || r.result === "outside"),
  );
  return { inside: compared.filter((r) => r.result === "inside").length, n: compared.length };
}

// Before T0 (or with no T0 yet), a pass is retrospective.
function before(t0: string | null, datetimeUtc: string): boolean {
  return t0 === null || datetimeUtc === "" || Date.parse(datetimeUtc) < Date.parse(t0);
}

const within = (value: number, interval: { low: number; high: number }) =>
  interval.low <= value && value <= interval.high;

/**
 * The 2026 passes sealed before T0 that have a gauge value: the sealed interval against the
 * gauge's value at the overpass (approved first, else provisional, as `reach check` reads it).
 *
 * @param reach - The reach's files.
 * @param t0 - The prospective cut-off (null: not anchored yet, so every pass counts here).
 * @returns Turbidity's count, and water temperature's where the reach has it.
 */
export function retrospectiveHits(
  reach: ReachData,
  t0: string | null,
): { turbidity: Hits; temperature: Hits | null } {
  const byKey = new Map(reach.series.map((row) => [sceneKey(row), row]));
  let inside = 0;
  let n = 0;
  for (const check of reach.checks) {
    const row = byKey.get(check.key);
    const interval = row === undefined ? null : (turbidity(row)?.interval ?? null);
    if (check.value === null || interval === null || !before(t0, check.datetimeUtc)) {
      continue;
    }
    n += 1;
    inside += within(check.value, interval) ? 1 : 0;
  }
  const thermal = reach.thermal;
  if (thermal === null) {
    return { turbidity: { inside, n }, temperature: null };
  }
  const bySceneId = new Map(thermal.series.map((row) => [row.sceneId, row]));
  let tInside = 0;
  let tN = 0;
  for (const check of thermal.checks) {
    const interval = bySceneId.get(check.sceneId)?.estimate.interval ?? null;
    if (check.value === null || interval === null || !before(t0, check.datetimeUtc)) {
      continue;
    }
    tN += 1;
    tInside += within(check.value, interval) ? 1 : 0;
  }
  return { turbidity: { inside, n }, temperature: { inside: tInside, n: tN } };
}

/**
 * The locked test's coverage as a count, from the cards.
 *
 * @param reach - The reach's files.
 * @returns Turbidity's count and water temperature's (null where a card or its coverage is missing).
 */
export function lockboxHits(reach: ReachData): {
  turbidity: Hits | null;
  temperature: Hits | null;
} {
  const lock = reach.card?.metrics.lockbox;
  const thermal = reach.thermal?.card?.metrics.lockbox;
  return {
    turbidity:
      lock === undefined ? null : { inside: insideCount(lock.coverage90, lock.n), n: lock.n },
    temperature:
      thermal?.coverage90 === undefined
        ? null
        : { inside: insideCount(thermal.coverage90, thermal.n), n: thermal.n },
  };
}
