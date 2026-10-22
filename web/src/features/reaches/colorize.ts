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
  /**
   * Colour usable water by its stretch's turbidity class instead of the NDTI ramp: RGBA per place
   * byte (256 entries; alpha 0 marks a stretch with no class on the pass).
   */
  readonly classes?: Uint8ClampedArray | null;
  /**
   * Paint every water pixel by its class, ignoring the pass's unusable pixels: an earlier year
   * drawn on a 2026 pass's water outline, whose clouds are not its own.
   */
  readonly wholeRiver?: boolean;
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
// A stretch of river the pass gave no class: faint, so the river's shape stays.
const NO_CLASS_RGB = [200, 210, 230] as const;

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

/** The pixels a {@link Colorizer} frame changed: their bounding box, in pixels (null: none). */
export interface DirtyRect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

/**
 * The pixels of {@link colorize}, for one packed map drawn at many reveals (the river filling in).
 * A pixel's place along the reach is one byte, so the map has only 256 places: the inside pixels
 * are grouped by place once, and a frame recolors only the places whose fade changed since the
 * last frame (the moving front, about a twentieth of the map), each pixel by the same expressions
 * as `colorize`, so the bytes are the same.
 */
export class Colorizer {
  private readonly packed: Uint8ClampedArray;
  private readonly width: number;
  private readonly out: Uint8ClampedArray;
  private readonly options: Omit<ColorizeOptions, "reveal">;
  /** Inside pixels' indices, grouped by place byte; place g owns order[start[g]..start[g+1]). */
  private readonly order: Uint32Array;
  private readonly start = new Uint32Array(257);
  /** The fade each place was last drawn with (-1: hidden; NaN: never drawn). */
  private readonly drawn = new Float64Array(256).fill(Number.NaN);

  /**
   * Groups the map's inside pixels by place and clears the rest.
   *
   * @param packed - The PNG's RGBA bytes, as for `colorize`.
   * @param width - Its width in pixels.
   * @param out - Where to write (same length); its pixels outside the reach end transparent.
   * @param options - Domain and look (the reveal is each frame's).
   */
  constructor(
    packed: Uint8ClampedArray,
    width: number,
    out: Uint8ClampedArray,
    options: Omit<ColorizeOptions, "reveal">,
  ) {
    this.packed = packed;
    this.width = width;
    this.out = out;
    this.options = options;
    const counts = new Uint32Array(256);
    for (let p = 0; p < packed.length; p += 4) {
      if ((packed[p + 3] ?? 0) === 0) {
        out[p + 3] = 0;
      } else {
        counts[packed[p + 1] ?? 0] = (counts[packed[p + 1] ?? 0] ?? 0) + 1;
      }
    }
    for (let g = 0; g < 256; g += 1) {
      this.start[g + 1] = (this.start[g] ?? 0) + (counts[g] ?? 0);
    }
    this.order = new Uint32Array(this.start[256] ?? 0);
    const next = this.start.slice(0, 256);
    for (let i = 0, p = 0; p < packed.length; i += 1, p += 4) {
      if ((packed[p + 3] ?? 0) !== 0) {
        const g = packed[p + 1] ?? 0;
        this.order[next[g] ?? 0] = i;
        next[g] = (next[g] ?? 0) + 1;
      }
    }
  }

  /**
   * Colors the map at a reveal, touching only the places whose fade changed.
   *
   * @param reveal - Share of the reach shown, from the upstream anchor (0..1).
   * @returns The bounding box of the pixels written (null when none changed).
   */
  render(reveal: number): DirtyRect | null {
    const { packed, width, out, options } = this;
    const [lo, hi] = options.packed;
    const [dmin, dmax] = options.domain;
    const span = dmax - dmin || 1;
    const front = reveal + options.feather;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -1;
    let maxY = -1;
    for (let g = 0; g < 256; g += 1) {
      const place = g / 255;
      const hidden = reveal <= 0 || place > front;
      const edge = hidden
        ? -1
        : options.feather > 0
          ? Math.min(1, (front - place) / options.feather)
          : 1;
      if (edge === this.drawn[g] || (this.start[g] ?? 0) === (this.start[g + 1] ?? 0)) {
        this.drawn[g] = edge;
        continue;
      }
      this.drawn[g] = edge;
      for (let k = this.start[g] ?? 0; k < (this.start[g + 1] ?? 0); k += 1) {
        const i = this.order[k] ?? 0;
        const p = i * 4;
        const x = i % width;
        const y = (i - x) / width;
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
        if (hidden) {
          out[p + 3] = 0;
          continue;
        }
        const code = packed[p + 2] ?? 0;
        const byte = packed[p] ?? 0;
        const whole = options.wholeRiver === true && options.classes != null;
        if (!whole && ((code & UNUSABLE_BIT) !== 0 || byte === 0)) {
          const stroke = (x + y) % HATCH < 2;
          out[p] = HATCH_RGB[0];
          out[p + 1] = HATCH_RGB[1];
          out[p + 2] = HATCH_RGB[2];
          out[p + 3] = Math.round((stroke ? 150 : 40) * edge);
          continue;
        }
        const classes = options.classes;
        if (classes != null) {
          const c = g * 4;
          const read = (classes[c + 3] ?? 0) > 0;
          out[p] = read ? (classes[c] ?? 0) : NO_CLASS_RGB[0];
          out[p + 1] = read ? (classes[c + 1] ?? 0) : NO_CLASS_RGB[1];
          out[p + 2] = read ? (classes[c + 2] ?? 0) : NO_CLASS_RGB[2];
          out[p + 3] = Math.round((read ? 255 * options.opacity : 46) * edge);
          continue;
        }
        const ndti = lo + ((byte - 1) / 254) * (hi - lo);
        const t = Math.min(1, Math.max(0, (ndti - dmin) / span));
        const lut = Math.round(t * (LUT_SIZE - 1)) * 3;
        out[p] = LUT[lut] ?? 0;
        out[p + 1] = LUT[lut + 1] ?? 0;
        out[p + 2] = LUT[lut + 2] ?? 0;
        out[p + 3] = Math.round(255 * options.opacity * edge);
      }
    }
    return maxX < 0 ? null : { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 };
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
