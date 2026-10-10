// Pure helpers of the hero globe's mouse drag (no three, no DOM), so they can be unit-tested.
// Angles in degrees unless a name says otherwise.

/**
 * Keeps a latitude offset such that `base + offset` stays within ±`limit`.
 *
 * @param base - The framing's own latitude.
 * @param offset - The offset to clamp.
 * @param limit - The largest absolute latitude allowed.
 * @returns The clamped offset.
 */
export function clampLatitudeOffset(base: number, offset: number, limit: number): number {
  return Math.min(limit - base, Math.max(-limit - base, offset));
}

/**
 * Exponential decay of an inertia velocity over one frame, snapping to 0 once it is negligible.
 *
 * @param velocity - Current velocity (any unit per second).
 * @param damping - Decay rate (1/s).
 * @param dt - Frame time (s).
 * @param epsilon - Speed under which it stops.
 * @returns The new velocity.
 */
export function decayVelocity(
  velocity: number,
  damping: number,
  dt: number,
  epsilon: number,
): number {
  const next = velocity * Math.exp(-damping * dt);
  return Math.abs(next) < epsilon ? 0 : next;
}

/**
 * Smooths a drag velocity sample (an exponential moving average over `timeConstant` seconds).
 *
 * @param previous - The smoothed velocity so far.
 * @param sample - This move's velocity.
 * @param dt - Time since the previous move (s).
 * @param timeConstant - Smoothing time (s).
 * @returns The new smoothed velocity.
 */
export function smoothVelocity(
  previous: number,
  sample: number,
  dt: number,
  timeConstant: number,
): number {
  const weight = 1 - Math.exp(-Math.max(0, dt) / timeConstant);
  return previous + (sample - previous) * weight;
}

/**
 * How far the idle behaviour (the drift, the camera easing back) has resumed after a drag.
 *
 * @param idleS - Seconds since the drag and its inertia ended (Infinity before any drag).
 * @param resumeS - Seconds of stillness first.
 * @param rampS - Seconds over which it then fades in.
 * @returns 0 (paused) to 1 (fully resumed), smooth.
 */
export function idleFactor(idleS: number, resumeS: number, rampS: number): number {
  const t = Math.min(1, Math.max(0, (idleS - resumeS) / rampS));
  return t * t * (3 - 2 * t);
}

/**
 * Latitude and longitude of a direction, in three-globe's frame (+Y north, longitude 0 on +Z,
 * 90°E on +X); the inverse of `latLngToVector3`.
 *
 * @param x - X component.
 * @param y - Y component.
 * @param z - Z component.
 * @returns Latitude and longitude in degrees.
 */
export function vectorToLatLng(x: number, y: number, z: number): { lat: number; lng: number } {
  const length = Math.hypot(x, y, z) || 1;
  const toDegrees = 180 / Math.PI;
  return {
    lat: Math.asin(Math.max(-1, Math.min(1, y / length))) * toDegrees,
    lng: Math.atan2(x, z) * toDegrees,
  };
}
