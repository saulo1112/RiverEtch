// `?lab=satellite`: the satellite alone with orbit controls, for close inspection. It reuses the
// hero's satellite rig (materials, environment, lights, shoulder) and the same bloom chain, but
// never loads globe.gl.
import {
  ACESFilmicToneMapping,
  HalfFloatType,
  MathUtils,
  PerspectiveCamera,
  Scene,
  Timer,
  Vector2,
  Vector3,
  WebGLRenderer,
  WebGLRenderTarget,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

import { POST, QUALITY_PRESETS, SATELLITE, type QualityName } from "./config.ts";
import { createSatellite, timeForOrbitOffset, type SatelliteRig } from "./satellite.ts";

/** Options for {@link mountSatelliteLab}. */
export interface SatelliteLabOptions {
  /** Rendering quality preset. */
  readonly quality: QualityName;
  /** Called once the first frame has been rendered. */
  readonly onReady: () => void;
}

/**
 * Mounts the satellite inspection lab. URL flags: `u=<deg>` freezes the orbit angle relative to
 * the pass, `spin=1` runs the real orbit, `px=<n>` frames the span at n pixels,
 * `cam=x,y,z` sets the initial camera offset in the satellite's frame.
 *
 * @param container - Element that receives the canvas.
 * @param options - Quality and lifecycle callback.
 * @returns A function that tears the lab down.
 */
export function mountSatelliteLab(
  container: HTMLElement,
  options: SatelliteLabOptions,
): () => void {
  const preset = QUALITY_PRESETS[options.quality];
  const params = new URLSearchParams(window.location.search);
  const frozenAngleDeg = params.has("u") ? Number(params.get("u")) : 0;
  const spin = params.get("spin") === "1";
  const spanPx = params.has("px") ? Number(params.get("px")) : null;
  // Initial camera offset in the satellite's frame (X wings, Y zenith, Z flight direction).
  const cameraParam = (params.get("cam") ?? "14,8,22").split(",").map(Number);
  const lifetime = new AbortController();

  const renderer = new WebGLRenderer({ antialias: !preset.bloom, alpha: true });
  renderer.toneMapping = ACESFilmicToneMapping;
  const pixelRatio = Math.min(window.devicePixelRatio, preset.dprCap);
  renderer.setPixelRatio(pixelRatio);
  renderer.setClearColor(0x000000, 0);
  container.replaceChildren(renderer.domElement);

  const scene = new Scene();
  const camera = new PerspectiveCamera(35, 1, 0.1, 2000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.minDistance = 8;
  controls.maxDistance = 90;

  // Same post chain as the hero's high preset.
  const composer = preset.bloom
    ? new EffectComposer(
        renderer,
        new WebGLRenderTarget(1, 1, {
          type: HalfFloatType,
          samples: pixelRatio < 1.25 ? 4 : pixelRatio < 1.75 ? 2 : 0,
        }),
      )
    : null;
  const { strength, radius, threshold } = POST.bloom;
  const passes =
    composer === null
      ? []
      : [
          new RenderPass(scene, camera),
          new UnrealBloomPass(new Vector2(1, 1), strength, radius, threshold),
          new OutputPass(),
        ];
  for (const pass of passes) {
    composer?.addPass(pass);
  }

  const timer = new Timer();
  timer.connect(document);
  let satellite: SatelliteRig | null = null;
  let rafId = 0;
  let running = false;
  let disposed = false;
  let readyNotified = false;
  let time = 0;
  const offset = new Vector3(cameraParam[0] ?? 14, cameraParam[1] ?? 8, cameraParam[2] ?? 22);
  const previousTarget = new Vector3();
  const drawingBuffer = new Vector2();

  const frozenTime = timeForOrbitOffset(MathUtils.degToRad(frozenAngleDeg));

  function resize(): void {
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    renderer.setSize(width, height, false);
    composer?.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.getDrawingBufferSize(drawingBuffer);
    if (satellite === null) {
      return;
    }
    satellite.setFraming(camera.position, height, camera.fov, drawingBuffer, pixelRatio);
    // The lab shows the model at its natural size.
    satellite.state.scale = 1;
    if (spanPx !== null) {
      // Distance at which the span covers `spanPx` pixels.
      const pixelsPerUnitAtOne = height / (2 * Math.tan(MathUtils.degToRad(camera.fov / 2)));
      const distance = (SATELLITE.spanUnits * pixelsPerUnitAtOne) / spanPx;
      offset.setLength(distance);
      controls.maxDistance = Math.max(controls.maxDistance, distance * 1.5);
    }
  }

  function frame(timestamp: number): void {
    rafId = requestAnimationFrame(frame);
    timer.update(timestamp);
    const dt = MathUtils.clamp(timer.getDelta(), 0, 1 / 30);
    time = spin ? time + dt : frozenTime;
    if (satellite === null) {
      return;
    }
    satellite.update(time, dt, camera.position);
    // Keep the camera's offset from the satellite while it moves along the orbit.
    const target = satellite.state.position;
    if (previousTarget.lengthSq() === 0) {
      camera.position.copy(offset).applyQuaternion(satellite.state.attitude).add(target);
    } else {
      camera.position.add(target).sub(previousTarget);
    }
    previousTarget.copy(target);
    controls.target.copy(target);
    controls.update(dt);
    if (composer === null) {
      renderer.render(scene, camera);
    } else {
      composer.render(dt);
    }
    if (!readyNotified) {
      readyNotified = true;
      options.onReady();
    }
  }

  function start(): void {
    if (running || disposed || satellite === null || document.hidden) {
      return;
    }
    running = true;
    timer.reset();
    rafId = requestAnimationFrame(frame);
  }

  function stop(): void {
    running = false;
    cancelAnimationFrame(rafId);
  }

  document.addEventListener(
    "visibilitychange",
    () => {
      if (document.hidden) {
        stop();
      } else {
        start();
      }
    },
    { signal: lifetime.signal },
  );

  const observer = new ResizeObserver(resize);
  observer.observe(container);

  createSatellite(renderer, preset, lifetime.signal)
    .then((rig) => {
      if (disposed) {
        rig.dispose();
        return;
      }
      satellite = rig;
      rig.state.scale = 1;
      scene.add(...rig.objects);
      resize();
      start();
    })
    .catch((error: unknown) => {
      if (!disposed && import.meta.env.DEV) {
        console.error("[hero] Could not build the satellite lab.", error);
      }
    });

  return () => {
    disposed = true;
    stop();
    lifetime.abort();
    observer.disconnect();
    controls.dispose();
    timer.dispose();
    satellite?.dispose();
    for (const pass of passes) {
      pass.dispose();
    }
    composer?.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    container.replaceChildren();
  };
}
