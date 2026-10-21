// The series as CSV, as the map toolbar's Export writes it: one row per pass, the sealed values of
// its turbidity estimate and indices, the station's value for context, and the record's
// fingerprint, so "Check a file" can match each row to its sealed record.
import { sceneKey } from "./scene.ts";
import type { ReachData, SeriesRow } from "./types.ts";

/**
 * The reach's 2026 passes as CSV.
 *
 * @param reach - Its passes and the station's values at them.
 * @returns The file's text.
 */
export function csvOfSeries(reach: Pick<ReachData, "series" | "checks">): string {
  const head = [
    "date",
    "sceneId",
    "level",
    "turbidity_fnu",
    "interval90_low",
    "interval90_high",
    "abstain_reason",
    "turbidity_class",
    "gauge_fnu",
    "gauge_approval",
    "ndti_upstream",
    "ndti_downstream",
    "recordSha256",
  ];
  const lines = reach.series.map((row: SeriesRow) => {
    const e = row.estimates.find((x) => x.target === "turbidity");
    const key = sceneKey(row);
    const gauge = reach.checks.find((c) => c.key === key);
    const cells = [
      row.date,
      row.sceneId,
      e?.level ?? "",
      e?.value ?? "",
      e?.interval?.low ?? "",
      e?.interval?.high ?? "",
      e?.abstainReason ?? "",
      e?.fnuClass ?? "",
      gauge?.value ?? "",
      gauge?.value === null || gauge === undefined ? "" : gauge.approval,
      row.indices.ndti.upstream ?? "",
      row.indices.ndti.downstream ?? "",
      row.recordSha256,
    ];
    return cells
      .map((c) => (/[",]/.test(String(c)) ? `"${String(c).replace(/"/g, '""')}"` : String(c)))
      .join(",");
  });
  return `${[head.join(","), ...lines].join("\n")}\n`;
}
