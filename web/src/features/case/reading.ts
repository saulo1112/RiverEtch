// Pure helpers that turn a model card's locked-test numbers into words a reader can use: how many
// times smaller the satellite's error is than guessing the river's usual value, how many test
// passes fell inside the 90 % range, and which way an estimate tends to lean. No React, so the
// web tests run them directly. (Ordinals come from `reaches/climate.ts`.)

/** How the satellite's error compares with guessing the river's usual value. */
export type Gain =
  | { readonly kind: "times"; readonly text: string }
  | { readonly kind: "none" }
  | { readonly kind: "worse" };

/** Below this ratio the gain is too small to call (the two errors are within 15 % of each other). */
const MIN_GAIN = 1.15;

/**
 * The satellite's gain over guessing the river's usual value, from the two locked-test errors.
 *
 * @param satellite - The model's error (MdSA in % or MAE in °C).
 * @param baseline - The baseline's error, in the same unit.
 * @returns "about N times smaller" (a whole number from 2, one decimal below), no clear gain, or
 *   worse than the baseline.
 */
export function gainOver(satellite: number, baseline: number): Gain {
  if (!(satellite > 0) || !(baseline > 0)) {
    return { kind: "none" };
  }
  const ratio = baseline / satellite;
  if (ratio < 1 / MIN_GAIN) {
    return { kind: "worse" };
  }
  if (ratio < MIN_GAIN) {
    return { kind: "none" };
  }
  return { kind: "times", text: ratio >= 2 ? String(Math.round(ratio)) : ratio.toFixed(1) };
}

/**
 * How many of a locked test's passes fell inside their 90 % range, from its coverage share.
 *
 * @param coverage - Share of passes inside (0..1), as the card states it.
 * @param n - Passes in the locked test.
 * @returns The whole count (the card's share is rounded from it).
 */
export function insideCount(coverage: number, n: number): number {
  return Math.round(coverage * n);
}

/** Which way a value tends to lean, in words. */
export type Lean =
  | { readonly kind: "warm" | "cold" | "high" | "low"; readonly text: string }
  | { readonly kind: "none" };

/**
 * A temperature bias (°C) in words: under 0.25 °C either way there is no clear lean.
 *
 * @param bias - Mean of estimate minus gauge, °C.
 * @returns Warm, cold or none, with the amount to one decimal.
 */
export function leanOfTemperature(bias: number): Lean {
  if (!Number.isFinite(bias) || Math.abs(bias) < 0.25) {
    return { kind: "none" };
  }
  return { kind: bias > 0 ? "warm" : "cold", text: Math.abs(bias).toFixed(1) };
}

/**
 * A turbidity bias (SSPB, %) in words: under 5 % either way there is no clear lean.
 *
 * @param sspb - Symmetric signed percentage bias.
 * @returns High, low or none, with the amount as a whole percentage.
 */
export function leanOfTurbidity(sspb: number): Lean {
  if (!Number.isFinite(sspb) || Math.abs(sspb) < 5) {
    return { kind: "none" };
  }
  return { kind: sspb > 0 ? "high" : "low", text: Math.abs(sspb).toFixed(0) };
}
