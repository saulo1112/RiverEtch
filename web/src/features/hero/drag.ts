// Pure helpers of the hero globe's mouse drag and "Follow satellite" (no three, no DOM), so they
// can be unit-tested. Angles in degrees unless a name says otherwise.

/**
 * Wraps an angle to (−180, 180].
 *
 * @param degrees - Any angle.
 * @returns The same direction, in (−180, 180].
 */
export function wrapDegrees(degrees: number): number {
  const wrapped = degrees - 360 * Math.floor((degrees + 180) / 360);
  return wrapped === -180 ? 180 : wrapped;
}

/**
 * The signed shortest turn from one angle to another.
 *
 * @param from - Start angle.
 * @param to - End angle.
 * @returns The turn, in (−180, 180].
 */
export function shortestDelta(from: number, to: number): number {
  return wrapDegrees(to - from);
}

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

/** The framing the follow camera copies (CAMERA in config.ts and ORBIT.passLatLng). */
export interface FollowFraming {
  /** The camera's latitude at rest (before the width weight). */
  readonly viewLatDeg: number;
  /** The camera's longitude offset from the pass point (before the width weight). */
  readonly viewLngOffsetDeg: number;
  /** Latitude of the orbit's pass point. */
  readonly passLatDeg: number;
}

/**
 * Where the follow camera sits for a given sub-satellite point: offset from it as the resting
 * camera is offset from the pass point, so the satellite holds its usual place on screen.
 *
 * @param subLat - Latitude under the satellite.
 * @param subLng - Longitude under the satellite.
 * @param widthWeight - The framing's width weight (narrow screens look more frontally).
 * @param framing - The resting framing.
 * @returns The camera's latitude and longitude (wrapped).
 */
export function followCamera(
  subLat: number,
  subLng: number,
  widthWeight: number,
  framing: FollowFraming,
): { lat: number; lng: number } {
  return {
    lat: subLat + framing.viewLatDeg * widthWeight - framing.passLatDeg,
    lng: wrapDegrees(subLng + framing.viewLngOffsetDeg * widthWeight),
  };
}
