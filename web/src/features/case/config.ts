// Tunables of the case map: tile sources, grading, terrain and the river line. Colors are sRGB.

const IMAGERY_LAYER = "s2cloudless-2024_3857";

/**
 * Sentinel-2 cloudless 2024 by EOX, as Web Mercator raster tiles (WMTS REST, tile matrix set `g`).
 *
 * Licence: CC BY-NC-SA 4.0 (attribution, NON-COMMERCIAL, share-alike). Fine for this research demo;
 * any commercial use needs a licence from EOX. The attribution below must stay visible.
 *
 * TODO: confirm the layer id, the tile matrix set and the URL template against
 * https://tiles.maps.eox.at/wmts/1.0.0/WMTSCapabilities.xml (the tile servers were not reachable
 * from the environment this was built in).
 */
export const IMAGERY = {
  layer: IMAGERY_LAYER,
  tiles: `https://tiles.maps.eox.at/wmts/1.0.0/${IMAGERY_LAYER}/default/g/{z}/{y}/{x}.jpg`,
  tileSize: 256,
  maxzoom: 13,
  attribution:
    "Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2024)",
  homepage: "https://s2maps.eu",
} as const;

/**
 * Elevation: Mapzen Terrain Tiles on the AWS Open Data registry, Terrarium-encoded PNG. Used twice
 * (3D terrain and a subtle hillshade) through two sources, as MapLibre recommends.
 *
 * TODO: confirm the URL template and the attribution against
 * https://registry.opendata.aws/terrain-tiles/ and
 * https://github.com/tilezen/joerd/blob/master/docs/attribution.md (not reachable from the
 * environment this was built in).
 */
export const TERRAIN = {
  tiles: "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
  encoding: "terrarium",
  tileSize: 256,
  maxzoom: 12,
  exaggeration: 1.4,
  attribution:
    "Terrain: Mapzen Terrain Tiles on AWS (SRTM and GMTED2010 courtesy of the U.S. Geological Survey, ETOPO1 by NOAA)",
} as const;

/** Map look: background, grading of the imagery, hillshade, sky and the river line. */
export const MAP_LOOK = {
  background: "#02040a",
  maxZoom: 13.5,
  // The flythrough waits this long for the first `idle` before it hands over anyway.
  readyTimeoutMs: 2500,
  // Dark, slightly desaturated grading so the glass panels and the river stay legible.
  imagery: { saturation: -0.1, contrast: 0.15, brightnessMax: 0.8, fadeDurationMs: 120 },
  // Subtle: translucent colors over the imagery.
  hillshade: {
    exaggeration: 0.22,
    shadow: "rgba(2, 4, 10, 0.55)",
    highlight: "rgba(169, 193, 230, 0.14)",
    accent: "rgba(11, 22, 48, 0.4)",
  },
  // Only visible if a tall viewport shows the horizon: keep it night-dark.
  sky: { sky: "#02040a", horizon: "#0b1a3d", fog: "#02040a" },
  river: {
    // Core and glow widths (px) by zoom, the glow's blur and opacity.
    coreWidth: [5, 1.2, 9, 2.2, 12, 3.5, 14, 4.5],
    glowWidth: [5, 5, 9, 9, 12, 16, 14, 22],
    glowBlur: [5, 3, 12, 9, 14, 12],
    glowOpacity: 0.55,
    // Length of the soft leading edge of the reveal, as a share of the reach.
    revealFeather: 0.04,
    revealMs: 1400,
  },
} as const;

/**
 * Flythrough timeline (hero to case map), in milliseconds unless noted. The hero's dive itself is
 * `DIVE` in features/hero/config.ts (3.2 s); the hero UI fade (350 ms) lives in hero.css.
 */
export const FLIGHT = {
  // Crossfade from the globe to the map once the dive reached the handoff and the map is ready.
  crossfadeMs: 700,
  // Without a dive (no WebGL scene yet) and with reduced motion: a quick crossfade instead.
  quickCrossfadeMs: 300,
  reducedCrossfadeMs: 200,
  // The map's tilt and zoom onto the reach: a soft start (the dive ends at rest), then a long
  // ease-out.
  flyMs: 3600,
  flyEase: [0.3, 0, 0.12, 1],
  // Shares of the map flight at which the river draws itself and the panels slide in.
  riverAt: 0.5,
  panelsAt: 0.7,
  // Panel slide: duration and stagger (case.css mirrors both).
  panelMs: 320,
  panelStaggerMs: 70,
  // The Skip button appears this long after the flight starts.
  skipDelayMs: 400,
} as const;
