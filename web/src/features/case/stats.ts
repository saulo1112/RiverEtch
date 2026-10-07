// Small statistics over NDTI samples, shared by the fixture and the panels.
import type { NdtiScene } from "./types.ts";

/**
 * Arithmetic mean.
 *
 * @param values - Numbers to average (at least one).
 * @returns Their mean.
 */
export function mean(values: readonly number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

/**
 * Mean NDTI of a scene's valid samples on one side of the split point.
 *
 * @param scene - The scene.
 * @param sampleProgress - Position of each sample along the reach (0 = upstream).
 * @param split - Split position along the reach (0..1).
 * @param side - Window: samples before the split (`upstream`) or from it on (`downstream`).
 * @returns The mean, or null when every sample in the window is cloudy or missing.
 */
export function windowMean(
  scene: NdtiScene,
  sampleProgress: readonly number[],
  split: number,
  side: "upstream" | "downstream",
): number | null {
  const values = scene.values.filter((value, index): value is number => {
    const p = sampleProgress[index] ?? 0;
    return value !== null && (side === "upstream" ? p < split : p >= split);
  });
  return values.length === 0 ? null : mean(values);
}
