// Geometry of the hero's dive to a site: the camera distance that matches a Web Mercator zoom when
// looking straight down, and the camera pose part-way through the dive.
import { MathUtils, Vector3 } from "three";

import { DIVE, GLOBE_RADIUS } from "./config.ts";

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
  const tanHalf = Math.tan(MathUtils.degToRad(fovDeg / 2));
  const metresPerPixelZ0 = METRES_PER_PIXEL_Z0 * Math.cos(MathUtils.degToRad(latDeg));
  const altitudeFor = (z: number) =>
    (viewportHeight * metresPerPixelZ0) / 2 ** z / METRES_PER_UNIT / (2 * tanHalf);

  let altitude = altitudeFor(zoom);
  const aspect = viewportWidth / Math.max(1, viewportHeight);
  const halfDiagonal = Math.atan(tanHalf * Math.hypot(1, aspect));
  const horizonLimit = Math.min(
    Math.PI / 2,
    halfDiagonal + MathUtils.degToRad(DIVE.horizonMarginDeg),
  );
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

const fromDirection = new Vector3();
const axis = new Vector3();
const siteSurface = new Vector3();

/**
 * Camera position and look-at point part-way through the dive. The direction from the globe center
 * swings along a great circle to the site, the altitude interpolates in log space (a steady zoom
 * rate), and the look-at point slides to the site, so at `k = 1` the camera looks straight down;
 * with world up kept at +Y, that view is north-up.
 *
 * @param k - Eased progress, 0..1.
 * @param fromPosition - Camera position when the dive started.
 * @param fromTarget - Look-at point when the dive started.
 * @param siteDirection - Unit vector from the globe center to the site.
 * @param distance - Camera distance at the handoff.
 * @param position - Receives the camera position.
 * @param target - Receives the look-at point.
 */
export function divePose(
  k: number,
  fromPosition: Vector3,
  fromTarget: Vector3,
  siteDirection: Vector3,
  distance: number,
  position: Vector3,
  target: Vector3,
): void {
  fromDirection.copy(fromPosition).normalize();
  const angle = fromDirection.angleTo(siteDirection);
  axis.crossVectors(fromDirection, siteDirection);
  if (axis.lengthSq() < 1e-12) {
    position.copy(siteDirection);
  } else {
    position.copy(fromDirection).applyAxisAngle(axis.normalize(), angle * k);
  }
  const startAltitude = Math.max(DIVE.minAltitude, fromPosition.length() - GLOBE_RADIUS);
  const endAltitude = Math.max(DIVE.minAltitude, distance - GLOBE_RADIUS);
  const altitude = Math.exp(MathUtils.lerp(Math.log(startAltitude), Math.log(endAltitude), k));
  position.multiplyScalar(GLOBE_RADIUS + altitude);

  siteSurface.copy(siteDirection).multiplyScalar(GLOBE_RADIUS);
  target.lerpVectors(fromTarget, siteSurface, k);
}
