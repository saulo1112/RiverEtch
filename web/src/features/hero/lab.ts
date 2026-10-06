// `?lab=satellite`: the satellite alone with orbit controls, for close inspection. It reuses the
// hero's satellite rig (materials, environment, lights and shoulder) but never loads globe.gl.
import {
  ACESFilmicToneMapping,
  MathUtils,
  PerspectiveCamera,
  Scene,
  Timer,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import { QUALITY_PRESETS, SATELLITE, type QualityName } from "./config.ts";
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
 * the pass over Colombia, `spin=1` runs the real orbit, `px=<n>` frames the span at n pixels.
 *
 * @param container - Element that receives the canvas.
 * @param options - Quality and lifecycle callback.
 * @returns A function that tears the lab down.
 */
export function mountSatelliteLab(
  container: HTMLElement,
  options: SatelliteLabOptions,
): () => void {
  const params = new URLSearchParams(window.location.search);
  const frozenAngleDeg = params.has("u") ? Number(params.get("u")) : 0;
  const spin = params.get("spin") === "1";
  const spanPx = params.has("px") ? Number(params.get("px")) : null;
  // Initial camera offset in the satellite's frame (X wings, Y zenith, Z flight direction).
  const cameraParam = (params.get("cam") ?? "14,8,22").split(",").map(Number);

  const renderer = new WebGLRenderer({ antialias: true, alpha: true });
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.setPixelRatio(
    Math.min(window.devicePixelRatio, QUALITY_PRESETS[options.quality].dprCap),
  );
  renderer.setClearColor(0x000000, 0);
  container.replaceChildren(renderer.domElement);

  const scene = new Scene();
  const camera = new PerspectiveCamera(35, 1, 0.1, 2000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.minDistance = 8;
  controls.maxDistance = 90;

  const timer = new Timer();
  timer.connect(document);
  let satellite: SatelliteRig | null = null;
  let rafId = 0;
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
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.getDrawingBufferSize(drawingBuffer);
    satellite?.setFraming(
      camera.position,
      height,
      camera.fov,
      drawingBuffer,
      renderer.getPixelRatio(),
    );
    if (satellite !== null) {
      satellite.state.scale = 1;
    }
    if (spanPx !== null && satellite !== null) {
      // Distance at which the span covers `spanPx` pixels.
      const pixelsPerUnitAtOne = height / (2 * Math.tan(MathUtils.degToRad(camera.fov / 2)));
      const distance = (SATELLITE.spanUnits * pixelsPerUnitAtOne) / spanPx;
      offset.setLength(distance);
    }
  }

  function frame(timestamp: number): void {
    rafId = requestAnimationFrame(frame);
    timer.update(timestamp);
    const dt = Math.min(timer.getDelta(), 1 / 30);
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
    renderer.render(scene, camera);
    if (!readyNotified) {
      readyNotified = true;
      options.onReady();
    }
  }

  const observer = new ResizeObserver(resize);
  observer.observe(container);

  void createSatellite(renderer, QUALITY_PRESETS[options.quality]).then((rig) => {
    if (disposed) {
      rig.dispose();
      return;
    }
    satellite = rig;
    rig.state.scale = 1;
    scene.add(...rig.objects);
    resize();
    rafId = requestAnimationFrame(frame);
  });

  return () => {
    disposed = true;
    cancelAnimationFrame(rafId);
    observer.disconnect();
    controls.dispose();
    timer.dispose();
    satellite?.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    container.replaceChildren();
  };
}
