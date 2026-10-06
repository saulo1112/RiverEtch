// Mounts the hero scene: globe.gl renders the Earth, but this module owns the frame loop, the
// camera and every extra object, and tears everything down without leaking WebGL contexts.
import Globe, { type GlobeInstance } from "globe.gl";
import {
  ACESFilmicToneMapping,
  Group,
  MeshBasicMaterial,
  PerspectiveCamera,
  Timer,
  Vector3,
  type Texture,
} from "three";

import { COLOMBIA_DIRECTION, latLngToVector3 } from "./colombia.ts";
import { CAMERA, GEO, GLOBE_RADIUS, QUALITY_PRESETS, type QualityName } from "./config.ts";
import { createFallbackEarthTexture, loadColorTexture } from "./textures.ts";

/** Options for {@link mountHero}. */
export interface MountHeroOptions {
  /** Rendering quality preset. */
  readonly quality: QualityName;
  /** Render a single still frame instead of animating. */
  readonly reducedMotion: boolean;
  /** Scene time to freeze at (development QA), or null to animate normally. */
  readonly frozenTime: number | null;
  /** Called once the first frame with the Earth texture has been rendered. */
  readonly onReady: () => void;
  /** Called when WebGL fails after mounting; the caller should show the fallback. */
  readonly onError: (error: unknown) => void;
}

/** Handle returned by {@link mountHero}. */
export interface HeroHandle {
  /** Stops the scene and releases every GPU resource; safe to call more than once. */
  readonly dispose: () => void;
}

interface HeroQAWindow extends Window {
  __heroQA?: { readonly stats: () => Record<string, unknown> };
}

// Scratch objects reused every frame.
const cameraPosition = new Vector3();
const lookTarget = new Vector3();
const projected = new Vector3();

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
  const lifetime = new AbortController();
  const { signal } = lifetime;

  let globe: GlobeInstance;
  try {
    globe = new Globe(container, {
      animateIn: false,
      waitForGlobeReady: false,
      rendererConfig: {
        antialias: true,
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

  const earthMaterial = new MeshBasicMaterial({ color: 0x0b2047 });
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
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1;
  const pixelRatio = Math.min(window.devicePixelRatio, preset.dprCap);
  renderer.setPixelRatio(pixelRatio);
  const composer = globe.postProcessingComposer();
  composer.setPixelRatio(pixelRatio);

  const camera = globe.camera() as PerspectiveCamera;
  camera.up.set(0, 1, 0);

  const scene = globe.scene();
  const heroRoot = new Group();
  heroRoot.name = "heroRoot";
  scene.add(heroRoot);

  let earthTexture: Texture | null = null;
  let cameraDistance = 335;
  let rafId = 0;
  let running = false;
  let readyNotified = false;
  let disposed = false;
  const timer = new Timer();
  timer.connect(document);

  // View-offset shift (px) that moves the globe center to its configured screen position.
  const viewShift = { x: 0, y: 0, width: 1, height: 1 };

  function layout(): void {
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    globe.width(width).height(height);

    const aspect = width / height;
    camera.aspect = aspect;
    // Fit the globe disc to the viewport height, but never wider than the viewport.
    const tanHalfFov = Math.tan(((CAMERA.fovDeg / 2) * Math.PI) / 180);
    const tanAngular = Math.min(CAMERA.discFraction * tanHalfFov, 0.88 * tanHalfFov * aspect);
    cameraDistance = GLOBE_RADIUS / Math.sin(Math.atan(tanAngular));

    // Project the globe center without any offset, then shift the view so it lands on the goal.
    poseCamera();
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
  }

  function poseCamera(): void {
    latLngToVector3(
      CAMERA.viewLatDeg,
      GEO.colombiaCentroid.lng + CAMERA.viewLngOffsetDeg,
      cameraDistance,
      cameraPosition,
    );
    lookTarget.copy(COLOMBIA_DIRECTION).multiplyScalar(CAMERA.targetFactor * GLOBE_RADIUS);
    camera.position.copy(cameraPosition);
    camera.lookAt(lookTarget);
  }

  // globe.gl's debounced digests reset `far` (from its sky radius) and clear the view offset;
  // restore ours before every render.
  function syncProjection(): void {
    const view = camera.view;
    const viewMatches =
      view !== null &&
      view.enabled &&
      view.offsetX === viewShift.x &&
      view.offsetY === viewShift.y &&
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
      viewShift.x,
      viewShift.y,
      viewShift.width,
      viewShift.height,
    );
  }

  function renderFrame(timestamp: number | undefined): void {
    timer.update(timestamp);
    const dt = Math.min(timer.getDelta(), 1 / 30);
    syncProjection();
    poseCamera();
    composer.render(dt);
    if (!readyNotified && earthTexture !== null) {
      readyNotified = true;
      options.onReady();
    }
  }

  function tick(timestamp: number): void {
    rafId = requestAnimationFrame(tick);
    renderFrame(timestamp);
  }

  function start(): void {
    if (running || disposed || options.reducedMotion || options.frozenTime !== null) {
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
        if (!disposed) {
          renderFrame(undefined);
        }
      });
    });
  }

  const resizeObserver = new ResizeObserver(() => {
    layout();
    if (!running) {
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

  void (async () => {
    let texture: Texture;
    try {
      texture = await loadColorTexture(preset.earthTexture, renderer, signal);
    } catch (error) {
      if (signal.aborted) {
        return;
      }
      if (import.meta.env.DEV) {
        console.warn(
          `[hero] Could not load textures/${preset.earthTexture}; using a procedural placeholder.`,
          error,
        );
      }
      texture = createFallbackEarthTexture();
    }
    earthTexture = texture;
    earthMaterial.map = texture;
    earthMaterial.color.set(0xffffff);
    earthMaterial.needsUpdate = true;
    if (document.hidden || options.reducedMotion || options.frozenTime !== null) {
      renderStill();
    } else {
      start();
    }
  })();

  if (import.meta.env.DEV) {
    // Development-only QA hook for headless screenshots (see the PR description).
    (window as HeroQAWindow).__heroQA = {
      stats: () => {
        camera.updateMatrixWorld();
        projected.set(0, 0, 0).project(camera);
        return {
          viewport: [container.clientWidth, container.clientHeight],
          viewShift: { ...viewShift },
          globeCenterPx: [
            ((projected.x + 1) / 2) * container.clientWidth,
            ((1 - projected.y) / 2) * container.clientHeight,
          ],
          cameraDistance,
          aspect: camera.aspect,
          view: camera.view,
          renderSize: [renderer.domElement.width, renderer.domElement.height],
        };
      },
    };
  }

  return {
    dispose(): void {
      if (disposed) {
        return;
      }
      disposed = true;
      stop();
      lifetime.abort();
      resizeObserver.disconnect();
      timer.dispose();

      scene.remove(heroRoot);
      earthTexture?.dispose();
      earthMaterial.dispose();

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
