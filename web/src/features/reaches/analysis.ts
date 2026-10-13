// Reads a pass's packed NDTI map (maps.json's encoding) the way a viewer's tools do: the pixel under
// the cursor, the profile along the river, and the pass's statistics. NDTI stays relative.
import type { LngLat, MapsIndex } from "./types.ts";

/** One pixel of a packed map. */
export interface PixelReading {
  /** NDTI, or null where the pass left the pixel unusable. */
  readonly ndti: number | null;
  /** Place along the reach, 0 at the upstream anchor to 1 at the downstream one. */
  readonly place: number;
  /** The part of the corridor: `upstream`, `downstream` or `between`. */
  readonly part: string;
  /** The pass left the pixel usable (no cloud, glint or missing data). */
  readonly usable: boolean;
}

/** A pass's statistics over its corridor. */
export interface PassStats {
  /** Water pixels in the corridor. */
  readonly water: number;
  /** Of them, usable on this pass. */
  readonly usable: number;
  /** NDTI percentiles (10, 50, 90) of the usable pixels, or null. */
  readonly percentiles: readonly [number, number, number] | null;
  /** Counts of usable pixels per NDTI bin across `domain`. */
  readonly histogram: readonly number[];
}

/** One step of the profile along the river. */
export interface ProfilePoint {
  /** Place along the reach (bin centre, 0..1). */
  readonly place: number;
  /** Median NDTI of the bin's usable pixels, or null. */
  readonly ndti: number | null;
  /** Share of the bin's water the pass left usable. */
  readonly usable: number;
}

const UNUSABLE_BIT = 4;

function mercator([lng, lat]: LngLat): [number, number] {
  const rad = (lat * Math.PI) / 180;
  return [(lng + 180) / 360, (1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2];
}

/**
 * The pixel of a map under a geographic point. The map is drawn between its four corners; over a
 * reach the grid is a parallelogram in Web Mercator, so the top-left, top-right and bottom-left
 * corners fix it.
 *
 * @param maps - The maps' index (corners and size).
 * @param point - `[lng, lat]`.
 * @returns Column and row, or null outside the image.
 */
export function pixelAt(maps: MapsIndex, point: LngLat): { col: number; row: number } | null {
  const [tl, tr, , bl] = maps.corners.map(mercator) as [
    [number, number],
    [number, number],
    [number, number],
    [number, number],
  ];
  const [px, py] = mercator(point);
  const ax = tr[0] - tl[0];
  const ay = tr[1] - tl[1];
  const bx = bl[0] - tl[0];
  const by = bl[1] - tl[1];
  const det = ax * by - ay * bx;
  if (det === 0) {
    return null;
  }
  const dx = px - tl[0];
  const dy = py - tl[1];
  const u = (dx * by - dy * bx) / det;
  const v = (ax * dy - ay * dx) / det;
  if (u < 0 || u >= 1 || v < 0 || v >= 1) {
    return null;
  }
  return { col: Math.floor(u * maps.width), row: Math.floor(v * maps.height) };
}

function partName(maps: MapsIndex, code: number): string {
  const base = code & ~UNUSABLE_BIT;
  return Object.entries(maps.encoding.b).find(([, v]) => v === base)?.[0] ?? "between";
}

function ndtiOf(maps: MapsIndex, byte: number): number {
  const [lo, hi] = maps.encoding.r.ndti;
  return lo + ((byte - 1) / 254) * (hi - lo);
}

/**
 * Reads one pixel of a packed map.
 *
 * @param maps - The maps' index (encoding).
 * @param data - The map's RGBA bytes.
 * @param col - Column.
 * @param row - Row.
 * @returns The reading, or null outside the corridor.
 */
export function readPixel(
  maps: MapsIndex,
  data: Uint8ClampedArray,
  col: number,
  row: number,
): PixelReading | null {
  const p = (row * maps.width + col) * 4;
  if ((data[p + 3] ?? 0) === 0) {
    return null;
  }
  const byte = data[p] ?? 0;
  const code = data[p + 2] ?? 0;
  const usable = (code & UNUSABLE_BIT) === 0 && byte > 0;
  return {
    ndti: usable ? ndtiOf(maps, byte) : null,
    place: (data[p + 1] ?? 0) / 255,
    part: partName(maps, code),
    usable,
  };
}

function percentile(sorted: readonly number[], q: number): number {
  const at = Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))));
  return sorted[at] ?? Number.NaN;
}

/**
 * The pass's statistics: its water, the usable share, NDTI percentiles and a histogram.
 *
 * @param maps - The maps' index (encoding).
 * @param data - The map's RGBA bytes.
 * @param domain - The NDTI range the histogram spans.
 * @param bins - Histogram bins.
 * @returns The statistics.
 */
export function passStats(
  maps: MapsIndex,
  data: Uint8ClampedArray,
  domain: readonly [number, number],
  bins = 24,
): PassStats {
  const counts = new Array<number>(bins).fill(0);
  const bytes = new Array<number>(256).fill(0);
  let water = 0;
  let usable = 0;
  for (let p = 0; p < data.length; p += 4) {
    if ((data[p + 3] ?? 0) === 0) {
      continue;
    }
    water += 1;
    const byte = data[p] ?? 0;
    if (((data[p + 2] ?? 0) & UNUSABLE_BIT) !== 0 || byte === 0) {
      continue;
    }
    usable += 1;
    bytes[byte] = (bytes[byte] ?? 0) + 1;
  }
  const values: number[] = [];
  for (let byte = 1; byte < 256; byte += 1) {
    const n = bytes[byte] ?? 0;
    if (n === 0) {
      continue;
    }
    const ndti = ndtiOf(maps, byte);
    const t = (ndti - domain[0]) / (domain[1] - domain[0] || 1);
    const bin = Math.min(bins - 1, Math.max(0, Math.floor(t * bins)));
    counts[bin] = (counts[bin] ?? 0) + n;
    // A compact sample for the percentiles: each byte value with its weight, capped.
    for (let k = 0; k < Math.min(n, 400); k += 1) {
      values.push(ndti);
    }
  }
  values.sort((a, b) => a - b);
  return {
    water,
    usable,
    percentiles:
      values.length === 0
        ? null
        : [percentile(values, 0.1), percentile(values, 0.5), percentile(values, 0.9)],
    histogram: counts,
  };
}

/**
 * The profile along the river: the median NDTI and the usable share of each stretch.
 *
 * @param maps - The maps' index (encoding).
 * @param data - The map's RGBA bytes.
 * @param bins - Stretches from the upstream anchor to the downstream one.
 * @returns One point per stretch.
 */
export function profile(maps: MapsIndex, data: Uint8ClampedArray, bins = 96): ProfilePoint[] {
  const perBin = Array.from({ length: bins }, () => new Array<number>(256).fill(0));
  const water = new Array<number>(bins).fill(0);
  const used = new Array<number>(bins).fill(0);
  for (let p = 0; p < data.length; p += 4) {
    if ((data[p + 3] ?? 0) === 0) {
      continue;
    }
    const bin = Math.min(bins - 1, Math.floor(((data[p + 1] ?? 0) / 256) * bins));
    water[bin] = (water[bin] ?? 0) + 1;
    const byte = data[p] ?? 0;
    if (((data[p + 2] ?? 0) & UNUSABLE_BIT) !== 0 || byte === 0) {
      continue;
    }
    used[bin] = (used[bin] ?? 0) + 1;
    const counts = perBin[bin];
    if (counts !== undefined) {
      counts[byte] = (counts[byte] ?? 0) + 1;
    }
  }
  return perBin.map((counts, bin) => {
    const n = used[bin] ?? 0;
    let median: number | null = null;
    if (n > 0) {
      let seen = 0;
      for (let byte = 1; byte < 256; byte += 1) {
        seen += counts[byte] ?? 0;
        if (seen * 2 >= n) {
          median = ndtiOf(maps, byte);
          break;
        }
      }
    }
    const w = water[bin] ?? 0;
    return { place: (bin + 0.5) / bins, ndti: median, usable: w === 0 ? 0 : n / w };
  });
}
