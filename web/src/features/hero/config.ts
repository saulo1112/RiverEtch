// Every tunable of the hero scene lives here. Units: globe radius R = 100 scene units, angles in
// degrees unless a name says otherwise, times in seconds. Colors are sRGB hex strings.

/** Rendering quality preset name; `?quality=low|high` overrides the default. */
export type QualityName = "low" | "high";

/** Satellite silhouette; only variant A (gold bus, two wings, dish) exists for now. */
export type SatelliteVariant = "A";

/** Per-preset rendering budgets. */
export interface QualityPreset {
  /** Upper bound for the device pixel ratio. */
  readonly dprCap: number;
  /** Earth color map in `public/textures/`. */
  readonly earthTexture: string;
  /** globe.gl sphere tessellation, in degrees per segment (lower is finer). */
  readonly globeCurvature: number;
}

/** Quality presets: `high` for desktops, `low` for weak GPUs and `?quality=low`. */
export const QUALITY_PRESETS: Readonly<Record<QualityName, QualityPreset>> = {
  high: { dprCap: 2, earthTexture: "earth-day-2k.jpg", globeCurvature: 2 },
  low: { dprCap: 1, earthTexture: "earth-day-2k.jpg", globeCurvature: 4 },
};

/** Default preset when the URL does not override it. */
export const DEFAULT_QUALITY: QualityName = "high";

/** Globe radius used by globe.gl / three-globe (scene units). */
export const GLOBE_RADIUS = 100;

/** Geographic anchors (decimal degrees). */
export const GEO = {
  // Area-weighted centroid of mainland Colombia (Natural Earth 1:50m).
  colombiaCentroid: { lat: 3.914, lng: -73.081 },
} as const;

/** Camera framing and motion. */
export const CAMERA = {
  fovDeg: 50,
  near: 1,
  far: 4000,
  // Viewpoint south-east of Colombia, so the orbit and the beam do not collapse onto one point.
  viewLatDeg: -8,
  viewLngOffsetDeg: 18,
  // Look-at point: this fraction of the radius along the Colombia direction.
  targetFactor: 0.85,
  // Globe disc diameter as a fraction of the viewport height (also bounded by the width).
  discFraction: 0.72,
  // Where the globe center lands on screen, as fractions of the viewport (0,0 = top-left).
  // Desktop leaves the left side free for future content; portrait screens center it.
  globeCenterDesktop: { x: 0.62, y: 0.52 },
  globeCenterPortrait: { x: 0.5, y: 0.5 },
} as const;

/** Visual tokens shared by the CSS layers and the WebGL scene. */
export const PALETTE = {
  space: "#02040a",
} as const;

/** Satellite options (built from milestone 3 on). */
export const SATELLITE = {
  variant: "A" satisfies SatelliteVariant,
} as const;

/** URL options read once when the hero mounts. */
export interface HeroUrlOptions {
  /** Quality preset forced by `?quality=`, or the default. */
  readonly quality: QualityName;
  /** True for `?lab=satellite`. */
  readonly lab: boolean;
  /** Frozen scene time from `?t=<seconds>` (development builds only), otherwise null. */
  readonly frozenTime: number | null;
}

/**
 * Parses the hero's URL options.
 *
 * @param search - A `location.search` string such as `"?quality=low"`.
 * @returns The quality preset, lab flag and optional frozen time.
 */
export function parseHeroUrlOptions(search: string): HeroUrlOptions {
  const params = new URLSearchParams(search);
  const qualityParam = params.get("quality");
  const quality: QualityName =
    qualityParam === "low" || qualityParam === "high" ? qualityParam : DEFAULT_QUALITY;
  const timeParam = params.get("t");
  const time = timeParam === null ? Number.NaN : Number(timeParam);

  return {
    quality,
    lab: params.get("lab") === "satellite",
    frozenTime: import.meta.env.DEV && Number.isFinite(time) ? time : null,
  };
}
