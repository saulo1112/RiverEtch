// Mounts the hero scene: globe.gl renders the Earth, but this module owns the frame loop, the
// camera, the shading and every extra object, and tears everything down without leaking WebGL
// contexts.
import Globe, { type GlobeInstance } from "globe.gl";
import {
  ACESFilmicToneMapping,
  AdditiveBlending,
  BackSide,
  Color,
  Group,
  HalfFloatType,
  MathUtils,
  Mesh,
  PerspectiveCamera,
  ShaderMaterial,
  SphereGeometry,
  Timer,
  Vector2,
  Vector3,
  WebGLRenderTarget,
  type Object3D,
  type Texture,
} from "three";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

import { cubicBezier } from "../../lib/easing.ts";
import {
  ASCENT,
  ATMOSPHERE,
  CAMERA,
  DIVE,
  DRAG,
  EARTH,
  EARTH_NIGHT_TEXTURE,
  EARTH_WATER_TEXTURE,
  GLOBE_RADIUS,
  ORBIT,
  POST,
  QUALITY_PRESETS,
  SUN,
  type HeroEffect,
  type QualityName,
} from "./config.ts";
import { divePose } from "./dive.ts";
import {
  clampLatitudeOffset,
  decayVelocity,
  idleFactor,
  smoothVelocity,
  vectorToLatLng,
} from "./drag.ts";
import { latLngToVector3 } from "./geo.ts";
import { handoffFrame } from "./handoff.ts";
import { createSatellite, timeForOrbitOffset, type SatelliteRig } from "./satellite.ts";
import { DITHER_GLSL, SHOULDER_GLSL } from "./shaders.ts";
import { createStarfield } from "./starfield.ts";
import { createFallbackEarthTexture, loadTexture } from "./textures.ts";

/** Options for {@link mountHero}. */
export interface MountHeroOptions {
  /** Rendering quality preset. */
  readonly quality: QualityName;
  /** Render a single still frame instead of animating. */
  readonly reducedMotion: boolean;
  /** Scene time to freeze at (development QA), or null to animate normally. */
  readonly frozenTime: number | null;
  /** Effects switched off for QA (`?off=`, development builds only). */
  readonly disabledEffects: ReadonlySet<HeroEffect>;
  /** Element that receives the CSS custom properties driving the sky layers. */
  readonly cssTarget: HTMLElement;
  /** Called once the first frame with the Earth texture has been rendered. */
  readonly onReady: () => void;
  /** Called when WebGL fails after mounting; the caller should show the fallback. */
  readonly onError: (error: unknown) => void;
  /**
   * Start parked at the top-down view of this site, as a dive leaves it (the way back from the
   * case view): no intro, overlays hidden, the camera held until {@link HeroHandle.ascend}. The
   * scene then reports ready only once its sharpest Earth map is in. Ignored without animation.
   */
  readonly arriveFrom?: DiveTarget | null;
  /**
   * The reference site, which the satellite's dish tracks as the Earth turns (nothing is drawn
   * there), or null to track the orbit's pass point.
   */
  readonly site?: GeoPoint | null;
}

/** A point on the globe, in decimal degrees. */
export interface GeoPoint {
  /** Latitude in degrees. */
  readonly lat: number;
  /** Longitude in degrees. */
  readonly lng: number;
}

/** Where {@link HeroHandle.dive} takes the camera. */
export interface DiveTarget {
  /** Site latitude in degrees. */
  readonly lat: number;
  /** Site longitude in degrees. */
  readonly lng: number;
  /** Web Mercator zoom (512 px tiles) the top-down view should match at the handoff. */
  readonly zoom: number;
}

/** Options for {@link HeroHandle.dive}. */
export interface DiveOptions {
  /** Dive duration in seconds (defaults to `DIVE.durationS`). */
  readonly durationS?: number;
  /** Called every rendered frame of the dive with its linear progress, 0..1. */
  readonly onProgress?: (progress: number) => void;
}

/** A running dive. */
export interface DiveHandle {
  /** Resolves when the camera reaches the handoff pose, or when the dive is cancelled or the scene disposed. */
  readonly done: Promise<void>;
  /** Stops the dive where it is (the camera holds that pose) and resolves `done`. */
  readonly cancel: () => void;
  /**
   * The zoom the handoff pose matches: the requested one, or a larger one on very wide screens,
   * where the camera goes lower to keep the horizon out of the frame.
   */
  readonly handoffZoom: number;
}

/** Options for {@link HeroHandle.ascend}. */
export interface AscentOptions {
  /** Rise duration in seconds (defaults to `ASCENT.durationS`). */
  readonly durationS?: number;
  /** Called every rendered frame of the rise with its linear progress, 0..1. */
  readonly onProgress?: (progress: number) => void;
}

/** A running rise. */
export interface AscentHandle {
  /** Resolves when the camera is back on the hero framing (or at once if nothing was parked). */
  readonly done: Promise<void>;
  /** Jumps to the end of the rise (Skip). */
  readonly finish: () => void;
}

/** Handle returned by {@link mountHero}. */
export interface HeroHandle {
  /**
   * Flies the camera from its current pose down to a top-down, north-up view of a site, centered
   * (the globe's off-center framing blends out), while the satellite, orbit and atmosphere
   * fade away, the parallax stops and the Earth turns back from its drift. The camera then holds
   * that pose.
   *
   * @param target - Site and handoff zoom.
   * @param options - Duration and a progress callback.
   * @returns The running dive.
   */
  readonly dive: (target: DiveTarget, options?: DiveOptions) => DiveHandle;
  /**
   * Lifts the camera parked by `arriveFrom` back to the hero framing along the dive's path in
   * reverse, converging on the live pose (parallax included), so the scene's normal motion takes
   * over seamlessly; the overlays and the globe's off-center framing come back.
   *
   * @param options - Duration and a progress callback.
   * @returns The running rise.
   */
  readonly ascend: (options?: AscentOptions) => AscentHandle;
  /**
   * Allows or blocks the mouse drag (blocked during flights and while the scene is not shown); a
   * drag in progress, and its inertia, stop at once.
   *
   * @param enabled - Whether the globe can be dragged.
   */
  readonly setInteractive: (enabled: boolean) => void;
  /** Stops the scene and releases every GPU resource; safe to call more than once. */
  readonly dispose: () => void;
}

interface HeroQAWindow extends Window {
  __heroQA?: {
    readonly stats: () => Record<string, unknown>;
    readonly project: (lat: number, lng: number) => [number, number];
    readonly setYaw: (degrees: number) => void;
    readonly setSceneTime: (seconds: number) => void;
    readonly dive: (target: DiveTarget, options?: DiveOptions) => DiveHandle;
    readonly ascend: (options?: AscentOptions) => AscentHandle;
  };
}

// A camera trip between the hero framing and the top-down view of a site: "down" is the dive
// (from a snapshot of the pose it left), "up" the rise (onto the live pose, recomputed into
// `fromPosition`/`fromTarget` every frame). An "up" trip starts parked until ascend(). `site` is
// the site with the Earth at its starting turn: a "down" trip turns the Earth back from `yawFrom`
// (its drift or drag when the dive began) early on, so the end pose never depends on either.
interface DiveState {
  readonly direction: "down" | "up";
  readonly fromPosition: Vector3;
  readonly fromTarget: Vector3;
  readonly site: Vector3;
  readonly yawFrom: number;
  readonly lat: number;
  readonly zoom: number;
  // "down": overlay opacity, framing blend and glint share at the start, so a dive that begins
  // part-way through a rise continues from there instead of snapping back to full.
  readonly fadeFrom: number;
  readonly blendFrom: number;
  readonly glintFrom: number;
  durationS: number;
  onProgress: ((progress: number) => void) | undefined;
  elapsedS: number;
  parked: boolean;
  settled: boolean;
  resolve: () => void;
}

// Unit vector from the Earth towards the sun (world space, fixed).
const SUN_DIRECTION: Readonly<Vector3> = new Vector3(...SUN.dir).normalize();

// Scratch objects reused every frame.
const cameraPosition = new Vector3();
const lookTarget = new Vector3();
const projected = new Vector3();
const settledCamera = new Vector3();
const drawingBuffer = new Vector2();
const groundPoint = new Vector3();
// The framing's latitude, longitude and distance before the drag's offset (see frame()).
const framed = { lat: 0, lng: 0, distance: 0 };
const Y_AXIS: Readonly<Vector3> = new Vector3(0, 1, 0);
const TWO_PI = 2 * Math.PI;

// Wraps an angle to (−π, π].
function wrapAngle(radians: number): number {
  const wrapped = radians - TWO_PI * Math.floor((radians + Math.PI) / TWO_PI);
  return wrapped === -Math.PI ? Math.PI : wrapped;
}

const easeOutCubic = (t: number) => 1 - (1 - t) ** 3;
const easeOutQuart = (t: number) => 1 - (1 - t) ** 4;
const easeInOutCubic = (t: number) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);
const diveEase = cubicBezier(...DIVE.ease);
const ascentEase = cubicBezier(...ASCENT.ease);

const earthVertexShader = /* glsl */ `
varying vec2 vUv;
varying vec3 vNormalWorld;
varying vec3 vPositionWorld;

void main() {
  vUv = uv;
  // modelMatrix includes three-globe's -90° turn that puts longitude 0 on +Z.
  vNormalWorld = normalize(mat3(modelMatrix) * normal);
  vec4 world = modelMatrix * vec4(position, 1.0);
  vPositionWorld = world.xyz;
  gl_Position = projectionMatrix * viewMatrix * world;
}
`;

const earthFragmentShader = /* glsl */ `
#include <common>

uniform sampler2D uDayMap;
uniform sampler2D uWaterMask;
uniform sampler2D uNightMap;
uniform float uNightLights;
uniform vec3 uSunDirection;
uniform vec3 uSunColor;
uniform float uSunGain;
uniform vec3 uTwilightColor;
uniform float uTwilightTint;
uniform vec3 uRayleigh;
uniform vec3 uNightAmbient;
uniform vec3 uNightTint;
uniform float uSaturation;
uniform vec2 uTerminator;
uniform vec3 uGlint; // roughness, gain, cap
uniform vec2 uShoulder; // knee, max luminance

varying vec2 vUv;
varying vec3 vNormalWorld;
varying vec3 vPositionWorld;

${SHOULDER_GLSL}
${DITHER_GLSL}

void main() {
  vec3 normal = normalize(vNormalWorld);
  vec3 viewDirection = normalize(cameraPosition - vPositionWorld);
  float nDotL = dot(normal, uSunDirection);
  float nDotV = saturate(dot(normal, viewDirection));

  vec3 albedo = texture2D(uDayMap, vUv).rgb;
  albedo = max(mix(vec3(heroLuminance(albedo)), albedo, uSaturation), 0.0);
  float water = texture2D(uWaterMask, vUv).r;

  // Soft terminator: wrapped Lambert faded in over the terminator band.
  float lit = smoothstep(uTerminator.x, uTerminator.y, nDotL);
  float lambert = saturate(nDotL);
  float wrapped = saturate((nDotL - uTerminator.x) / (1.0 - uTerminator.x)) * lit;
  float twilight = lit * (1.0 - smoothstep(0.0, 0.3, nDotL));
  vec3 sun = uSunColor * uSunGain * mix(vec3(1.0), uTwilightColor, uTwilightTint * twilight);

  vec3 color = albedo * sun * wrapped;
  // Light scattered inside the ocean body.
  color += water * vec3(0.004, 0.011, 0.03) * sun * lambert;
  // Night side: a trace of albedo, a navy floor and the optional city lights.
  vec3 night = albedo * uNightAmbient + uNightTint + texture2D(uNightMap, vUv).rgb * uNightLights;
  color += night * (1.0 - lit);

  // Aerial perspective and the inner limb, on the day side only.
  float air = pow(1.0 - nDotV, 2.2);
  color = color * (1.0 - 0.45 * air * lit) + uRayleigh * uSunGain * 0.018 * (0.35 + 1.65 * air) * lit;
  color += uRayleigh * 0.55 * pow(1.0 - nDotV, 6.0) * smoothstep(-0.15, 0.35, nDotL);

  color = heroShoulder(color, uShoulder.x, uShoulder.y);

  // Sun glint on water (GGX with Schlick Fresnel). A soft cap keeps the lobe's shape (a hard clip
  // would flatten its core) and keeps it below the bloom threshold, so it does not flare.
  vec3 halfVector = normalize(uSunDirection + viewDirection);
  float nDotH = saturate(dot(normal, halfVector));
  float alpha = uGlint.x * uGlint.x;
  float alpha2 = alpha * alpha;
  float denominator = nDotH * nDotH * (alpha2 - 1.0) + 1.0;
  float distribution = alpha2 / (PI * denominator * denominator);
  float fresnel = 0.02 + 0.98 * pow(1.0 - saturate(dot(viewDirection, halfVector)), 5.0);
  float glint = distribution * fresnel * uGlint.y * water * lambert;
  color += uSunColor * uGlint.z * (1.0 - exp(-glint / uGlint.z));

  gl_FragColor = vec4(heroDither(color, gl_FragCoord.xy), 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

const atmosphereVertexShader = /* glsl */ `
varying vec3 vPositionWorld;

void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vPositionWorld = world.xyz;
  gl_Position = projectionMatrix * viewMatrix * world;
}
`;

const atmosphereFragmentShader = /* glsl */ `
#include <common>

uniform vec3 uSunDirection;
uniform vec3 uRayleigh;
uniform vec3 uTwilightColor;
uniform float uIntensity;
uniform float uPlanetRadius;
uniform vec2 uScaleHeights;
uniform vec2 uFade;
uniform float uForwardScatter;
uniform float uTwilight;

varying vec3 vPositionWorld;

${DITHER_GLSL}

void main() {
  // Height above the surface of the ray's closest approach to the Earth's center.
  vec3 ray = normalize(vPositionWorld - cameraPosition);
  vec3 closest = cameraPosition + ray * dot(-cameraPosition, ray);
  float height = max(length(closest) - uPlanetRadius, 0.0);
  float density = 1.15 * exp(-height / uScaleHeights.x) + 0.2 * exp(-height / uScaleHeights.y);
  density *= 1.0 - smoothstep(uFade.x, uFade.y, height);

  float sunHeight = dot(normalize(closest), uSunDirection);
  float day = smoothstep(-0.3, 0.35, sunHeight);
  float twilight = 1.0 - smoothstep(0.0, 0.35, abs(sunHeight - 0.02));
  float forward = uForwardScatter * pow(saturate(dot(ray, uSunDirection)), 8.0);
  vec3 color = density * uIntensity * (uRayleigh * (day + forward) + uTwilightColor * uTwilight * twilight);

  color = heroDither(color, gl_FragCoord.xy);
  // Premultiplied additive glow over the transparent canvas.
  gl_FragColor = vec4(color, max(color.r, max(color.g, color.b)));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

function createEarthMaterial(oceanGlint: boolean): ShaderMaterial {
  return new ShaderMaterial({
    name: "earth",
    uniforms: {
      uDayMap: { value: null },
      uWaterMask: { value: null },
      uNightMap: { value: null },
      uNightLights: { value: 0 },
      uSunDirection: { value: SUN_DIRECTION },
      uSunColor: { value: new Color(SUN.color) },
      uSunGain: { value: EARTH.sunGain },
      uTwilightColor: { value: new Color(EARTH.twilightColor) },
      uTwilightTint: { value: EARTH.twilightTint },
      uRayleigh: { value: new Color(ATMOSPHERE.rayleighColor) },
      uNightAmbient: { value: new Vector3(...EARTH.nightAmbient) },
      uNightTint: { value: new Vector3(...EARTH.nightTint) },
      uSaturation: { value: EARTH.saturation },
      uTerminator: { value: new Vector2(...EARTH.terminator) },
      uGlint: {
        value: new Vector3(EARTH.glintRoughness, oceanGlint ? EARTH.glintGain : 0, EARTH.glintMax),
      },
      uShoulder: { value: new Vector2(EARTH.shoulderKnee, EARTH.shoulderMax) },
    },
    vertexShader: earthVertexShader,
    fragmentShader: earthFragmentShader,
  });
}

function createAtmosphere(segments: readonly [number, number]): Mesh {
  const geometry = new SphereGeometry(ATMOSPHERE.radius, segments[0], segments[1]);
  const material = new ShaderMaterial({
    name: "atmosphere",
    uniforms: {
      uSunDirection: { value: SUN_DIRECTION },
      uRayleigh: { value: new Color(ATMOSPHERE.rayleighColor) },
      uTwilightColor: { value: new Color(EARTH.twilightColor) },
      uIntensity: { value: ATMOSPHERE.intensity },
      uPlanetRadius: { value: GLOBE_RADIUS },
      uScaleHeights: { value: new Vector2(...ATMOSPHERE.scaleHeights) },
      uFade: { value: new Vector2(...ATMOSPHERE.fade) },
      uForwardScatter: { value: ATMOSPHERE.forwardScatter },
      uTwilight: { value: ATMOSPHERE.twilight },
    },
    vertexShader: atmosphereVertexShader,
    fragmentShader: atmosphereFragmentShader,
    side: BackSide,
    blending: AdditiveBlending,
    premultipliedAlpha: true,
    transparent: true,
    depthWrite: false,
  });
  const mesh = new Mesh(geometry, material);
  mesh.name = "atmosphere";
  mesh.renderOrder = 1;
  return mesh;
}

/**
 * Creates the hero scene inside `container`. Throws, leaving the container empty, when the
 * browser cannot create a WebGL context.
 *
 * @param container - Empty element that globe.gl takes over (its children are replaced).
 * @param options - Quality, motion and lifecycle callbacks.
 * @returns A handle whose `dispose` tears the scene down.
 */
export function mountHero(container: HTMLElement, options: MountHeroOptions): HeroHandle {
  const preset = QUALITY_PRESETS[options.quality];
  const { cssTarget, disabledEffects } = options;
  const lifetime = new AbortController();
  const { signal } = lifetime;

  let globe: GlobeInstance;
  try {
    globe = new Globe(container, {
      animateIn: false,
      waitForGlobeReady: false,
      rendererConfig: {
        // With bloom the scene renders into a multisampled target instead.
        antialias: !preset.bloom,
        alpha: true,
        premultipliedAlpha: true,
        stencil: false,
        powerPreference: "high-performance",
      },
    });
  } catch (error) {
    // Usually a failed WebGL context; leave the container empty for the CSS fallback.
    container.replaceChildren();
    throw error;
  }
  // globe.gl starts its own loops on creation; this module drives rendering instead.
  globe.pauseAnimation();

  const earthMaterial = createEarthMaterial(!disabledEffects.has("oceanGlint"));
  // Ocean glint (roughness, gain, cap); the dive fades its gain, since the flat map has no glint.
  const earthGlint = (earthMaterial.uniforms as { uGlint: { value: Vector3 } }).uGlint.value;
  const earthGlintGain = earthGlint.y;
  globe
    .enablePointerInteraction(false)
    .backgroundColor("rgba(0,0,0,0)")
    .showAtmosphere(false)
    .globeCurvatureResolution(preset.globeCurvature)
    .globeMaterial(earthMaterial)
    .lights([]);

  const controls = globe.controls();
  controls.enabled = false;
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.enableRotate = false;
  // Also gives touch scrolling back to the page.
  controls.disconnect();

  const renderer = globe.renderer();
  // Count every pass of a frame together (reset once per frame in renderFrame).
  renderer.info.autoReset = false;
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = options.reducedMotion ? 1 : 0;
  let pixelRatio = Math.min(window.devicePixelRatio, preset.dprCap);
  renderer.setPixelRatio(pixelRatio);
  const composer = globe.postProcessingComposer();
  composer.setPixelRatio(pixelRatio);

  // High preset: globe.gl's composer only holds a render pass, so render into a multisampled
  // half-float target and add bloom plus an output pass (tone mapping and sRGB) after it. Low
  // preset: the render pass draws straight to the antialiased canvas and glows use sprites.
  let bloomPass: UnrealBloomPass | null = null;
  let outputPass: OutputPass | null = null;
  if (preset.bloom) {
    const samples = pixelRatio < 1.25 ? 4 : pixelRatio < 1.75 ? 2 : 0;
    composer.reset(new WebGLRenderTarget(1, 1, { type: HalfFloatType, samples }));
    composer.setPixelRatio(pixelRatio);
    const { strength, radius, threshold } = POST.bloom;
    bloomPass = new UnrealBloomPass(new Vector2(1, 1), strength, radius, threshold);
    // `?off=bloom` keeps the same target and output pass, so only the bloom itself changes.
    bloomPass.enabled = !disabledEffects.has("bloom");
    outputPass = new OutputPass();
    composer.addPass(bloomPass);
    composer.addPass(outputPass);
  }

  const camera = globe.camera() as PerspectiveCamera;
  camera.up.set(0, 1, 0);

  const scene = globe.scene();
  const heroRoot = new Group();
  heroRoot.name = "heroRoot";
  scene.add(heroRoot);

  const atmosphere = createAtmosphere(preset.shellSegments);
  const atmosphereUniforms = (atmosphere.material as ShaderMaterial).uniforms as {
    uIntensity: { value: number };
  };
  const starfield = createStarfield(preset.stars, pixelRatio);
  heroRoot.add(starfield.object, atmosphere);

  // The satellite's dish tracks the site (in the Earth frame, which turns), or its pass point.
  const site = options.site ?? null;
  const dishTarget =
    site === null ? null : latLngToVector3(site.lat, site.lng, GLOBE_RADIUS, new Vector3());
  // three-globe's root object (found in loadSurface): the Earth's drift turns it. The sun, orbit
  // and camera stay in world space.
  let earthRoot: Object3D | null = null;
  // The Earth's turn about its axis (radians, eastward), wrapped to (−π, π].
  let earthYaw = 0;
  const driftRate = MathUtils.degToRad(EARTH.driftDegPerS);

  // Mouse drag. A horizontal drag turns the Earth; a vertical one offsets the camera's latitude from
  // the framing (degrees, `userLat`).
  let interactive = false;
  let dragId: number | null = null;
  const dragLast = { x: 0, y: 0, timeStamp: 0 };
  // Inertia after a release: the Earth's turn (rad/s) and the camera's latitude (degrees/s).
  const velocity = { yaw: 0, lat: 0 };
  // Seconds since the last drag and its inertia ended (Infinity before any drag: idle already).
  let idleS = Number.POSITIVE_INFINITY;
  let userLat = 0;
  // The globe's radius on screen (CSS px): a drag turns the surface about as fast as the pointer.
  let radiusPx = 1;
  let stillQueued = false;

  const earthUniforms = earthMaterial.uniforms as {
    uDayMap: { value: Texture | null };
    uWaterMask: { value: Texture | null };
    uNightMap: { value: Texture | null };
    uNightLights: { value: number };
  };
  const ownedTextures = new Set<Texture>();
  let satellite: SatelliteRig | null = null;

  // Camera rig state. `sceneTime` starts when the Earth texture is ready.
  let sceneTime = 0;
  let baseDistance = 335;
  let widthWeight = 1;
  const pointerTarget = { x: 0, y: 0 };
  const pointer = { x: 0, y: 0 };
  const cssParallax = { x: Number.NaN, y: Number.NaN };

  let rafId = 0;
  let running = false;
  let started = false;
  let onScreen = true;
  let contextLost = false;
  let contextTimer = 0;
  let readyNotified = false;
  let disposed = false;
  const timer = new Timer();
  timer.connect(document);
  const animate = !options.reducedMotion && options.frozenTime === null;
  // Reduced motion shows one settled frame just before the pass (intro finished, no drift).
  const stillTime = Math.max(timeForOrbitOffset(ORBIT.stillOffsetRad), CAMERA.intro.durationS);

  // View-offset shift (px) that moves the globe center to its configured screen position.
  const viewShift = { x: 0, y: 0, width: 1, height: 1 };
  // Share of that shift in use: 1 normally, blended to 0 (centered) by the dive.
  let viewBlend = 1;
  let dive: DiveState | null = null;
  // Opacity of the satellite, orbit and atmosphere (the dive fades them out).
  let overlayFade = 1;
  // Coming back from the case view: parked over the site, past the intro, overlays hidden.
  const arrival = animate ? (options.arriveFrom ?? null) : null;
  if (arrival !== null) {
    sceneTime = CAMERA.intro.durationS;
    renderer.toneMappingExposure = 1;
    viewBlend = 0;
    dive = {
      direction: "up",
      fromPosition: new Vector3(),
      fromTarget: new Vector3(),
      site: latLngToVector3(arrival.lat, arrival.lng, 1, new Vector3()),
      yawFrom: 0,
      lat: arrival.lat,
      zoom: arrival.zoom,
      fadeFrom: 1,
      blendFrom: 1,
      glintFrom: 1,
      durationS: ASCENT.durationS,
      onProgress: undefined,
      elapsedS: 0,
      parked: true,
      settled: false,
      resolve: () => undefined,
    };
  }

  function layout(): void {
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    globe.width(width).height(height);

    const aspect = width / height;
    camera.aspect = aspect;
    // Narrow screens look at the globe more frontally, so it stays inside the frame.
    widthWeight = 0.35 + 0.65 * MathUtils.smoothstep(aspect, 0.6, 1.2);
    // Fit the globe disc to the viewport height, but never wider than the viewport.
    const tanHalfFov = Math.tan(MathUtils.degToRad(CAMERA.fovDeg / 2));
    const tanAngular = Math.min(CAMERA.discFraction * tanHalfFov, 0.88 * tanHalfFov * aspect);
    baseDistance = GLOBE_RADIUS / Math.sin(Math.atan(tanAngular));
    radiusPx = Math.max(1, (height / 2) * (tanAngular / tanHalfFov));

    // Project the globe center from the settled pose, then shift the view so it lands on the goal.
    poseCamera(Number.POSITIVE_INFINITY, false, false);
    settledCamera.copy(camera.position);
    camera.near = CAMERA.near;
    camera.far = CAMERA.far;
    camera.fov = CAMERA.fovDeg;
    camera.clearViewOffset();
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    projected.set(0, 0, 0).project(camera);
    const wide = MathUtils.smoothstep(aspect, ...CAMERA.wideAspect);
    const { globeCenterDesktop: desktop, globeCenterWide: wideCenter } = CAMERA;
    const goal =
      aspect >= 1
        ? {
            x: MathUtils.lerp(desktop.x, wideCenter.x, wide),
            y: MathUtils.lerp(desktop.y, wideCenter.y, wide),
          }
        : CAMERA.globeCenterPortrait;
    viewShift.x = ((projected.x + 1) / 2 - goal.x) * width;
    viewShift.y = ((1 - projected.y) / 2 - goal.y) * height;
    viewShift.width = width;
    viewShift.height = height;
    syncProjection();
    frameSatellite();
    cssTarget.style.setProperty("--globe-x", `${(goal.x * 100).toFixed(2)}%`);
    cssTarget.style.setProperty("--globe-y", `${(goal.y * 100).toFixed(2)}%`);
  }

  function frameSatellite(): void {
    const height = Math.max(1, container.clientHeight);
    drawingBuffer.set(
      Math.floor(Math.max(1, container.clientWidth) * pixelRatio),
      Math.floor(height * pixelRatio),
    );
    satellite?.setFraming(settledCamera, height, CAMERA.fovDeg, drawingBuffer, pixelRatio);
  }

  // Places the camera for scene time `timeS`; `withMotion` adds the parallax, `withUser` the drag's
  // latitude offset.
  function poseCamera(timeS: number, withMotion: boolean, withUser: boolean): void {
    computePose(timeS, withMotion, withUser, cameraPosition, lookTarget);
    camera.position.copy(cameraPosition);
    camera.lookAt(lookTarget);
  }

  // The framing's own latitude, longitude and distance at scene time `timeS` (into `framed`).
  function frame(timeS: number, withMotion: boolean): void {
    const { intro, parallax } = CAMERA;
    const progress = MathUtils.clamp(timeS / intro.durationS, 0, 1);
    const dolly = easeInOutCubic(progress);
    framed.distance = baseDistance * (1 + intro.distanceGain * (1 - easeOutQuart(progress)));
    framed.lat = CAMERA.viewLatDeg * widthWeight - intro.latDeg * (1 - easeOutCubic(progress));
    framed.lng =
      ORBIT.passLatLng.lng + CAMERA.viewLngOffsetDeg * widthWeight + intro.lngDeg * (1 - dolly);
    if (withMotion) {
      framed.lng += pointer.x * parallax.lngDeg * dolly;
      framed.lat -= pointer.y * parallax.latDeg * dolly;
    }
  }

  // The hero pose at scene time `timeS`: camera position, and the globe center to look at (the
  // view offset puts that center at its place on screen).
  function computePose(
    timeS: number,
    withMotion: boolean,
    withUser: boolean,
    position: Vector3,
    target: Vector3,
  ) {
    frame(timeS, withMotion);
    const lat = withUser
      ? MathUtils.clamp(framed.lat + userLat, -DRAG.latLimitDeg, DRAG.latLimitDeg)
      : framed.lat;
    latLngToVector3(lat, framed.lng, framed.distance, position);
    target.set(0, 0, 0);
  }

  // One frame of the idle behaviour: drag inertia, then (after a pause) the Earth's drift and the
  // camera easing back to the framing.
  function stepInteraction(dt: number): void {
    const coasting = velocity.yaw !== 0 || velocity.lat !== 0;
    if (dragId === null && coasting) {
      if (earthRoot !== null) {
        setEarthYaw(earthYaw + velocity.yaw * dt);
      }
      const next = userLat + velocity.lat * dt;
      userLat = clampLatitudeOffset(CAMERA.viewLatDeg * widthWeight, next, DRAG.latLimitDeg);
      velocity.yaw = decayVelocity(velocity.yaw, DRAG.inertiaDamping, dt, DRAG.minYawSpeed);
      velocity.lat =
        userLat === next
          ? decayVelocity(velocity.lat, DRAG.inertiaDamping, dt, DRAG.minLatSpeed)
          : 0;
    } else if (dragId === null) {
      idleS += dt;
    }
    const resume =
      dragId === null && !coasting ? idleFactor(idleS, DRAG.idleResumeS, DRAG.resumeRampS) : 0;
    if (resume > 0) {
      if (earthRoot !== null) {
        setEarthYaw(earthYaw + driftRate * dt * resume);
      }
      userLat = MathUtils.damp(userLat, 0, DRAG.returnRate * resume, dt);
    }
  }

  // Ends a drag; with `coast`, the turn carries on and slows down (never under reduced motion).
  function finishDrag(coast: boolean): void {
    const id = dragId;
    dragId = null;
    if (id !== null && cssTarget.hasPointerCapture(id)) {
      cssTarget.releasePointerCapture(id);
    }
    if (!coast) {
      velocity.yaw = 0;
      velocity.lat = 0;
    }
    idleS = 0;
    syncDragCursor();
  }

  // The grab cursor (drag.css) shows only while the globe can be dragged.
  function syncDragCursor(): void {
    if (interactive && !disposed) {
      cssTarget.dataset.heroDrag = dragId === null ? "idle" : "dragging";
    } else {
      delete cssTarget.dataset.heroDrag;
    }
  }

  // Without animation (reduced motion, a frozen time) frames render on demand, one per animation
  // frame at most.
  function requestStill(): void {
    if (stillQueued || running || !started || disposed) {
      return;
    }
    stillQueued = true;
    requestAnimationFrame(() => {
      stillQueued = false;
      if (!disposed && !running) {
        renderFrame(undefined);
      }
    });
  }

  // globe.gl's debounced digests reset `far` (from its sky radius) and clear the view offset;
  // restore ours before every render.
  function syncProjection(): void {
    const view = camera.view;
    const offsetX = viewShift.x * viewBlend;
    const offsetY = viewShift.y * viewBlend;
    const viewMatches =
      view !== null &&
      view.enabled &&
      view.offsetX === offsetX &&
      view.offsetY === offsetY &&
      view.fullWidth === viewShift.width &&
      view.fullHeight === viewShift.height;
    if (
      viewMatches &&
      camera.near === CAMERA.near &&
      camera.far === CAMERA.far &&
      camera.fov === CAMERA.fovDeg
    ) {
      return;
    }
    camera.near = CAMERA.near;
    camera.far = CAMERA.far;
    camera.fov = CAMERA.fovDeg;
    // setViewOffset also updates the projection matrix.
    camera.setViewOffset(
      viewShift.width,
      viewShift.height,
      offsetX,
      offsetY,
      viewShift.width,
      viewShift.height,
    );
  }

  function writeCssParallax(): void {
    // Only touch the style when the sky would move by at least ~0.1 px.
    if (
      Math.abs(pointer.x - cssParallax.x) < 0.0125 &&
      Math.abs(pointer.y - cssParallax.y) < 0.0125
    ) {
      return;
    }
    cssParallax.x = pointer.x;
    cssParallax.y = pointer.y;
    cssTarget.style.setProperty("--px", pointer.x.toFixed(3));
    cssTarget.style.setProperty("--py", pointer.y.toFixed(3));
  }

  function setOverlayFade(alpha: number): void {
    if (alpha === overlayFade) {
      return;
    }
    overlayFade = alpha;
    atmosphereUniforms.uIntensity.value = ATMOSPHERE.intensity * alpha;
    atmosphere.visible = alpha > 0;
    satellite?.setFade(alpha);
  }

  // Turns the Earth (three-globe's object) about its axis.
  function setEarthYaw(radians: number): void {
    earthYaw = wrapAngle(radians);
    if (earthRoot !== null) {
      earthRoot.rotation.y = earthYaw;
    }
  }

  // three-globe's object (a direct child of the scene) holding the Earth mesh. Its shading reads
  // world-space normals, so turning the object keeps the sun where it is.
  function findEarthRoot(): Object3D | null {
    let node: Object3D | null = scene.getObjectByProperty("material", earthMaterial) ?? null;
    while (node !== null && node.parent !== scene) {
      node = node.parent;
    }
    return node;
  }

  // Advances the dive or the rise by `frameS` seconds of wall-clock time and poses the camera.
  function advanceDive(state: DiveState, frameS: number): void {
    if (!state.settled && !state.parked) {
      state.elapsedS = Math.min(state.durationS, state.elapsedS + frameS);
    }
    const progress = state.durationS > 0 ? state.elapsedS / state.durationS : 1;
    const up = state.direction === "up";
    // k: how far along from the hero framing (0) to the top-down view (1).
    const k = up ? 1 - ascentEase(progress) : diveEase(progress);
    if (up) {
      computePose(sceneTime, !options.reducedMotion, true, state.fromPosition, state.fromTarget);
    }
    const { distance } = handoffFrame(
      state.zoom,
      state.lat,
      Math.max(1, container.clientWidth),
      Math.max(1, container.clientHeight),
      CAMERA.fovDeg,
    );
    divePose(
      k,
      state.fromPosition,
      state.fromTarget,
      state.site,
      distance,
      cameraPosition,
      lookTarget,
    );
    camera.position.copy(cameraPosition);
    camera.lookAt(lookTarget);
    viewBlend = up ? 1 - k : state.blendFrom * (1 - k);
    if (up) {
      setOverlayFade(MathUtils.smoothstep(progress, ...ASCENT.fadeIn));
      earthGlint.y = earthGlintGain * MathUtils.smoothstep(progress, ...ASCENT.glintIn);
    } else {
      if (state.yawFrom !== 0) {
        setEarthYaw(state.yawFrom * (1 - MathUtils.smoothstep(progress, 0, DIVE.yawUnwindEnd)));
      }
      setOverlayFade(state.fadeFrom * (1 - MathUtils.smoothstep(progress, 0, DIVE.fadeEnd)));
      earthGlint.y =
        state.glintFrom * earthGlintGain * (1 - MathUtils.smoothstep(progress, ...DIVE.glintFade));
    }
    if (!state.settled && !state.parked) {
      state.onProgress?.(progress);
      if (progress >= 1) {
        state.settled = true;
        state.resolve();
        // Back on the live pose: the normal loop takes over from the next frame.
        if (up && dive === state) {
          dive = null;
        }
      }
    }
  }

  function renderFrame(timestamp: number | undefined): void {
    timer.update(timestamp);
    // Clamp both ends: the first frame after a reset can report a slightly negative delta. The
    // dive runs on wall-clock time (bounded), so a slow GPU does not stretch it; the scene's own
    // motion keeps the 1/30 s cap.
    const frameS = MathUtils.clamp(timer.getDelta(), 0, 0.25);
    const dt = Math.min(frameS, 1 / 30);
    if (animate) {
      sceneTime += dt;
    } else {
      sceneTime = options.frozenTime ?? stillTime;
    }

    if (!options.reducedMotion && (dive === null || dive.direction === "up")) {
      const damping = CAMERA.parallax.damping;
      pointer.x = MathUtils.damp(pointer.x, pointerTarget.x, damping, dt);
      pointer.y = MathUtils.damp(pointer.y, pointerTarget.y, damping, dt);
      writeCssParallax();
      renderer.toneMappingExposure = easeOutCubic(
        MathUtils.clamp(sceneTime / CAMERA.intro.exposureS, 0, 1),
      );
    }

    if (dive === null) {
      // The Earth drifts only while the hero is idle (a dive turns it back, a rise keeps it still).
      if (animate) {
        stepInteraction(dt);
      }
      poseCamera(sceneTime, !options.reducedMotion, true);
    } else {
      advanceDive(dive, frameS);
    }
    syncProjection();
    starfield.update(sceneTime);
    renderer.info.reset();
    if (satellite !== null) {
      const ground =
        dishTarget === null
          ? undefined
          : groundPoint.copy(dishTarget).applyAxisAngle(Y_AXIS, earthYaw);
      satellite.update(sceneTime, dt, camera.position, options.reducedMotion, ground);
    }
    composer.render(dt);
    if (!readyNotified && earthUniforms.uDayMap.value !== null) {
      readyNotified = true;
      options.onReady();
    }
  }

  function tick(timestamp: number): void {
    rafId = requestAnimationFrame(tick);
    renderFrame(timestamp);
  }

  function start(): void {
    if (
      running ||
      disposed ||
      !started ||
      (!animate && dive === null) ||
      document.hidden ||
      !onScreen ||
      contextLost
    ) {
      return;
    }
    running = true;
    timer.reset();
    rafId = requestAnimationFrame(tick);
  }

  function stop(): void {
    running = false;
    cancelAnimationFrame(rafId);
  }

  function renderStill(): void {
    // globe.gl applies props in a debounced digest; wait two frames before the single render.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (!disposed && !running) {
          renderFrame(undefined);
        }
      });
    });
  }

  const resizeObserver = new ResizeObserver(() => {
    layout();
    if (!running && started) {
      renderStill();
    }
  });
  resizeObserver.observe(container);
  layout();

  document.addEventListener(
    "visibilitychange",
    () => {
      if (document.hidden) {
        stop();
      } else {
        start();
      }
    },
    { signal },
  );

  // Pause while the hero is scrolled out of view.
  const intersectionObserver = new IntersectionObserver(
    (entries) => {
      onScreen = entries.some((entry) => entry.isIntersecting);
      if (onScreen) {
        start();
      } else {
        stop();
      }
    },
    { threshold: 0 },
  );
  intersectionObserver.observe(cssTarget);

  // Context loss: wait briefly for a restore, otherwise hand over to the CSS fallback.
  const canvas = renderer.domElement;
  canvas.addEventListener(
    "webglcontextlost",
    (event) => {
      event.preventDefault();
      contextLost = true;
      stop();
      contextTimer = window.setTimeout(() => {
        options.onError(new Error("The WebGL context was lost and not restored."));
      }, POST.contextRestoreTimeoutMs);
    },
    { signal },
  );
  canvas.addEventListener(
    "webglcontextrestored",
    () => {
      window.clearTimeout(contextTimer);
      contextLost = false;
      // Textures re-upload from their sources; the environment map has to be re-rendered.
      satellite?.restoreAfterContextLoss();
      if (animate) {
        start();
      } else {
        renderStill();
      }
    },
    { signal },
  );

  // Follow device-pixel-ratio changes (moving the window to another screen, zooming).
  function watchPixelRatio(): void {
    const query = window.matchMedia(`(resolution: ${String(window.devicePixelRatio)}dppx)`);
    query.addEventListener(
      "change",
      () => {
        if (disposed) {
          return;
        }
        pixelRatio = Math.min(window.devicePixelRatio, preset.dprCap);
        renderer.setPixelRatio(pixelRatio);
        composer.setPixelRatio(pixelRatio);
        starfield.setPixelRatio(pixelRatio);
        layout();
        if (!running && started) {
          renderStill();
        }
        watchPixelRatio();
      },
      { once: true, signal },
    );
  }
  watchPixelRatio();

  if (!options.reducedMotion) {
    window.addEventListener(
      "pointermove",
      (event) => {
        // Touch and pen drags scroll the page; only a hovering mouse steers the parallax, and not
        // while it drags the globe.
        if (event.pointerType !== "mouse" || dragId !== null) {
          return;
        }
        const rect = cssTarget.getBoundingClientRect();
        pointerTarget.x = MathUtils.clamp(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -1,
          1,
        );
        pointerTarget.y = MathUtils.clamp(
          ((event.clientY - rect.top) / rect.height) * 2 - 1,
          -1,
          1,
        );
      },
      { passive: true, signal },
    );
    document.addEventListener(
      "pointerout",
      (event) => {
        if (event.relatedTarget === null) {
          pointerTarget.x = 0;
          pointerTarget.y = 0;
        }
      },
      { passive: true, signal },
    );
  }

  // Mouse drag on the scene, wherever the overlay leaves it (the overlay's controls, panels and text
  // take their own presses). Reduced motion keeps the drag, without inertia or drift.
  const onOverlay = (target: EventTarget | null) =>
    target instanceof Element && target.closest(".hero-ui") !== null;
  cssTarget.addEventListener(
    "pointerdown",
    (event) => {
      if (
        !interactive ||
        dive !== null ||
        dragId !== null ||
        event.pointerType !== "mouse" ||
        event.button !== 0 ||
        onOverlay(event.target)
      ) {
        return;
      }
      // No text selection, no focus change.
      event.preventDefault();
      dragId = event.pointerId;
      try {
        cssTarget.setPointerCapture(event.pointerId);
      } catch {
        // The pointer is already gone (or synthetic): the drag still ends on its pointerup.
      }
      dragLast.x = event.clientX;
      dragLast.y = event.clientY;
      dragLast.timeStamp = event.timeStamp;
      velocity.yaw = 0;
      velocity.lat = 0;
      idleS = 0;
      syncDragCursor();
    },
    { signal },
  );
  cssTarget.addEventListener(
    "pointermove",
    (event) => {
      if (event.pointerId !== dragId) {
        return;
      }
      const dt = Math.max(0.001, (event.timeStamp - dragLast.timeStamp) / 1000);
      // Moving the pointer by the globe's radius turns the surface by about a radian.
      const yaw = (event.clientX - dragLast.x) / radiusPx;
      const lat = MathUtils.radToDeg((event.clientY - dragLast.y) / radiusPx);
      dragLast.x = event.clientX;
      dragLast.y = event.clientY;
      dragLast.timeStamp = event.timeStamp;
      if (earthRoot !== null) {
        setEarthYaw(earthYaw + yaw);
      }
      userLat = clampLatitudeOffset(
        CAMERA.viewLatDeg * widthWeight,
        userLat + lat,
        DRAG.latLimitDeg,
      );
      const { velocitySmoothingS: smoothing } = DRAG;
      velocity.yaw = MathUtils.clamp(smoothVelocity(velocity.yaw, yaw / dt, dt, smoothing), -4, 4);
      velocity.lat = MathUtils.clamp(
        smoothVelocity(velocity.lat, lat / dt, dt, smoothing),
        -240,
        240,
      );
      requestStill();
    },
    { signal },
  );
  const endDrag = (event: PointerEvent) => {
    if (event.pointerId !== dragId) {
      return;
    }
    // A release while still moving coasts; a pause before letting go does not.
    finishDrag(animate && event.type === "pointerup" && event.timeStamp - dragLast.timeStamp < 80);
  };
  cssTarget.addEventListener("pointerup", endDrag, { signal });
  cssTarget.addEventListener("pointercancel", endDrag, { signal });
  cssTarget.addEventListener("lostpointercapture", endDrag, { signal });

  function adopt(texture: Texture): Texture {
    ownedTextures.add(texture);
    return texture;
  }

  async function loadSurface(): Promise<void> {
    const [day, water, rig] = await Promise.allSettled([
      loadTexture(preset.earthTexture, renderer, signal, "color"),
      loadTexture(EARTH_WATER_TEXTURE, renderer, signal, "data"),
      createSatellite(renderer, preset, signal, disabledEffects),
    ]);
    if (signal.aborted) {
      for (const result of [day, water, rig]) {
        if (result.status === "fulfilled") {
          result.value.dispose();
        }
      }
      return;
    }
    if (rig.status === "fulfilled") {
      satellite = rig.value;
      heroRoot.add(...satellite.objects);
      if (overlayFade < 1) {
        satellite.setFade(overlayFade);
      }
      frameSatellite();
    } else if (import.meta.env.DEV) {
      console.error("[hero] Could not build the satellite.", rig.reason);
    }
    if (day.status === "fulfilled") {
      earthUniforms.uDayMap.value = adopt(day.value);
    } else {
      if (import.meta.env.DEV) {
        console.warn(
          `[hero] Could not load textures/${preset.earthTexture}; using a procedural placeholder.`,
          day.reason,
        );
      }
      earthUniforms.uDayMap.value = adopt(createFallbackEarthTexture());
    }
    if (water.status === "fulfilled") {
      earthUniforms.uWaterMask.value = adopt(water.value);
    }

    // Compile every program up front, so the first pass does not hitch.
    try {
      await renderer.compileAsync(scene, camera);
    } catch {
      // Compilation errors surface again on the first render; nothing to do here.
    }
    if (disposed) {
      return;
    }

    // Coming back from the case view, the first frames are the close top-down view: wait for the
    // sharp map, so it does not swap in visibly during the rise. (start() ignores a disposed scene.)
    if (arrival !== null) {
      await loadDetailTexture();
    }
    // three-globe adds its Earth mesh in a debounced digest, long done by now.
    earthRoot = findEarthRoot();
    if (earthRoot === null && import.meta.env.DEV) {
      console.warn("[hero] Could not find the globe's object; the Earth will not drift.");
    }
    started = true;
    if (animate) {
      start();
    } else {
      renderStill();
    }
    if (arrival === null) {
      void loadDetailTexture();
    }
  }

  // Swaps in the sharper Earth map once the scene runs; the upload happens before the swap.
  async function loadDetailTexture(): Promise<void> {
    if (preset.earthTextureDetail === null) {
      return;
    }
    try {
      const detail = await loadTexture(preset.earthTextureDetail, renderer, signal, "color");
      if (signal.aborted || contextLost) {
        detail.dispose();
        return;
      }
      renderer.initTexture(detail);
      const previous = earthUniforms.uDayMap.value;
      earthUniforms.uDayMap.value = adopt(detail);
      if (previous !== null) {
        ownedTextures.delete(previous);
        previous.dispose();
      }
      if (!running && started) {
        renderStill();
      }
    } catch {
      // Keep the first map.
    }
  }

  async function loadNightLights(): Promise<void> {
    try {
      const night = await loadTexture(EARTH_NIGHT_TEXTURE, renderer, signal, "color");
      if (signal.aborted) {
        night.dispose();
        return;
      }
      earthUniforms.uNightMap.value = adopt(night);
      earthUniforms.uNightLights.value = EARTH.nightLightsGain;
      if (!running && started) {
        renderStill();
      }
    } catch {
      // The night-lights map is optional; without it the night side stays dark.
    }
  }

  void loadSurface();
  void loadNightLights();

  function startDive(target: DiveTarget, diveOptions: DiveOptions = {}): DiveHandle {
    // No drag or inertia during a flight; the dive starts from exactly the pose of the last frame
    // (motion and drag included).
    if (dragId !== null) {
      finishDrag(false);
    }
    velocity.yaw = 0;
    velocity.lat = 0;
    if (dive === null) {
      poseCamera(sceneTime, !options.reducedMotion, true);
    }
    const { zoom } = handoffFrame(
      target.zoom,
      target.lat,
      Math.max(1, container.clientWidth),
      Math.max(1, container.clientHeight),
      CAMERA.fovDeg,
    );
    if (dive !== null && !dive.settled) {
      dive.settled = true;
      dive.resolve();
    }
    let resolveDone: (() => void) | undefined;
    const done = new Promise<void>((settle) => {
      resolveDone = settle;
    });
    // The further the Earth has drifted, the longer the dive, so turning it back stays gentle.
    const yawFrom = earthYaw;
    const state: DiveState = {
      direction: "down",
      fromPosition: camera.position.clone(),
      fromTarget: lookTarget.clone(),
      site: latLngToVector3(target.lat, target.lng, 1, new Vector3()),
      yawFrom,
      lat: target.lat,
      zoom: target.zoom,
      fadeFrom: overlayFade,
      blendFrom: viewBlend,
      glintFrom: earthGlintGain > 0 ? earthGlint.y / earthGlintGain : 1,
      durationS: Math.max(
        0,
        diveOptions.durationS ?? DIVE.durationS + (DIVE.yawExtraS * Math.abs(yawFrom)) / Math.PI,
      ),
      onProgress: diveOptions.onProgress,
      elapsedS: 0,
      parked: false,
      settled: false,
      resolve: () => {
        resolveDone?.();
      },
    };
    dive = state;
    if (disposed || !started || document.hidden || !onScreen || contextLost) {
      // Nothing renders (still loading, hidden, off-screen or without a context), so the dive
      // could not progress: it settles at once.
      setEarthYaw(0);
      state.settled = true;
      state.resolve();
    } else {
      start();
    }
    return {
      done,
      handoffZoom: zoom,
      cancel() {
        if (!state.settled) {
          state.settled = true;
          state.resolve();
        }
      },
    };
  }

  // Ends a rise at once: the hero framing, overlays and glint back, the normal loop in charge.
  function settleAscent(state: DiveState): void {
    state.elapsedS = state.durationS;
    state.parked = false;
    if (!state.settled) {
      state.settled = true;
      state.resolve();
    }
    if (dive === state) {
      dive = null;
    }
    viewBlend = 1;
    setOverlayFade(1);
    earthGlint.y = earthGlintGain;
  }

  function startAscend(ascentOptions: AscentOptions = {}): AscentHandle {
    const state = dive;
    if (state?.direction !== "up" || !state.parked) {
      return { done: Promise.resolve(), finish: () => undefined };
    }
    let resolveDone: (() => void) | undefined;
    const done = new Promise<void>((settle) => {
      resolveDone = settle;
    });
    state.resolve = () => {
      resolveDone?.();
    };
    state.durationS = Math.max(0, ascentOptions.durationS ?? ASCENT.durationS);
    state.onProgress = ascentOptions.onProgress;
    state.parked = false;
    if (disposed || !started || document.hidden || !onScreen || contextLost) {
      // Nothing renders, so the rise could not progress: land on the hero framing at once.
      settleAscent(state);
    } else {
      start();
    }
    return {
      done,
      finish() {
        if (state.settled) {
          return;
        }
        if (running) {
          // The next frame lands on the live pose and hands over to the normal loop.
          state.elapsedS = state.durationS;
        } else {
          settleAscent(state);
          renderStill();
        }
      },
    };
  }

  if (import.meta.env.DEV) {
    // Development-only QA hook for headless screenshots.
    (window as HeroQAWindow).__heroQA = {
      stats: () => {
        camera.updateMatrixWorld();
        const width = container.clientWidth;
        const height = container.clientHeight;
        const toPixels = (point: Vector3): [number, number] => {
          projected.copy(point).project(camera);
          return [((projected.x + 1) / 2) * width, ((1 - projected.y) / 2) * height];
        };
        // Wingtip to wingtip on screen.
        let satelliteSpanPx: number | null = null;
        if (satellite !== null) {
          const { position, attitude, scale } = satellite.state;
          const half = new Vector3(1, 0, 0).applyQuaternion(attitude).multiplyScalar(12 * scale);
          const [ax, ay] = toPixels(position.clone().add(half));
          const [bx, by] = toPixels(position.clone().sub(half));
          satelliteSpanPx = Math.hypot(ax - bx, ay - by);
        }
        projected.set(0, 0, 0).project(camera);
        return {
          satelliteSpanPx,
          sceneTime,
          viewport: [container.clientWidth, container.clientHeight],
          globeCenterPx: [
            ((projected.x + 1) / 2) * container.clientWidth,
            ((1 - projected.y) / 2) * container.clientHeight,
          ],
          baseDistance,
          satelliteScale: satellite?.state.scale ?? null,
          glint: satellite?.state.glint ?? null,
          satelliteAngleDeg: satellite === null ? null : MathUtils.radToDeg(satellite.state.angle),
          earthYawDeg: MathUtils.radToDeg(earthYaw),
          userLatDeg: userLat,
          interactive,
          dragging: dragId !== null,
          inertia: [velocity.yaw, velocity.lat],
          cameraLatLng: vectorToLatLng(camera.position.x, camera.position.y, camera.position.z),
          earthRootFound: earthRoot !== null,
          exposure: renderer.toneMappingExposure,
          diveDirection: dive?.direction ?? null,
          diveParked: dive?.parked ?? null,
          diveProgress: dive === null ? null : dive.elapsedS / Math.max(1e-6, dive.durationS),
          diveDurationS: dive?.durationS ?? null,
          overlayFade,
          viewBlend,
          cameraAltitude: camera.position.length() - GLOBE_RADIUS,
          drawCalls: renderer.info.render.calls,
          triangles: renderer.info.render.triangles,
        };
      },
      dive: startDive,
      ascend: startAscend,
      // Screen position (CSS px) of a geographic point with the current camera and Earth turn.
      project: (lat, lng) => {
        camera.updateMatrixWorld();
        latLngToVector3(lat, lng, GLOBE_RADIUS, projected).applyAxisAngle(Y_AXIS, earthYaw);
        projected.project(camera);
        return [
          ((projected.x + 1) / 2) * container.clientWidth,
          ((1 - projected.y) / 2) * container.clientHeight,
        ];
      },
      // Jumps the scene clock (the orbit) without rendering; the next frame picks it up.
      setSceneTime: (seconds) => {
        sceneTime = seconds;
      },
      // Turns the Earth to a given drift (degrees), as if it had drifted that far.
      setYaw: (degrees) => {
        if (earthRoot === null || dive !== null) {
          return;
        }
        setEarthYaw(MathUtils.degToRad(degrees));
        if (!running && started) {
          renderStill();
        }
      },
    };
  }

  return {
    dive: startDive,
    ascend: startAscend,
    setInteractive(enabled) {
      interactive = enabled && !disposed;
      if (!interactive) {
        if (dragId !== null) {
          finishDrag(false);
        }
        velocity.yaw = 0;
        velocity.lat = 0;
      }
      syncDragCursor();
    },
    dispose(): void {
      if (disposed) {
        return;
      }
      disposed = true;
      if (dive !== null && !dive.settled) {
        dive.settled = true;
        dive.resolve();
      }
      if (dragId !== null) {
        finishDrag(false);
      }
      // The section outlives a re-mount (a reduced-motion change): drop the grab cursor.
      delete cssTarget.dataset.heroDrag;
      stop();
      lifetime.abort();
      window.clearTimeout(contextTimer);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      timer.dispose();

      scene.remove(heroRoot);
      satellite?.dispose();
      starfield.dispose();
      atmosphere.geometry.dispose();
      (atmosphere.material as ShaderMaterial).dispose();
      for (const texture of ownedTextures) {
        texture.dispose();
      }
      earthMaterial.dispose();
      bloomPass?.dispose();
      outputPass?.dispose();

      globe._destructor();
      renderer.forceContextLoss();
      container.replaceChildren();
      // three-render-objects publishes its scene on window for debugging; drop our reference.
      const debugWindow = window as unknown as { scene?: unknown };
      if (debugWindow.scene === scene) {
        delete debugWindow.scene;
      }
      if (import.meta.env.DEV) {
        delete (window as HeroQAWindow).__heroQA;
      }
    },
  };
}
