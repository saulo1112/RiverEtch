// Geometry of the hero's dive to a site (and of the rise back): the camera pose part-way through.
// The handoff distance itself lives in handoff.ts, which has no three dependency.
import { MathUtils, Vector3 } from "three";

import { DIVE, GLOBE_RADIUS } from "./config.ts";

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
