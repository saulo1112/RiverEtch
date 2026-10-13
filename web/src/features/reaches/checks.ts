// The prospective check's CSV (`checks/checks.csv`, written by `climate-pipeline reach check`):
// each recorded pass beside the gauge's value at its overpass, labelled approved or provisional.
import type { GaugeCheck } from "./types.ts";

/**
 * Parses the prospective check's CSV (`checks/checks.csv`).
 *
 * @param text - The file.
 * @returns One row per scene; empty cells become null.
 */
export function parseChecks(text: string): GaugeCheck[] {
  const [head, ...lines] = text.trim().split(/\r?\n/);
  if (head === undefined) {
    return [];
  }
  const columns = head.split(",");
  const at = (name: string) => columns.indexOf(name);
  const number = (cell: string | undefined) => {
    const value = cell === undefined || cell === "" ? Number.NaN : Number(cell);
    return Number.isFinite(value) ? value : null;
  };
  return lines.map((line) => {
    const cells = line.split(",");
    return {
      key: cells[at("key")] ?? "",
      date: cells[at("date")] ?? "",
      estimate: number(cells[at("estimate")]),
      value: number(cells[at("value")]),
      approval: cells[at("approval")] ?? "",
    };
  });
}
