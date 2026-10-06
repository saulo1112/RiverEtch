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
  /** Earth color map in `public/textures/`, used for the first frames. */
  readonly earthTexture: string;
  /** Sharper Earth map swapped in once the scene runs, or null to keep the first one. */
  readonly earthTextureDetail: string | null;
  /** Bloom through the post-processing composer; without it, glows use additive sprites. */
  readonly bloom: boolean;
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
  /** Scan effect resolution. */
  readonly scan: {
    /** Colombia data texture size (longitude, latitude). */
    readonly data: readonly [number, number];
    /** Colombia patch grid segments (longitude, latitude). */
    readonly patchSegments: readonly [number, number];
    /** Footprint grid segments (cross-track, along-track). */
    readonly footprintSegments: readonly [number, number];
    /** Ring plane segments per side. */
    readonly ringSegments: number;
    /** Radial segments of the beam cone. */
    readonly coneRadial: number;
  };
}

/** Quality presets: `high` for desktops, `low` for weak GPUs and `?quality=low`. */
export const QUALITY_PRESETS: Readonly<Record<QualityName, QualityPreset>> = {
  high: {
    dprCap: 2,
    earthTexture: "earth-day-2k.jpg",
    earthTextureDetail: "earth-day-4k.jpg",
    bloom: true,
    globeCurvature: 2,
    shellSegments: [128, 64],
    stars: 4000,
    foil: { size: 512, creases: 70 },
    cells: [768, 960],
    osr: 512,
    iridescence: true,
    ribbonSamples: 720,
    scan: {
      data: [768, 1024],
      patchSegments: [64, 80],
      footprintSegments: [48, 64],
      ringSegments: 96,
      coneRadial: 48,
    },
  },
  low: {
    dprCap: 1,
    earthTexture: "earth-day-2k.jpg",
    earthTextureDetail: null,
    bloom: false,
    globeCurvature: 4,
    shellSegments: [64, 32],
    stars: 1800,
    foil: { size: 256, creases: 40 },
    cells: [384, 480],
    osr: 256,
    iridescence: false,
    ribbonSamples: 360,
    scan: {
      data: [384, 512],
      patchSegments: [32, 40],
      footprintSegments: [24, 32],
      ringSegments: 48,
      coneRadial: 32,
    },
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
  // Lat/lng box of the scan patch (mainland and Gorgona; San Andrés lies outside and is omitted).
  patch: { lngMin: -80.5, lngMax: -65.5, latMin: -5.5, latMax: 13.5 },
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
  // GGX roughness of the ocean sun glint, its gain and its soft cap (linear). The cap stays below
  // the bloom threshold (POST.bloom.threshold), so the glint reads as sunlight on water, not a flare.
  glintRoughness: 0.22,
  glintGain: 0.17,
  glintMax: 0.8,
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
  globeCenterDesktop: { x: 0.6, y: 0.56 },
  globeCenterPortrait: { x: 0.5, y: 0.5 },
  // Intro dolly-in: duration, extra distance, extra longitude and latitude it starts from.
  intro: { durationS: 3.6, distanceGain: 0.55, lngDeg: 20, latDeg: 6, exposureS: 1.4 },
  // Mouse parallax (degrees at the hero edge) and its damping rate (1/s).
  parallax: { lngDeg: 1.6, latDeg: 1.0, damping: 3.2, cssShiftPx: [8, 5] },
  // Slow Lissajous drift: amplitudes (degrees) and periods (seconds).
  drift: { latDeg: 0.3, latPeriodS: 23, lngDeg: 0.45, lngPeriodS: 31 },
} as const;

/**
 * Orbit: prograde and low-inclination, ascending over Colombia on every pass because the Earth is
 * static, so the satellite crosses the frame left to right, climbing slightly. The altitude is
 * exaggerated (0.34 R) so the satellite, beam and footprint read at hero scale.
 */
export const ORBIT = {
  // The single orbit knob. A real Earth-observation orbit would be sun-synchronous (~98°, like
  // Sentinel-2), but it crosses the frame top to bottom; it was dropped purely for composition.
  // Keep it well above 0: from this camera a near-equatorial orbit collapses into a flat line.
  inclinationDeg: 30,
  radius: 134,
  periodS: 50,
  // Scene time of the first pass over Colombia.
  peakTimeS: 9,
  // Time warp θ = 2πp − a·sin 2πp + b·sin 4πp: slow over Colombia, fast on the far side.
  warp: [0.6, 0.075],
  // Small yaw steering, as real Earth-observation satellites do: its amplitude on a polar orbit,
  // scaled by sin(inclination).
  yawSteerDeg: 3.9,
} as const;

/** Satellite model, materials and lights. */
export const SATELLITE = {
  variant: "A" satisfies SatelliteVariant,
  // Wingtip-to-wingtip span in model units, and its target size on screen at the scan peak
  // (before foreshortening: the wings are seen at an angle, so ~225 px end to end at 1080p). The
  // target is capped to a share of the viewport width (portrait screens), then the model scale is
  // clamped to scaleRange.
  spanUnits: 24,
  targetSpanPx: 260,
  maxSpanViewportFraction: 0.4,
  scaleRange: [1.0, 3.2],
  // Thermal blankets: model units per foil texture tile (larger shows the creases at hero scale)
  // and the strength of their relief.
  foilTileUnits: 6.5,
  foilNormalScale: 1.05,
  // Solar cells per panel (columns along the span, rows along the chord), the width of the
  // substrate gaps between them (share of the texture's shorter side), its color and the cells'
  // HSL lightness range (percent).
  cells: { columns: 4, rows: 6, gapFraction: 0.022, gapColor: "#8d96a6", lightness: [12, 15] },
  // Solar-array drive: critically damped spring (rad/s) with a rate limit.
  sada: { omega: 4, maxDegPerS: 12 },
  // Panel glint, solved once per orbit: where on the orbit it happens (relative to Colombia), the
  // largest cant and array offset used to aim it, and the feather window. The arrays sweep through
  // the glint attitude by ±sweepDeg over that window, so the gleam is brief. The reflection lobe
  // is sigmaDeg wide; a twist of twistDeg from root to tip and each cell's tilt (cellTilt times the
  // normal map) make it travel along the wing as a band. `peak` is its linear brightness, kept
  // below the bloom threshold so the cells never clip to white; haloScale sizes the low preset's
  // sprite.
  glint: {
    orbitOffsetDeg: 55,
    cantMaxDeg: 22,
    offsetMaxDeg: 35,
    windowDeg: 20,
    sweepDeg: 24,
    sigmaDeg: 1.2,
    twistDeg: 8,
    cellTilt: 1,
    peak: 0.8,
    haloScale: 2,
  },
  // Dish tracks Colombia while it is above the horizon, otherwise it stows.
  dish: { omega: 1.6, maxDegPerS: 12, maxElevationDeg: 75 },
  // Nav lights: periods (s), pulse width (ms), HDR peak colors (linear) and resting level.
  navLights: {
    redPeriodS: 1.9,
    greenPeriodS: 2.3,
    strobePeriodS: 1.6,
    pulseMs: 70,
    red: [4, 0.25, 0.18],
    green: [0.25, 4, 1.1],
    strobe: 9,
    resting: 0.03,
    // Steady level for the reduced-motion still.
    still: 0.6,
  },
  colors: {
    gold: "#d99b3a",
    silver: "#d6dae0",
    osr: "#aab2bc",
    panelBack: "#1e2125",
    frame: "#c4c8cc",
    titanium: "#8a8d91",
    anodize: "#0d0e10",
    paint: "#eceae3",
    lens: "#05060a",
    aperture: "#020203",
  },
  lights: {
    key: 2.0,
    keyColor: "#fff3e2",
    rim: 2.6,
    rimColor: "#5b8cff",
    earthshine: 0.9,
    earthshineColor: "#86aeff",
    // Share of the earthshine kept over the night side, so the satellite still reads there.
    earthshineMin: 0.3,
    ambient: 0.16,
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
  trailGain: 0.5,
  // Trail decay constant, gap behind the satellite and maximum length (radians of orbit).
  decay: 0.279,
  gap: 0.055,
  length: 1.22,
  // Line width in CSS px for the ring and the trail head.
  widthPx: [1, 2],
} as const;

/** Scan effect: state machine, beam, footprint, Colombia patch, border stroke and rings. */
export const SCAN = {
  // Intensity I = 1 − smoothstep(ψ, in, out), ψ = angle between the nadir and Colombia's centroid.
  intensityDeg: [7, 30],
  // State machine thresholds on I (idle → approach → scan → leave → idle), and the lock ring.
  thresholds: { approach: 0.03, scan: 0.65, leave: 0.55, lock: 0.4 },
  // Damping rates (1/s) of the smoothed drivers.
  damping: { beam: 8, strokeRise: 3, strokeFall: 1.2, cap: 3, push: 1.5 },
  colors: { beam: "#8fe6ff", instrument: "#22d3ee", rings: "#5fe3ff" },
  beam: {
    // Footprint semi-axes on the ground (scene units) and how far the base sinks below it.
    crossTrack: 9.5,
    alongTrack: 4.2,
    sink: 1.2,
    // Body brightness, aperture hot spot, stripe length (units) and speed (1/s).
    bodyGain: 0.6,
    hot: 1.2,
    stripeLength: 2.6,
    stripeSpeed: 1.4,
  },
  footprint: { crossTrackRad: 0.095, alongTrackRad: 0.042 },
  stroke: { idle: 0.35, gain: 1.0, widthPx: [1.25, 1.7] },
  rings: { slots: 3, lifeS: 2.8, cadenceS: 1.25, maxRadiusRad: 0.18, extentRad: 0.2, gain: 0.8 },
  heat: {
    // The illustrative heat map along the rivers has no meaning in the hero yet: hidden (and not
    // generated) unless this is true. The cyan cap, border glow, stroke and rivers always show.
    visible: false as boolean,
    // Heat left over after a pass decays to `floor` with time constant `agingS`.
    agingS: 9,
    floor: 0.35,
    // Limit of the push-broom front (radians of orbit either side of Colombia).
    frontLimit: 0.4,
    ramp: ["#0e5f73", "#15a6b5", "#e8b23a", "#ff6b2c", "#ffe2a8"],
    contourColor: "#ffe9c4",
  },
  // Radii of the overlays (globe radius 100), ordered so they never z-fight.
  radii: { patch: 100.35, stroke: 100.5, footprint: 100.6, rings: 100.7 },
  // Reduced-motion still: orbit angle relative to Colombia (radians) and camera push-in.
  stillOffsetRad: -0.1,
  cameraPush: 0.025,
} as const;

/**
 * Bloom (high preset). Only light sources and glints exceed the threshold: nav lights, the panel
 * glint, the beam's aperture, the scan line and stroke, and fresh heat when shown. Every surface
 * material stays below it through a luminance shoulder, and the ocean glint through its soft cap.
 */
export const POST = {
  bloom: { strength: 0.55, radius: 0.45, threshold: 0.92 },
  // A context lost for longer than this falls back to the CSS planet.
  contextRestoreTimeoutMs: 2000,
} as const;

/** An effect that `?off=` can disable in development builds, to isolate it during QA. */
export type HeroEffect = "rings" | "strobe" | "glint" | "oceanGlint" | "bloom" | "heat";

const HERO_EFFECTS: readonly HeroEffect[] = [
  "rings",
  "strobe",
  "glint",
  "oceanGlint",
  "bloom",
  "heat",
];

/** URL options read once when the hero mounts. */
export interface HeroUrlOptions {
  /** Quality preset forced by `?quality=`, or the default. */
  readonly quality: QualityName;
  /** True for `?lab=satellite`. */
  readonly lab: boolean;
  /** Frozen scene time from `?t=<seconds>` (development builds only), otherwise null. */
  readonly frozenTime: number | null;
  /** Effects disabled by `?off=rings,strobe,…` (development builds only), otherwise empty. */
  readonly disabledEffects: ReadonlySet<HeroEffect>;
}

/**
 * Parses the hero's URL options.
 *
 * @param search - A `location.search` string such as `"?quality=low"`.
 * @returns The quality preset, lab flag, optional frozen time and disabled effects.
 */
export function parseHeroUrlOptions(search: string): HeroUrlOptions {
  const params = new URLSearchParams(search);
  const qualityParam = params.get("quality");
  const quality: QualityName =
    qualityParam === "low" || qualityParam === "high" ? qualityParam : DEFAULT_QUALITY;
  const timeParam = params.get("t");
  const time = timeParam === null ? Number.NaN : Number(timeParam);
  const off = import.meta.env.DEV ? (params.get("off") ?? "").split(",") : [];

  return {
    quality,
    lab: params.get("lab") === "satellite",
    frozenTime: import.meta.env.DEV && Number.isFinite(time) ? time : null,
    disabledEffects: new Set(HERO_EFFECTS.filter((effect) => off.includes(effect))),
  };
}
