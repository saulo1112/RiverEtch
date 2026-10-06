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

/** A `[latitude, longitude]` pair in decimal degrees. */
export type LatLng = readonly [number, number];

/** An illustrative river: approximate course and its share of the heat-map blobs. */
export interface IllustrativeRiver {
  /** River name. */
  readonly name: string;
  /** Share of the blobs placed along this river (all shares sum to 1). */
  readonly weight: number;
  /** Approximate course from source to mouth. */
  readonly points: readonly LatLng[];
}

/**
 * Approximate courses of Colombia's main rivers. ILLUSTRATIVE, NOT MEASURED: they only place the
 * decorative turbidity heat map until the Sentinel-2 pipeline provides real anomalies.
 */
export const RIVERS: readonly IllustrativeRiver[] = [
  {
    name: "Magdalena",
    weight: 0.3,
    points: [
      [1.9, -76.4],
      [2.9, -75.3],
      [4.2, -74.9],
      [5.5, -74.6],
      [7.0, -73.9],
      [8.6, -74.0],
      [9.3, -74.6],
      [10.2, -74.8],
      [11.0, -74.85],
    ],
  },
  {
    name: "Cauca",
    weight: 0.2,
    points: [
      [2.4, -76.6],
      [3.5, -76.4],
      [4.8, -75.9],
      [6.2, -75.7],
      [7.6, -75.3],
      [8.9, -74.5],
    ],
  },
  {
    name: "Atrato",
    weight: 0.12,
    points: [
      [5.5, -76.6],
      [6.5, -76.9],
      [7.5, -77.1],
      [8.1, -77.0],
    ],
  },
  {
    name: "Meta",
    weight: 0.12,
    points: [
      [4.1, -73.3],
      [4.6, -71.8],
      [5.0, -70.5],
      [6.2, -67.5],
    ],
  },
  {
    name: "Caquetá",
    weight: 0.1,
    points: [
      [1.0, -75.6],
      [0.2, -73.5],
      [-1.0, -71.5],
      [-1.4, -69.5],
    ],
  },
  {
    name: "Guaviare",
    weight: 0.08,
    points: [
      [2.6, -72.8],
      [3.0, -70.5],
      [4.0, -67.8],
    ],
  },
  {
    name: "Putumayo",
    weight: 0.08,
    points: [
      [0.5, -76.8],
      [-0.6, -74.5],
      [-2.0, -72.5],
      [-2.9, -70.0],
    ],
  },
];

/** An illustrative hotspot: a round blob of extra heat. */
export interface IllustrativeHotspot {
  /** Place name. */
  readonly name: string;
  /** Center, `[latitude, longitude]`. */
  readonly at: LatLng;
  /** Peak amplitude (0..1). */
  readonly weight: number;
  /** Radius in degrees. */
  readonly radiusDeg: number;
}

/** River towns used as extra heat blobs. ILLUSTRATIVE, NOT MEASURED (see {@link RIVERS}). */
export const HOTSPOTS: readonly IllustrativeHotspot[] = [
  { name: "Bajo Cauca / Caucasia", at: [7.98, -75.2], weight: 1.0, radiusDeg: 1.0 },
  { name: "Quibdó / Atrato", at: [5.69, -76.66], weight: 0.9, radiusDeg: 0.8 },
  { name: "Mompox", at: [9.2, -74.4], weight: 0.8, radiusDeg: 1.1 },
  { name: "Barranquilla mouth", at: [11.0, -74.8], weight: 0.75, radiusDeg: 0.7 },
  { name: "Barrancabermeja", at: [7.07, -73.85], weight: 0.7, radiusDeg: 0.7 },
  { name: "San José del Guaviare", at: [2.57, -72.64], weight: 0.55, radiusDeg: 0.8 },
  { name: "Caquetá", at: [-0.6, -72.4], weight: 0.5, radiusDeg: 0.9 },
  { name: "Putumayo", at: [-0.3, -75.0], weight: 0.45, radiusDeg: 0.8 },
  { name: "Puerto Carreño", at: [6.19, -67.48], weight: 0.4, radiusDeg: 0.7 },
];
