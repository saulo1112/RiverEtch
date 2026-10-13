// Turns a packed NDTI map (maps.json, written by `climate-pipeline reach render`) into the pixels
// the case map draws: each usable water pixel on the NDTI ramp, unusable ones hatched, and the
// river revealed from its upstream anchor down to `reveal` with a soft leading edge.
import { rampRgb } from "../case/ramp.ts";

/** How a map is drawn. */
export interface ColorizeOptions {
  /** NDTI values at the ends of the ramp: the reach's own range, so colors compare scenes. */
  readonly domain: readonly [number, number];
  /** The NDTI the packed bytes 1..255 span (`maps.json` → encoding.r.ndti). */
  readonly packed: readonly [number, number];
  /** Share of the reach shown, from the upstream anchor (0..1). */
  readonly reveal: number;
  /** Length of the soft leading edge, as a share of the reach. */
  readonly feather: number;
  /** Opacity of usable water. */
  readonly opacity: number;
}

const LUT_SIZE = 256;
const LUT = (() => {
  const table = new Uint8ClampedArray(LUT_SIZE * 3);
  for (let k = 0; k < LUT_SIZE; k += 1) {
    const [r, g, b] = rampRgb(k / (LUT_SIZE - 1));
    table.set([r, g, b], k * 3);
  }
  return table;
})();
const UNUSABLE_BIT = 4;
// Hatch of unusable pixels: a light stroke every HATCH pixels along the diagonal.
const HATCH = 7;
const HATCH_RGB = [190, 200, 220] as const;

/**
 * Colors a packed map into RGBA pixels.
 *
 * @param packed - The PNG's RGBA bytes (R: NDTI, G: place along the reach, B: part, A: inside).
 * @param width - Its width in pixels.
 * @param out - Where to write (same length).
 * @param options - Domain, reveal and look.
 */
export function colorize(
  packed: Uint8ClampedArray,
  width: number,
  out: Uint8ClampedArray,
  options: ColorizeOptions,
): void {
  const [lo, hi] = options.packed;
  const [dmin, dmax] = options.domain;
  const span = dmax - dmin || 1;
  const front = options.reveal + options.feather;
  for (let i = 0, p = 0; p < packed.length; i += 1, p += 4) {
    const inside = packed[p + 3] ?? 0;
    const place = (packed[p + 1] ?? 0) / 255;
    if (inside === 0 || options.reveal <= 0 || place > front) {
      out[p + 3] = 0;
      continue;
    }
    const edge = options.feather > 0 ? Math.min(1, (front - place) / options.feather) : 1;
    const code = packed[p + 2] ?? 0;
    const byte = packed[p] ?? 0;
    if ((code & UNUSABLE_BIT) !== 0 || byte === 0) {
      const x = i % width;
      const y = (i - x) / width;
      const stroke = (x + y) % HATCH < 2;
      out[p] = HATCH_RGB[0];
      out[p + 1] = HATCH_RGB[1];
      out[p + 2] = HATCH_RGB[2];
      out[p + 3] = Math.round((stroke ? 150 : 40) * edge);
      continue;
    }
    const ndti = lo + ((byte - 1) / 254) * (hi - lo);
    const t = Math.min(1, Math.max(0, (ndti - dmin) / span));
    const k = Math.round(t * (LUT_SIZE - 1)) * 3;
    out[p] = LUT[k] ?? 0;
    out[p + 1] = LUT[k + 1] ?? 0;
    out[p + 2] = LUT[k + 2] ?? 0;
    out[p + 3] = Math.round(255 * options.opacity * edge);
  }
}

/**
 * The reach's own NDTI range: the medians of its records, widened by a quarter on each side.
 *
 * @param values - Sub-reach NDTI medians across the records.
 * @returns The ramp's domain (a fallback when there are fewer than two values).
 */
export function ndtiDomain(values: readonly number[]): [number, number] {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length < 2) {
    return [-0.1, 0.1];
  }
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const pad = Math.max(0.01, (max - min) * 0.25);
  return [min - pad, max + pad];
}
