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
  /** Atmosphere shell segments (width, height). */
  readonly shellSegments: readonly [number, number];
  /** Number of procedural stars. */
  readonly stars: number;
  /** Foil texture size and crease count. */
  readonly foil: { readonly size: number; readonly creases: number };
  /** Solar-cell texture size (width, height). */
  readonly cells: readonly [number, number];
  /** Radiator texture size. */
  readonly osr: number;
  /** Thin-film iridescence on the solar cells and lenses. */
  readonly iridescence: boolean;
  /** Samples of the orbit ring and trail ribbon. */
  readonly ribbonSamples: number;
}

/** Quality presets: `high` for desktops, `low` for weak GPUs and `?quality=low`. */
export const QUALITY_PRESETS: Readonly<Record<QualityName, QualityPreset>> = {
  high: {
    dprCap: 2,
    earthTexture: "earth-day-2k.jpg",
    globeCurvature: 2,
    shellSegments: [128, 64],
    stars: 4000,
    foil: { size: 512, creases: 70 },
    cells: [768, 960],
    osr: 512,
    iridescence: true,
    ribbonSamples: 720,
  },
  low: {
    dprCap: 1,
    earthTexture: "earth-day-2k.jpg",
    globeCurvature: 4,
    shellSegments: [64, 32],
    stars: 1800,
    foil: { size: 256, creases: 40 },
    cells: [384, 480],
    osr: 256,
    iridescence: false,
    ribbonSamples: 360,
  },
};

/** Optional night-lights map; used only if the file exists in `public/textures/`. */
export const EARTH_NIGHT_TEXTURE = "earth-night.jpg";

/** Ocean mask (white = water) for the sun glint, in `public/textures/`. */
export const EARTH_WATER_TEXTURE = "earth-water-2k.png";

/** Default preset when the URL does not override it. */
export const DEFAULT_QUALITY: QualityName = "high";

/** Globe radius used by globe.gl / three-globe (scene units). */
export const GLOBE_RADIUS = 100;

/** Geographic anchors (decimal degrees). */
export const GEO = {
  // Area-weighted centroid of mainland Colombia (Natural Earth 1:50m).
  colombiaCentroid: { lat: 3.914, lng: -73.081 },
} as const;

/**
 * Sun, fixed in world space: upper left of the frame with the terminator at the lower right.
 * `dir` points from the Earth towards the sun.
 */
export const SUN = {
  dir: [-0.8525, 0.2394, -0.4647],
  color: "#fff4e5",
} as const;

/** Earth surface shading. */
export const EARTH = {
  // Sun intensity on the day side (linear multiplier of the albedo).
  sunGain: 2.4,
  saturation: 1.08,
  // N·L range of the soft day/night transition.
  terminator: [-0.06, 0.28],
  // Strength of the sunset tint near the terminator.
  twilightTint: 0.2,
  twilightColor: "#ff9a5a",
  // GGX roughness of the ocean sun glint, its gain and its cap (linear).
  glintRoughness: 0.22,
  glintGain: 0.25,
  glintMax: 1.1,
  // Night side: residual albedo light, a faint navy floor and the optional night-lights gain.
  nightAmbient: [0.006, 0.009, 0.016],
  nightTint: [0.0012, 0.0024, 0.0065],
  nightLightsGain: 0.9,
  // Darkens the globe away from Colombia (1 = off).
  focusVignette: 0.92,
  // Luminance shoulder that keeps the surface below the bloom threshold.
  shoulderKnee: 0.6,
  shoulderMax: 0.85,
} as const;

/** Atmosphere shell around the Earth (Rayleigh-like rim, brighter on the day side). */
export const ATMOSPHERE = {
  radius: 122,
  rayleighColor: "#6fa8ff",
  intensity: 0.85,
  // Density profile: two exponential scale heights (scene units) and the fade-out band.
  scaleHeights: [1.5, 7],
  fade: [18, 22],
  forwardScatter: 0.25,
  twilight: 0.35,
} as const;

/** Procedural starfield (THREE.Points). */
export const STARFIELD = {
  seed: 1977,
  radius: [1800, 2600],
  // Share of stars placed along a Milky Way band, its tilt from +Y and its angular spread.
  bandShare: 0.25,
  bandTiltDeg: 62,
  bandSigmaDeg: 9,
  // Brightness = min + range * r^exponent, which keeps most stars faint; size in CSS px.
  brightness: [0.1, 0.65],
  brightnessExponent: 5,
  size: [1.2, 2.0],
  // Share of faint stars that twinkle, twinkle depth range and frequency range (Hz).
  twinkleShare: 0.35,
  twinkleDepth: [0.15, 0.45],
  twinkleHz: [0.15, 1.1],
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
  // Intro dolly-in: duration, extra distance, extra longitude and latitude it starts from.
  intro: { durationS: 3.6, distanceGain: 0.55, lngDeg: 20, latDeg: 6, exposureS: 1.4 },
  // Mouse parallax (degrees at the hero edge) and its damping rate (1/s).
  parallax: { lngDeg: 1.6, latDeg: 1.0, damping: 3.2, cssShiftPx: [8, 5] },
  // Slow Lissajous drift: amplitudes (degrees) and periods (seconds).
  drift: { latDeg: 0.3, latPeriodS: 23, lngDeg: 0.45, lngPeriodS: 31 },
} as const;

/**
 * Orbit: near-polar (98°), descending over Colombia on every pass because the Earth is static.
 * The altitude is exaggerated (0.34 R) so the satellite, beam and footprint read at hero scale.
 */
export const ORBIT = {
  inclinationDeg: 98,
  radius: 134,
  periodS: 50,
  // Scene time of the first pass over Colombia.
  peakTimeS: 9,
  // Time warp θ = 2πp − a·sin 2πp + b·sin 4πp: slow over Colombia, fast on the far side.
  warp: [0.6, 0.075],
  // Small yaw steering, as real Earth-observation satellites do.
  yawSteerDeg: 3.9,
} as const;

/** Satellite model, materials and lights. */
export const SATELLITE = {
  variant: "A" satisfies SatelliteVariant,
  // Wingtip-to-wingtip span in model units, and its target size on screen at the scan peak
  // (before foreshortening: the wings are seen at an angle, so ~100 px end to end).
  spanUnits: 24,
  targetSpanPx: 115,
  scaleRange: [0.7, 1.35],
  // Solar-array drive: critically damped spring (rad/s) with a rate limit.
  sada: { omega: 4, maxDegPerS: 12 },
  colors: {
    gold: "#e8b65a",
    silver: "#d6dae0",
    osr: "#d7dee6",
    panelBack: "#1e2125",
    frame: "#c4c8cc",
    titanium: "#8a8d91",
    anodize: "#0d0e10",
    paint: "#eceae3",
    lens: "#05060a",
    aperture: "#020203",
  },
  lights: {
    key: 3.2,
    keyColor: "#fff3e2",
    rim: 1.6,
    rimColor: "#5b8cff",
    earthshine: 0.9,
    earthshineColor: "#86aeff",
    ambient: 0.12,
    ambientColor: "#1b2340",
  },
  // PMREM blur of the procedural room environment.
  environmentBlur: 0.04,
  // Luminance shoulder that keeps the body below the bloom threshold.
  shoulderKnee: 0.62,
  shoulderMax: 0.88,
} as const;

/** Orbit ring and the fading trail behind the satellite (one ribbon mesh). */
export const TRAIL = {
  ringColor: "#7fa6ff",
  // Ring brightness: base plus a boost on the arc facing the camera.
  ringGain: [0.1, 0.12],
  trailColor: "#cfe4ff",
  trailGain: 0.8,
  // Trail decay constant, gap behind the satellite and maximum length (radians of orbit).
  decay: 0.279,
  gap: 0.026,
  length: 1.22,
  // Line width in CSS px for the ring and the trail head.
  widthPx: [1, 2],
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
