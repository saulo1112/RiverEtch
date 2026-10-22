// Turbidity classes along a whole reach (`along/windows.json` and `along/series.json`, written by
// `climate-pipeline reach along`, preregistration-along-river.md): which pass and window a cell
// is, where a window sits on the river, and each class's colour.
import type { AlongData, AlongPass, FnuClass, ReachData } from "./types.ts";

/** The four classes along the river, clearest first. */
export const ALONG_CLASSES: readonly FnuClass[] = [
  "under_30",
  "30_to_50",
  "50_to_100",
  "100_and_over",
];

/**
 * Each class's colour: from clear water (teal) to muddy water (red earth), darker as the water
 * gets muddier, so the order reads without the hue. Every use pairs it with the class's words.
 */
export const CLASS_COLORS: Readonly<Record<string, string>> = {
  under_15: "#9ee6dc",
  "15_to_30": "#9ee6dc",
  under_30: "#9ee6dc",
  "30_to_50": "#e8c35a",
  "30_to_100": "#e8c35a",
  "50_to_100": "#f0a04b",
  "100_and_over": "#d9603b",
};

/**
 * A pass's classes as the map paints them: RGBA for each place byte along the reach (alpha 0 where
 * the nearest window has no class).
 *
 * @param along - The reach's classes along the river.
 * @param pass - The pass (null: no class anywhere).
 * @param length - The river's length.
 * @returns 256 × 4 bytes.
 */
export function classTable(
  along: AlongData,
  pass: AlongPass | null,
  length: number,
): Uint8ClampedArray {
  const table = new Uint8ClampedArray(256 * 4);
  for (let g = 0; g < 256; g += 1) {
    const window = windowAt(along, g / 255, length);
    const cls = window === null || pass === null ? null : (pass.classes[window] ?? null);
    const hex = cls === null ? undefined : CLASS_COLORS[cls];
    if (hex !== undefined) {
      table.set([...hexRgb(hex), 255], g * 4);
    }
  }
  return table;
}

// "#9ee6dc" as [158, 230, 220].
function hexRgb(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/**
 * The river's length the map's places are fractions of (the centreline's, as the profile uses).
 *
 * @param reach - The reach.
 * @returns Its length in metres (0 without geometry or windows).
 */
export function riverLength(reach: ReachData): number {
  const features = reach.geometry?.features ?? [];
  const river = features.find((f) => f.properties.kind === "river");
  const line = features.find((f) => f.properties.kind === "centreline");
  const chain = (line?.properties as { chainageM?: readonly number[] } | undefined)?.chainageM;
  const length = river?.properties.lengthM ?? chain?.at(-1);
  if (typeof length === "number" && length > 0) {
    return length;
  }
  const last = reach.along?.plan.windows.at(-1);
  return last === undefined ? 0 : last.chainageM + (reach.along?.plan.firstM ?? 0);
}

/**
 * Where a window sits on the river, as the map's probe takes it.
 *
 * @param chainageM - The window's distance from the upstream end.
 * @param length - The river's length.
 * @returns A fraction from 0 (upstream) to 1 (downstream).
 */
export function placeOf(chainageM: number, length: number): number {
  return length > 0 ? Math.min(1, Math.max(0, chainageM / length)) : 0;
}

/**
 * The window nearest a place on the river.
 *
 * @param along - The reach's classes along the river.
 * @param place - A fraction from 0 (upstream) to 1 (downstream).
 * @param length - The river's length.
 * @returns The window's index (null: no window).
 */
export function windowAt(along: AlongData, place: number, length: number): number | null {
  const target = place * length;
  let best: number | null = null;
  let distance = Infinity;
  along.plan.windows.forEach((w, k) => {
    const d = Math.abs(w.chainageM - target);
    if (d < distance) {
      best = k;
      distance = d;
    }
  });
  return best;
}

/**
 * Each pass along the river, with the index of its pass in the reach's series (the map and the
 * record follow that index); passes the series does not list are left out.
 *
 * @param reach - The reach.
 * @returns The passes, oldest first, each with its series index.
 */
export function alongPasses(reach: ReachData): { pass: AlongPass; index: number }[] {
  const at = new Map(reach.series.map((row, index) => [row.sceneId, index]));
  return (reach.along?.passes ?? [])
    .flatMap((pass) => {
      const index = at.get(pass.sceneId);
      return index === undefined ? [] : [{ pass, index }];
    })
    .sort((a, b) => a.pass.date.localeCompare(b.pass.date) || a.index - b.index);
}

/**
 * How many of a pass's windows have a class.
 *
 * @param pass - The pass.
 * @returns The count.
 */
export function readCount(pass: AlongPass): number {
  return pass.classes.filter((c) => c !== null).length;
}
