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
  // Night side: residual albedo light (moon- and airglow-like, enough to read the continents), a
  // deep-navy floor and the optional night-lights gain.
  nightAmbient: [0.04, 0.05, 0.085],
  nightTint: [0.005, 0.01, 0.026],
  nightLightsGain: 0.9,
  // Slow spin of the Earth about its axis while the hero is idle (degrees per second, eastward; a
  // turn takes 24 minutes). Off under reduced motion and with `?t=`.
  driftDegPerS: 0.25,
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
  // Viewpoint east of the orbit's pass point (ORBIT.passLatLng) and not below it, so the orbit
  // does not collapse onto a line.
  viewLatDeg: 12,
  viewLngOffsetDeg: 18,
  // Globe disc diameter as a fraction of the viewport height (also bounded by the width).
  discFraction: 0.72,
  // Where the globe center lands on screen, as fractions of the viewport (0,0 = top-left).
  // Desktop leaves the left side to the headline (and keeps the orbit's lower-left arc clear of
  // it); wide screens (aspect ratio from wideAspect[0], fully at wideAspect[1]) centre the globe
  // and the headline on the screen's middle, closer together; portrait screens raise the globe so
  // the headline fits underneath. hero.css mirrors all three.
  globeCenterDesktop: { x: 0.64, y: 0.56 },
  globeCenterWide: { x: 0.62, y: 0.5 },
  wideAspect: [1.4, 1.6],
  globeCenterPortrait: { x: 0.5, y: 0.3 },
  // Intro dolly-in: duration, extra distance, extra longitude and latitude it starts from.
  intro: { durationS: 3.6, distanceGain: 0.55, lngDeg: 20, latDeg: 6, exposureS: 1.4 },
  // Mouse parallax (degrees at the hero edge) and its damping rate (1/s).
  parallax: { lngDeg: 1.6, latDeg: 1.0, damping: 3.2, cssShiftPx: [8, 5] },
} as const;

/**
 * Drag on the globe, with the mouse or with a finger or pen that moves sideways (a vertical swipe
 * still scrolls the page): horizontal turns the Earth, vertical moves the camera's latitude. No
 * zoom, no pan.
 */
export const DRAG = {
  // A finger or pen must move this far (CSS px) before the drag starts; the direction decides
  // between turning the globe (sideways) and scrolling the page (vertical).
  touchSlopPx: 8,
  // The camera's latitude stays within this (degrees, absolute), so a pole never faces it.
  latLimitDeg: 60,
  // Velocity smoothing while dragging (s), inertia decay rate (1/s) and the speeds under which
  // inertia stops (rad/s for the turn, degrees/s for the latitude).
  velocitySmoothingS: 0.05,
  inertiaDamping: 3.5,
  minYawSpeed: 0.002,
  minLatSpeed: 0.1,
  // Seconds of stillness after a drag before the drift resumes and the camera eases back to the
  // framing, the ramp over which they fade in, and the easing rate (1/s).
  idleResumeS: 4,
  resumeRampS: 2,
  returnRate: 0.6,
} as const;

/**
 * Dive from the settled hero pose to a top-down (nadir, north-up) view of a site, where the case map
 * takes over (HeroHandle.dive).
 */
export const DIVE = {
  durationS: 2.6,
  // cubic-bezier: a slow start, then a long ease-out that settles on the site.
  ease: [0.5, 0, 0.1, 1],
  // Share of the dive after which the map may take over: the ease-out's tail moves the camera by
  // well under 1 %, so the crossfade can start without waiting for the last, still frames.
  handoffAt: 0.94,
  // Share of the dive over which the satellite, orbit and atmosphere fade out (the camera crosses
  // the orbit and the atmosphere shell on the way down).
  fadeEnd: 0.35,
  // An Earth turned by its drift or a drag turns back to its start over this share of the dive, so
  // the camera always lands on the same, sunlit view of the site; the dive lasts this much longer
  // per half turn to undo.
  yawUnwindEnd: 0.35,
  yawExtraS: 1,
  // The ocean sun glint fades over this part of the dive: the flat map that takes over has none.
  glintFade: [0.3, 0.85],
  // Margin between the frame's corners and the horizon at the handoff (degrees): on very wide
  // screens the camera goes lower, so the limb never shows.
  horizonMarginDeg: 2,
  // Closest the camera may get to the surface (scene units).
  minAltitude: 4,
} as const;

/**
 * The way back (HeroHandle.ascend): from the top-down view of the site up to the hero framing, the
 * dive's path in reverse, ending on the live (drifting) hero pose.
 */
export const ASCENT = {
  durationS: 2.2,
  // cubic-bezier: leaves the site gently, then settles into the hero framing.
  ease: [0.45, 0, 0.2, 1],
  // Shares of the rise over which the satellite, orbit and atmosphere fade back in (once the
  // camera is above the orbit) and the ocean glint returns.
  fadeIn: [0.55, 1],
  glintIn: [0.15, 0.7],
} as const;

/**
 * Orbit: prograde and low-inclination, fixed in space, so the satellite crosses the frame left to
 * right, climbing slightly, slowest over its pass point. The altitude is exaggerated (0.34 R) so the
 * satellite reads at hero scale.
 */
export const ORBIT = {
  // The single orbit knob. A real Earth-observation orbit would be sun-synchronous (~98°, like
  // Sentinel-2), but it crosses the frame top to bottom; it was dropped purely for composition.
  // Keep it well above 0: from this camera a near-equatorial orbit collapses into a flat line (at
  // 20° with the pass at 6°N it already does). 24° with the pass at 12°N crosses central Mexico and
  // the Caribbean, near the middle of the disc.
  inclinationDeg: 24,
  radius: 134,
  periodS: 50,
  // Where the ascending pass peaks (lat/lng with the Earth at its starting turn): a framing anchor
  // only, which the camera's viewpoint and look-at derive from. Nothing is singled out there.
  passLatLng: { lat: 12, lng: -110 },
  // Scene time of the first pass.
  peakTimeS: 9,
  // Time warp θ = 2πp − a·sin 2πp + b·sin 4πp (slow over the pass point, fast on the far side
  // with a > 0). [0, 0] is a uniform speed; [0.6, 0.075] was the earlier rhythm.
  warp: [0, 0],
  // Small yaw steering, as real Earth-observation satellites do: its amplitude on a polar orbit,
  // scaled by sin(inclination).
  yawSteerDeg: 3.9,
  // Reduced-motion still: orbit angle relative to the pass point (radians).
  stillOffsetRad: -0.1,
} as const;

/** Satellite model, materials and lights. */
export const SATELLITE = {
  variant: "A" satisfies SatelliteVariant,
  // Wingtip-to-wingtip span in model units, and its target size on screen at the pass
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
  // Panel glint, solved once per orbit: where on the orbit it happens (relative to the pass), the
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
  // Dish tracks the reference reach while it is above the horizon, otherwise it stows.
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

/**
 * Bloom (high preset). Only light sources and glints exceed the threshold: the nav lights and the
 * panel glint. Every surface material stays below it through a luminance shoulder, and the ocean
 * glint through its soft cap.
 */
export const POST = {
  bloom: { strength: 0.55, radius: 0.45, threshold: 0.92 },
  // A context lost for longer than this falls back to the CSS planet.
  contextRestoreTimeoutMs: 2000,
} as const;

/** An effect that `?off=` can disable in development builds, to isolate it during QA. */
export type HeroEffect = "strobe" | "glint" | "oceanGlint" | "bloom";

const HERO_EFFECTS: readonly HeroEffect[] = ["strobe", "glint", "oceanGlint", "bloom"];

/** URL options read once when the hero mounts. */
export interface HeroUrlOptions {
  /** Quality preset forced by `?quality=`, or the default. */
  readonly quality: QualityName;
  /** True for `?lab=satellite`. */
  readonly lab: boolean;
  /** Frozen scene time from `?t=<seconds>` (development builds only), otherwise null. */
  readonly frozenTime: number | null;
  /** Effects disabled by `?off=strobe,glint,…` (development builds only), otherwise empty. */
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
