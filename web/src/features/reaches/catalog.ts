// The demo's cases: the two gauged reaches the water-quality validation v5 chose by its
// preregistered rule, the ungauged reach of the transfer test, and the reach outside the tested
// region (docs/water-quality/report.md). Everything a case shows comes from the pipeline's
// committed files (docs/water-quality/reach/<id>/examples/, served under /data/reaches);
// this catalog only holds what the globe needs before those files load: where to dive and how the
// map frames the reach.
import type { LngLat } from "./types.ts";

/** One case of the demo workspace. */
export interface ReachCase {
  /** The reach's site id, as the pipeline names it (and its data folder). */
  readonly id: string;
  /** Card and case-file title. */
  readonly title: string;
  /** Where it is. */
  readonly place: string;
  /** The reach's centre (`[lng, lat]`): the dive's target and the satellite dish's site. */
  readonly center: LngLat;
  /** Web Mercator zoom (512 px tiles) at which the globe hands over to the map, looking down. */
  readonly handoffZoom: number;
  /** Final pitch of the map, in degrees. */
  readonly pitch: number;
  /** Final bearing of the map, in degrees clockwise from north: the reach reads across. */
  readonly bearing: number;
  /** The capture of the landed case view, under `public/cases/` (null until it exists). */
  readonly thumbnail: string | null;
  /** A station measures its turbidity (the cases screen groups the two kinds). */
  readonly gauged: boolean;
}

/** The cases, the featured one first. Centres are the middle of each corridor's bounds. */
export const REACH_CASES: readonly ReachCase[] = [
  {
    id: "mississippi-belle-chasse",
    title: "Mississippi · Belle Chasse",
    place: "Mississippi River, Chalmette to Belle Chasse, Louisiana (USA)",
    center: [-89.950106, 29.897519],
    handoffZoom: 5.2,
    pitch: 52,
    bearing: -20,
    thumbnail: null,
    gauged: true,
  },
  {
    id: "platte-louisville",
    title: "Platte · Louisville",
    place: "Platte River near Louisville, Nebraska (USA)",
    center: [-96.052607, 41.040321],
    handoffZoom: 5.2,
    pitch: 52,
    bearing: 10,
    thumbnail: null,
    gauged: true,
  },
  {
    id: "mississippi-st-joseph",
    title: "Mississippi · St. Joseph",
    place:
      "Mississippi River above Natchez, from St. Joseph, Louisiana (USA): no turbidity station",
    center: [-91.303384, 31.822055],
    handoffZoom: 5.2,
    pitch: 52,
    bearing: -45,
    thumbnail: null,
    gauged: false,
  },
  {
    id: "firat-birecik",
    title: "Fırat · Birecik",
    place:
      "Fırat (Euphrates) River below the Birecik Dam, Şanlıurfa (Türkiye): no turbidity station",
    center: [37.945756, 37.039699],
    handoffZoom: 5.2,
    pitch: 52,
    bearing: 0,
    thumbnail: null,
    gauged: false,
  },
];

/**
 * A case by id.
 *
 * @param id - The reach's site id.
 * @returns The case (the featured one for an unknown id).
 */
export function reachCase(id: string): ReachCase {
  const found = REACH_CASES.find((c) => c.id === id) ?? REACH_CASES[0];
  if (found === undefined) {
    throw new Error("the catalog has no case");
  }
  return found;
}
