import { REFERENCE_REACH_CENTER } from "./reachGeometry.ts";
import type { SiteConfig } from "./types.ts";

/**
 * The study site of the flythrough: the reference reach of the Río Magdalena between Puerto Wilches
 * and San Pablo. Its location and centreline are real (reachGeometry.ts); the event the case view
 * shows on it is synthetic. The dive, the map and the panels all read from here.
 */
export const CASE_SITE: SiteConfig = {
  id: "magdalena-puerto-wilches",
  name: "Magdalena · reference reach",
  center: REFERENCE_REACH_CENTER,
  // Kept near 5: closer in, the globe's 4k Earth texture turns soft before the crossfade.
  handoffZoom: 5.2,
  // The reach is about 15.7 km long: this zoom frames it at the size the panels leave free.
  finalZoom: 11.2,
  pitch: 55,
  bearing: -20,
};
