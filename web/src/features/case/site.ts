import type { SiteConfig } from "./types.ts";

/**
 * The study site of the flythrough. A PLACEHOLDER: the Atrato near Quibdó (Chocó) was picked for
 * illustration only and nothing about it was measured. Swap it for a site the pipeline reports;
 * the dive, the map and the panels all read from here.
 */
export const CASE_SITE: SiteConfig = {
  id: "atrato-quibdo-placeholder",
  name: "Atrato River near Quibdó",
  center: [-76.655, 5.69],
  // Kept near 5: closer in, the globe's 4k Earth texture turns soft before the crossfade.
  handoffZoom: 5.2,
  finalZoom: 12,
  pitch: 55,
  bearing: -20,
};
