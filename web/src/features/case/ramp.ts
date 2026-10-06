// The NDTI color ramp, shared by the river line, the legend and the timeline. A semantic "heat" ramp
// (blue, cyan, amber, red) that always ships with its scale legend; NDTI is a relative index here,
// never converted to NTU.

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

/** NDTI values mapped onto the ends of the ramp (values outside are clamped). */
export const NDTI_DOMAIN = { min: -0.01, max: 0.15 } as const;

/** Color of samples under cloud or without data (the legend shows it hatched), and its opacity. */
export const NO_DATA = { rgb: [150, 162, 186], alpha: 0.45 } as const;

/** An sRGB color as 0..255 channels. */
export type Rgb = readonly [number, number, number];

function parseHex(hex: string): Rgb {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

const RAMP_RGB = NDTI_RAMP.map((stop) => ({ at: stop.at, rgb: parseHex(stop.color) }));

/**
 * Formats a color for CSS and MapLibre.
 *
 * @param rgb - sRGB channels, 0..255.
 * @param alpha - Opacity, 0..1.
 * @returns A comma-separated `rgba()` string (the syntax MapLibre parses).
 */
export function rgba(rgb: Rgb, alpha = 1): string {
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
}

/**
 * Position of an NDTI value on the ramp.
 *
 * @param ndti - NDTI value.
 * @returns 0 at {@link NDTI_DOMAIN}.min, 1 at its max, clamped.
 */
export function ndtiPosition(ndti: number): number {
  const t = (ndti - NDTI_DOMAIN.min) / (NDTI_DOMAIN.max - NDTI_DOMAIN.min);
  return Math.min(1, Math.max(0, t));
}

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
 * Ramp color of an NDTI value.
 *
 * @param ndti - NDTI value, or null for cloud / no data.
 * @returns A CSS color.
 */
export function ndtiColor(ndti: number | null): string {
  return ndti === null ? rgba(NO_DATA.rgb, NO_DATA.alpha) : rgba(rampRgb(ndtiPosition(ndti)));
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
