// Turbidity classes along a whole reach (`along/windows.json` and `along/series.json`, written by
// `climate-pipeline reach along`, preregistration-along-river.md), and water-temperature classes
// on the same windows (`along-temperature/series.json`, preregistration-along-temperature.md):
// which pass and window a cell is, where a window sits on the river, where the reading spot can
// go, and each class's colour.
import type {
  AlongData,
  AlongPass,
  AlongTemperaturePass,
  FnuClass,
  ReachData,
  TemperatureClass,
} from "./types.ts";

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

/** The six water-temperature classes along the river, coldest first. */
export const TEMPERATURE_CLASSES: readonly TemperatureClass[] = [
  "under_10",
  "10_to_15",
  "15_to_20",
  "20_to_25",
  "25_to_30",
  "30_and_over",
];

/** The edges between them, in °C (a value on an edge is in the upper class). */
export const TEMPERATURE_EDGES: readonly number[] = [10, 15, 20, 25, 30];

/**
 * Each temperature class's colour: one rose hue, pale for cold water and deeper as it warms, so
 * the order reads by lightness alone (checked with the dataviz skill's validator against the
 * panels' surface). Every use pairs it with the class's words.
 */
export const TEMPERATURE_COLORS: Readonly<Record<TemperatureClass, string>> = {
  under_10: "#ffe9ed",
  "10_to_15": "#ffc5cf",
  "15_to_20": "#f2a0ae",
  "20_to_25": "#e27a8f",
  "25_to_30": "#cb5672",
  "30_and_over": "#ac3a58",
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

/**
 * Each water-temperature pass along the river, with the index of its pass in the reach's
 * temperature series; passes the series does not list are left out.
 *
 * @param reach - The reach.
 * @returns The passes, oldest first, each with its temperature series index.
 */
export function thermalPasses(reach: ReachData): { pass: AlongTemperaturePass; index: number }[] {
  const at = new Map((reach.thermal?.series ?? []).map((row, index) => [row.sceneId, index]));
  return (reach.alongTemperature ?? [])
    .flatMap((pass) => {
      const index = at.get(pass.sceneId);
      return index === undefined ? [] : [{ pass, index }];
    })
    .sort((a, b) => a.pass.date.localeCompare(b.pass.date) || a.index - b.index);
}

/**
 * Metres between two points (an equirectangular approximation, fine within a reach).
 *
 * @param lng0 - The first point's longitude.
 * @param lat0 - Its latitude.
 * @param lng1 - The second point's longitude.
 * @param lat1 - Its latitude.
 * @returns The distance in metres.
 */
export function metres(lng0: number, lat0: number, lng1: number, lat1: number): number {
  const scale = Math.cos((((lat0 + lat1) / 2) * Math.PI) / 180);
  return Math.hypot((lng1 - lng0) * scale, lat1 - lat0) * 111_320;
}

/**
 * The placed window nearest a point (the reading spot snaps to it).
 *
 * @param along - The reach's classes along the river.
 * @param lng - Longitude.
 * @param lat - Latitude.
 * @param within - The farthest a window may be, in metres.
 * @returns Its index in the plan (null: none within reach).
 */
export function nearestWindow(
  along: AlongData,
  lng: number,
  lat: number,
  within = Infinity,
): number | null {
  let best: number | null = null;
  let distance = within;
  along.plan.windows.forEach((w, k) => {
    const d = metres(lng, lat, w.lon, w.lat);
    if (w.selected && d <= distance) {
      best = k;
      distance = d;
    }
  });
  return best;
}

/**
 * Where the reading spot starts: the placed window nearest the reach's station, or its reading
 * spot where it has no station (the point its records are read at).
 *
 * @param reach - The reach.
 * @returns The window's index (null: no geometry or no window).
 */
export function startWindow(reach: ReachData): number | null {
  const point = reach.geometry?.features.find((f) => f.properties.kind === "station");
  if (reach.along == null || point?.geometry.type !== "Point") {
    return null;
  }
  const [lng, lat] = point.geometry.coordinates as [number, number];
  return nearestWindow(reach.along, lng, lat);
}

/**
 * The next placed window upstream (-1) or downstream (+1) of one.
 *
 * @param along - The reach's classes along the river.
 * @param from - The window's index.
 * @param step - -1 upstream, +1 downstream.
 * @returns The next window's index (null: none that way).
 */
export function stepWindow(along: AlongData, from: number, step: -1 | 1): number | null {
  for (let k = from + step; k >= 0 && k < along.plan.windows.length; k += step) {
    if (along.plan.windows[k]?.selected === true) {
      return k;
    }
  }
  return null;
}

/**
 * A window's stretch of river, in km from the upstream end.
 *
 * @param along - The reach's classes along the river.
 * @param k - The window's index.
 * @returns Its two ends, one decimal each (null: no such window).
 */
export function stretchKm(along: AlongData, k: number): readonly [string, string] | null {
  const w = along.plan.windows[k];
  if (w === undefined) {
    return null;
  }
  const half = along.plan.spacingM / 2;
  return [
    (Math.max(0, w.chainageM - half) / 1000).toFixed(1),
    ((w.chainageM + half) / 1000).toFixed(1),
  ];
}
