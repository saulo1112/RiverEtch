// The entry screen's evidence strip: how many rivers the demo covers and how many passes it has
// sealed, counted from the reaches' committed files (vite.config.ts reads them at build time into
// `__REACH_FACTS__`), never typed by hand.

/** What vite.config.ts read from one reach's committed files. */
export interface ReachFacts {
  /** The river, as the reach's `reach.json` names it. */
  readonly river: string;
  /** Lines of its ledgers (Sentinel-2 and Landsat): one per sealed pass. */
  readonly sealed: number;
}

/** The strip's figures. */
export interface Evidence {
  /** Distinct rivers among the cases. */
  readonly rivers: number;
  /** Sealed passes of every case. */
  readonly sealedPasses: number;
}

/**
 * Counts the demo's rivers and sealed passes over its cases.
 *
 * @param caseIds - The cases' site ids (the catalog).
 * @param facts - What the build read per site.
 * @returns The figures, or null if any case has no facts (the strip is then left out).
 */
export function evidenceOf(
  caseIds: readonly string[],
  facts: Readonly<Record<string, ReachFacts>>,
): Evidence | null {
  const found = caseIds.map((id) => facts[id]);
  if (found.length === 0 || found.some((f) => f === undefined)) {
    return null;
  }
  const known = found as readonly ReachFacts[];
  return {
    rivers: new Set(known.map((f) => f.river)).size,
    sealedPasses: known.reduce((sum, f) => sum + f.sealed, 0),
  };
}
