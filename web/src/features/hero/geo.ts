// Geographic helpers of the hero scene (three-globe's frame: +Y north, longitude 0 on +Z, 90°E on +X).
import { Vector3 } from "three";

import { GLOBE_RADIUS, ORBIT } from "./config.ts";

/**
 * Converts geographic coordinates to scene coordinates, using three-globe's convention
 * (+Y north, longitude 0 on +Z, 90°E on +X).
 *
 * @param latDeg - Latitude in degrees.
 * @param lngDeg - Longitude in degrees.
 * @param radius - Distance from the globe center in scene units.
 * @param target - Vector that receives the result (avoids allocations in the frame loop).
 * @returns The `target` vector.
 */
export function latLngToVector3(
  latDeg: number,
  lngDeg: number,
  radius: number,
  target: Vector3,
): Vector3 {
  const phi = ((90 - latDeg) * Math.PI) / 180;
  const theta = ((90 - lngDeg) * Math.PI) / 180;

  return target.set(
    radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

/**
 * Unit vector towards the orbit's pass point ({@link ORBIT.passLatLng}). A framing anchor, not a
 * highlighted place.
 */
export const FRAMING_AIM: Readonly<Vector3> = latLngToVector3(
  ORBIT.passLatLng.lat,
  ORBIT.passLatLng.lng,
  1,
  new Vector3(),
);

/** The pass point on the globe surface (scene units): the dish's default ground target. */
export const PASS_SURFACE_POINT: Readonly<Vector3> =
  FRAMING_AIM.clone().multiplyScalar(GLOBE_RADIUS);
