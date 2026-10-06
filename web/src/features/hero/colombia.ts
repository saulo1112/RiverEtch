// Colombia outline: Natural Earth 1:50m admin-0 (public domain) via the world-atlas npm package.
import { Vector3 } from "three";

import { GEO, GLOBE_RADIUS } from "./config.ts";
import colombiaGeoJson from "./data/colombia.geo.json";

/** A `[longitude, latitude]` pair in decimal degrees. */
export type LngLat = readonly [number, number];

/** Outer rings of Colombia's polygons (mainland and Gorgona island), as lng/lat pairs. */
export const COLOMBIA_RINGS: readonly (readonly LngLat[])[] = colombiaGeoJson.features.flatMap(
  (feature) =>
    feature.geometry.coordinates.map((polygon) =>
      (polygon[0] ?? []).map(([lng = 0, lat = 0]): LngLat => [lng, lat]),
    ),
);

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

/** Unit vector from the globe center towards Colombia's centroid. */
export const COLOMBIA_DIRECTION: Readonly<Vector3> = latLngToVector3(
  GEO.colombiaCentroid.lat,
  GEO.colombiaCentroid.lng,
  1,
  new Vector3(),
);

/** Colombia's centroid on the globe surface, in scene units. */
export const COLOMBIA_SURFACE_POINT: Readonly<Vector3> =
  COLOMBIA_DIRECTION.clone().multiplyScalar(GLOBE_RADIUS);
