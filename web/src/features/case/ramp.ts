// The NDTI color ramp, shared by the river's pixels, the legend and the case cards. A semantic
// "heat" ramp (blue, cyan, amber, red) that always ships with its scale legend; NDTI is a relative
// index, never converted to a unit.

/** A stop of the ramp: position (0..1) and sRGB hex color. */
export interface RampStop {
  /** Position along the ramp, 0 = low turbidity, 1 = high. */
  readonly at: number;
  /** sRGB hex color. */
  readonly color: string;
}

/** Ramp stops from low to high NDTI. OKLCH lightness rises to the amber; the red leads by chroma. */
export const NDTI_RAMP: readonly RampStop[] = [
  { at: 0, color: "#2f6df6" },
  { at: 0.38, color: "#22d3ee" },
  { at: 0.7, color: "#f5b942" },
  { at: 1, color: "#ff4f3f" },
];

/** An sRGB color as 0..255 channels. */
export type Rgb = readonly [number, number, number];

function parseHex(hex: string): Rgb {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

const RAMP_RGB = NDTI_RAMP.map((stop) => ({ at: stop.at, rgb: parseHex(stop.color) }));

/**
 * Ramp color at a position, interpolated in sRGB like MapLibre's `interpolate` does.
 *
 * @param position - Position along the ramp (0..1, clamped).
 * @returns The color's sRGB channels.
 */
export function rampRgb(position: number): Rgb {
  const t = Math.min(1, Math.max(0, position));
  const upper = Math.max(
    1,
    RAMP_RGB.findIndex((stop) => stop.at >= t),
  );
  const a = RAMP_RGB[upper - 1];
  const b = RAMP_RGB[upper];
  if (a === undefined || b === undefined) {
    return [0, 0, 0];
  }
  const k = (t - a.at) / (b.at - a.at);
  const mix = (from: number, to: number) => Math.round(from + (to - from) * k);
  return [mix(a.rgb[0], b.rgb[0]), mix(a.rgb[1], b.rgb[1]), mix(a.rgb[2], b.rgb[2])];
}

/**
 * The ramp as a CSS gradient, for legends.
 *
 * @param direction - Gradient direction, e.g. `"to right"`.
 * @returns A `linear-gradient()` value.
 */
export function rampGradientCss(direction = "to right"): string {
  const stops = NDTI_RAMP.map((stop) => `${stop.color} ${(stop.at * 100).toFixed(0)}%`);
  return `linear-gradient(${direction}, ${stops.join(", ")})`;
}
