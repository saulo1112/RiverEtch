// The prospective check's CSV (`checks/checks.csv`, written by `climate-pipeline reach check`):
// each recorded pass beside the gauge's value at its overpass, labelled approved or provisional.
import type { ContextReading, GaugeCheck, ThermalCheck } from "./types.ts";

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

// A CSV's rows as records of their columns (no quoted commas in these files).
function rows(text: string): Record<string, string>[] {
  const [head, ...lines] = text.trim().split(/\r?\n/);
  if (head === undefined) {
    return [];
  }
  const columns = head.split(",");
  return lines.map((line) => {
    const cells = line.split(",");
    return Object.fromEntries(columns.map((c, k) => [c, cells[k] ?? ""]));
  });
}

function number(cell: string | undefined): number | null {
  const value = cell === undefined || cell === "" ? Number.NaN : Number(cell);
  return Number.isFinite(value) ? value : null;
}

/**
 * Parses the gauge's water temperature at each Landsat pass (`thermal/checks.csv`).
 *
 * @param text - The file.
 * @returns One row per pass.
 */
export function parseThermalChecks(text: string): ThermalCheck[] {
  return rows(text).map((r) => ({
    sceneId: r.sceneId ?? "",
    date: r.date ?? "",
    value: number(r.value),
    approval: r.approval ?? "",
  }));
}

/**
 * Parses the gauge's own readings at each pass (`checks/context.csv`).
 *
 * @param text - The file.
 * @returns One row per reading with a value.
 */
export function parseContext(text: string): ContextReading[] {
  return rows(text).flatMap((r) => {
    const value = number(r.value);
    return value === null
      ? []
      : [
          {
            key: r.key ?? "",
            parameter: r.parameter ?? "",
            name: r.name ?? "",
            value,
            unit: r.unit ?? "",
            approval: r.approval ?? "",
          },
        ];
  });
}
