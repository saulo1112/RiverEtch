// Where the hero's dive hands over to the case map: the camera distance at which a top-down view
// of the globe matches a Web Mercator zoom. Plain math with no three import, so the app shell can
// use it (the map's zoom for the way back) without pulling three into the entry chunk.
import { DIVE, GLOBE_RADIUS } from "./config.ts";

const degToRad = (degrees: number) => (degrees * Math.PI) / 180;

/** Earth radius (6371 km) over the globe radius: metres per scene unit. */
const METRES_PER_UNIT = 6_371_000 / GLOBE_RADIUS;
/** Web Mercator ground resolution at zoom 0 with 512 px tiles (MapLibre), metres per pixel. */
const METRES_PER_PIXEL_Z0 = 78_271.517;

/** Camera distance for the handoff, and the zoom it actually matches. */
export interface HandoffFrame {
  /** Camera distance from the globe center (scene units). */
  readonly distance: number;
  /** The Web Mercator zoom this distance matches at the site (may exceed the requested one). */
  readonly zoom: number;
}

/**
 * Solves the camera distance at which a nadir view of the globe shows the ground at the same scale,
 * at the screen center, as a Web Mercator map at `zoom` (pitch 0). The map's visible ground height
 * is `H · 78271.5 · cos(lat) / 2^zoom` metres; the camera's is about `2 · (d − R) · tan(fov / 2)`.
 * When the frame's corners would reach past the horizon (very wide screens), the camera goes lower
 * and the returned zoom is the larger one that distance matches.
 *
 * @param zoom - Requested handoff zoom.
 * @param latDeg - Site latitude in degrees.
 * @param viewportWidth - Viewport width in CSS pixels.
 * @param viewportHeight - Viewport height in CSS pixels.
 * @param fovDeg - Vertical field of view in degrees.
 * @returns The distance and the zoom it matches.
 */
export function handoffFrame(
  zoom: number,
  latDeg: number,
  viewportWidth: number,
  viewportHeight: number,
  fovDeg: number,
): HandoffFrame {
  const tanHalf = Math.tan(degToRad(fovDeg / 2));
  const metresPerPixelZ0 = METRES_PER_PIXEL_Z0 * Math.cos(degToRad(latDeg));
  const altitudeFor = (z: number) =>
    (viewportHeight * metresPerPixelZ0) / 2 ** z / METRES_PER_UNIT / (2 * tanHalf);

  let altitude = altitudeFor(zoom);
  const aspect = viewportWidth / Math.max(1, viewportHeight);
  const halfDiagonal = Math.atan(tanHalf * Math.hypot(1, aspect));
  const horizonLimit = Math.min(Math.PI / 2, halfDiagonal + degToRad(DIVE.horizonMarginDeg));
  const maxAltitude = GLOBE_RADIUS / Math.sin(horizonLimit) - GLOBE_RADIUS;
  if (altitude <= maxAltitude) {
    return { distance: GLOBE_RADIUS + altitude, zoom };
  }
  altitude = Math.max(DIVE.minAltitude, maxAltitude);
  const matched = Math.log2(
    (viewportHeight * metresPerPixelZ0) / (altitude * METRES_PER_UNIT * 2 * tanHalf),
  );
  return { distance: GLOBE_RADIUS + altitude, zoom: matched };
}
