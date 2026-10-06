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
  type Texture,
} from "three";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

import { cubicBezier } from "../../lib/easing.ts";
import { COLOMBIA_DIRECTION, COLOMBIA_RINGS, latLngToVector3 } from "./colombia.ts";
import {
  ATMOSPHERE,
  CAMERA,
  DIVE,
  EARTH,
  EARTH_NIGHT_TEXTURE,
  EARTH_WATER_TEXTURE,
  GEO,
  GLOBE_RADIUS,
  POST,
  QUALITY_PRESETS,
  SCAN,
  SUN,
  type HeroEffect,
  type QualityName,
} from "./config.ts";
import { divePose, handoffFrame } from "./dive.ts";
import { createSatellite, timeForOrbitOffset, type SatelliteRig } from "./satellite.ts";
import { createScan, type ScanEffect } from "./scan.ts";
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

/** Handle returned by {@link mountHero}. */
export interface HeroHandle {
  /**
   * Flies the camera from its current pose down to a top-down, north-up view of a site, centered
   * (the globe's off-center framing blends out), while the satellite, orbit, scan overlays and
   * atmosphere fade away and the parallax and drift stop. The camera then holds that pose.
   *
   * @param target - Site and handoff zoom.
   * @param options - Duration and a progress callback.
   * @returns The running dive.
   */
  readonly dive: (target: DiveTarget, options?: DiveOptions) => DiveHandle;
  /** Stops the scene and releases every GPU resource; safe to call more than once. */
  readonly dispose: () => void;
}

interface HeroQAWindow extends Window {
  __heroQA?: {
    readonly stats: () => Record<string, unknown>;
    readonly simulate: (fromS: number, toS: number, stepS: number) => unknown[];
    readonly project: (lat: number, lng: number) => [number, number];
    readonly dive: (target: DiveTarget, options?: DiveOptions) => DiveHandle;
  };
}

interface DiveState {
  readonly fromPosition: Vector3;
  readonly fromTarget: Vector3;
  readonly site: Vector3;
  readonly lat: number;
  readonly zoom: number;
  readonly durationS: number;
  readonly onProgress: ((progress: number) => void) | undefined;
  elapsedS: number;
  settled: boolean;
  readonly resolve: () => void;
}

// Unit vector from the Earth towards the sun (world space, fixed).
const SUN_DIRECTION: Readonly<Vector3> = new Vector3(...SUN.dir).normalize();

// Scratch objects reused every frame.
const cameraPosition = new Vector3();
const lookTarget = new Vector3();
const projected = new Vector3();
const settledCamera = new Vector3();
const drawingBuffer = new Vector2();

const easeOutCubic = (t: number) => 1 - (1 - t) ** 3;
const easeOutQuart = (t: number) => 1 - (1 - t) ** 4;
const easeInOutCubic = (t: number) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);
const diveEase = cubicBezier(...DIVE.ease);

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
uniform vec3 uFocusDirection;
uniform float uFocusVignette;
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

  // Keep the eye on Colombia.
  color *= mix(uFocusVignette, 1.0, smoothstep(0.55, 0.85, dot(normal, uFocusDirection)));
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
      uFocusDirection: { value: COLOMBIA_DIRECTION },
      uFocusVignette: { value: EARTH.focusVignette },
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

  const earthUniforms = earthMaterial.uniforms as {
    uDayMap: { value: Texture | null };
    uWaterMask: { value: Texture | null };
    uNightMap: { value: Texture | null };
    uNightLights: { value: number };
  };
  const ownedTextures = new Set<Texture>();
  let satellite: SatelliteRig | null = null;
  let scan: ScanEffect | null = null;

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
  // Reduced motion shows one settled frame near the scan climax (intro finished, no drift).
  const stillTime = Math.max(timeForOrbitOffset(SCAN.stillOffsetRad), CAMERA.intro.durationS);

  // View-offset shift (px) that moves the globe center to its configured screen position.
  const viewShift = { x: 0, y: 0, width: 1, height: 1 };
  // Share of that shift in use: 1 normally, blended to 0 (centered) by the dive.
  let viewBlend = 1;
  let dive: DiveState | null = null;
  // Opacity of the satellite, orbit, scan overlays and atmosphere (the dive fades them out).
  let overlayFade = 1;

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

    // Project the globe center from the settled pose, then shift the view so it lands on the goal.
    poseCamera(Number.POSITIVE_INFINITY, false);
    settledCamera.copy(camera.position);
    camera.near = CAMERA.near;
    camera.far = CAMERA.far;
    camera.fov = CAMERA.fovDeg;
    camera.clearViewOffset();
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    projected.set(0, 0, 0).project(camera);
    const goal = aspect >= 1 ? CAMERA.globeCenterDesktop : CAMERA.globeCenterPortrait;
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
    scan?.setResolution(Math.max(1, container.clientWidth), height);
  }

  // Places the camera for scene time `timeS`; `withMotion` adds parallax and drift.
  function poseCamera(timeS: number, withMotion: boolean): void {
    const { intro, parallax, drift } = CAMERA;
    const progress = MathUtils.clamp(timeS / intro.durationS, 0, 1);
    const dolly = easeInOutCubic(progress);
    const push = withMotion ? SCAN.cameraPush * (scan?.status.push ?? 0) : 0;
    const distance =
      baseDistance * (1 + intro.distanceGain * (1 - easeOutQuart(progress))) * (1 - push);
    let lat = CAMERA.viewLatDeg * widthWeight - intro.latDeg * (1 - easeOutCubic(progress));
    let lng =
      GEO.colombiaCentroid.lng + CAMERA.viewLngOffsetDeg * widthWeight + intro.lngDeg * (1 - dolly);
    if (withMotion) {
      lng += pointer.x * parallax.lngDeg * dolly;
      lat -= pointer.y * parallax.latDeg * dolly;
      lat += drift.latDeg * Math.sin((2 * Math.PI * timeS) / drift.latPeriodS);
      lng += drift.lngDeg * Math.sin((2 * Math.PI * timeS) / drift.lngPeriodS + 1.1);
    }
    latLngToVector3(lat, lng, distance, cameraPosition);
    lookTarget
      .copy(COLOMBIA_DIRECTION)
      .multiplyScalar(CAMERA.targetFactor * widthWeight * dolly * GLOBE_RADIUS);
    camera.position.copy(cameraPosition);
    camera.lookAt(lookTarget);
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
    scan?.setFade(alpha);
  }

  // Advances the dive by `frameS` seconds of wall-clock time and poses the camera.
  function advanceDive(state: DiveState, frameS: number): void {
    if (!state.settled) {
      state.elapsedS = Math.min(state.durationS, state.elapsedS + frameS);
    }
    const progress = state.durationS > 0 ? state.elapsedS / state.durationS : 1;
    const k = diveEase(progress);
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
    viewBlend = 1 - k;
    setOverlayFade(1 - MathUtils.smoothstep(progress, 0, DIVE.fadeEnd));
    earthGlint.y = earthGlintGain * (1 - MathUtils.smoothstep(progress, ...DIVE.glintFade));
    if (!state.settled) {
      state.onProgress?.(progress);
      if (progress >= 1) {
        state.settled = true;
        state.resolve();
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

    if (!options.reducedMotion && dive === null) {
      const damping = CAMERA.parallax.damping;
      pointer.x = MathUtils.damp(pointer.x, pointerTarget.x, damping, dt);
      pointer.y = MathUtils.damp(pointer.y, pointerTarget.y, damping, dt);
      writeCssParallax();
      renderer.toneMappingExposure = easeOutCubic(
        MathUtils.clamp(sceneTime / CAMERA.intro.exposureS, 0, 1),
      );
    }

    if (dive === null) {
      poseCamera(sceneTime, !options.reducedMotion);
    } else {
      advanceDive(dive, frameS);
    }
    syncProjection();
    starfield.update(sceneTime);
    renderer.info.reset();
    if (satellite !== null) {
      satellite.update(sceneTime, dt, camera.position, options.reducedMotion);
      if (!animate) {
        scan?.snap(options.reducedMotion);
      }
      scan?.update(sceneTime, dt, satellite.state);
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
        // Touch and pen drags scroll the page; only a hovering mouse steers the parallax.
        if (event.pointerType !== "mouse") {
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

  function adopt(texture: Texture): Texture {
    ownedTextures.add(texture);
    return texture;
  }

  async function loadSurface(): Promise<void> {
    const [day, water, rig, effect] = await Promise.allSettled([
      loadTexture(preset.earthTexture, renderer, signal, "color"),
      loadTexture(EARTH_WATER_TEXTURE, renderer, signal, "data"),
      createSatellite(renderer, preset, signal, disabledEffects),
      createScan(preset, signal, disabledEffects),
    ]);
    if (signal.aborted) {
      for (const result of [day, water, rig, effect]) {
        if (result.status === "fulfilled") {
          result.value.dispose();
        }
      }
      return;
    }
    if (effect.status === "fulfilled") {
      scan = effect.value;
      heroRoot.add(...scan.objects);
      if (overlayFade < 1) {
        scan.setFade(overlayFade);
      }
    } else if (import.meta.env.DEV) {
      console.error("[hero] Could not build the scan effect.", effect.reason);
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

    // Compile every program up front, so the first pass over Colombia does not hitch.
    try {
      await renderer.compileAsync(scene, camera);
    } catch {
      // Compilation errors surface again on the first render; nothing to do here.
    }
    if (disposed) {
      return;
    }

    started = true;
    if (animate) {
      start();
    } else {
      renderStill();
    }
    void loadDetailTexture();
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
    // Start from exactly the pose of the last frame (motion included).
    if (dive === null) {
      poseCamera(sceneTime, !options.reducedMotion);
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
    const state: DiveState = {
      fromPosition: camera.position.clone(),
      fromTarget: lookTarget.clone(),
      site: latLngToVector3(target.lat, target.lng, 1, new Vector3()),
      lat: target.lat,
      zoom: target.zoom,
      durationS: Math.max(0, diveOptions.durationS ?? DIVE.durationS),
      onProgress: diveOptions.onProgress,
      elapsedS: 0,
      settled: false,
      resolve: () => {
        resolveDone?.();
      },
    };
    dive = state;
    if (disposed || !started || document.hidden || !onScreen || contextLost) {
      // Nothing renders (still loading, hidden, off-screen or without a context), so the dive
      // could not progress: it settles at once.
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
        // Wingtip to wingtip on screen, and Colombia's on-screen bounding box.
        let satelliteSpanPx: number | null = null;
        if (satellite !== null) {
          const { position, attitude, scale } = satellite.state;
          const half = new Vector3(1, 0, 0).applyQuaternion(attitude).multiplyScalar(12 * scale);
          const [ax, ay] = toPixels(position.clone().add(half));
          const [bx, by] = toPixels(position.clone().sub(half));
          satelliteSpanPx = Math.hypot(ax - bx, ay - by);
        }
        let minX = Number.POSITIVE_INFINITY;
        let maxX = Number.NEGATIVE_INFINITY;
        let minY = Number.POSITIVE_INFINITY;
        let maxY = Number.NEGATIVE_INFINITY;
        for (const ring of COLOMBIA_RINGS) {
          for (const [lng, lat] of ring) {
            const [x, y] = toPixels(latLngToVector3(lat, lng, GLOBE_RADIUS, new Vector3()));
            minX = Math.min(minX, x);
            maxX = Math.max(maxX, x);
            minY = Math.min(minY, y);
            maxY = Math.max(maxY, y);
          }
        }
        projected.set(0, 0, 0).project(camera);
        return {
          satelliteSpanPx,
          colombiaBoxPx: [maxX - minX, maxY - minY],
          sceneTime,
          viewport: [container.clientWidth, container.clientHeight],
          globeCenterPx: [
            ((projected.x + 1) / 2) * container.clientWidth,
            ((1 - projected.y) / 2) * container.clientHeight,
          ],
          baseDistance,
          satelliteScale: satellite?.state.scale ?? null,
          glint: satellite?.state.glint ?? null,
          scanPhase: scan?.status.phase ?? null,
          scanIntensity: scan?.status.intensity ?? null,
          satelliteAngleDeg: satellite === null ? null : MathUtils.radToDeg(satellite.state.angle),
          exposure: renderer.toneMappingExposure,
          diveProgress: dive === null ? null : dive.elapsedS / Math.max(1e-6, dive.durationS),
          overlayFade,
          viewBlend,
          cameraAltitude: camera.position.length() - GLOBE_RADIUS,
          drawCalls: renderer.info.render.calls,
          triangles: renderer.info.render.triangles,
        };
      },
      // Runs the satellite and the scan state machine over a time range without rendering, and
      // returns the phase transitions (headless browsers render too slowly to watch a full orbit).
      simulate: (fromS, toS, stepS) => {
        const transitions: unknown[] = [];
        if (satellite === null || scan === null) {
          return transitions;
        }
        let previous = "";
        for (let t = fromS; t <= toS; t += stepS) {
          satellite.update(t, stepS, camera.position);
          scan.update(t, stepS, satellite.state);
          if (satellite.state.glint > 0.05) {
            transitions.push([
              Number(t.toFixed(2)),
              "glint",
              Number(satellite.state.glint.toFixed(3)),
            ]);
          }
          if (scan.status.phase !== previous) {
            previous = scan.status.phase;
            transitions.push([
              Number(t.toFixed(2)),
              previous,
              Number(scan.status.intensity.toFixed(3)),
            ]);
          }
        }
        return transitions;
      },
      dive: startDive,
      // Screen position (CSS px) of a geographic point with the current camera.
      project: (lat, lng) => {
        camera.updateMatrixWorld();
        projected.copy(latLngToVector3(lat, lng, GLOBE_RADIUS, new Vector3())).project(camera);
        return [
          ((projected.x + 1) / 2) * container.clientWidth,
          ((1 - projected.y) / 2) * container.clientHeight,
        ];
      },
    };
  }

  return {
    dive: startDive,
    dispose(): void {
      if (disposed) {
        return;
      }
      disposed = true;
      if (dive !== null && !dive.settled) {
        dive.settled = true;
        dive.resolve();
      }
      stop();
      lifetime.abort();
      window.clearTimeout(contextTimer);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      timer.dispose();

      scene.remove(heroRoot);
      scan?.dispose();
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
