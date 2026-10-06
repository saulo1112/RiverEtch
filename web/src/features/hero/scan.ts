// Colombia scan effect. As the satellite passes overhead, its sensor beam lands on the country, a
// push-broom line sweeps across it, the border glows and rings pulse out from the centroid. An
// illustrative turbidity heat map along the main rivers can be revealed behind the push-broom line
// (SCAN.heat.visible, off in the hero for now). Driven by a small state machine.
import {
  AdditiveBlending,
  Color,
  ConeGeometry,
  DoubleSide,
  MathUtils,
  Mesh,
  NormalBlending,
  PlaneGeometry,
  BufferGeometry,
  Float32BufferAttribute,
  ShaderMaterial,
  Vector2,
  Vector3,
  Vector4,
  type DataTexture,
  type Object3D,
} from "three";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";

import { COLOMBIA_DIRECTION, COLOMBIA_RINGS, latLngToVector3 } from "./colombia.ts";
import { GEO, GLOBE_RADIUS, SCAN, type HeroEffect, type QualityPreset } from "./config.ts";
import {
  COLOMBIA_ORBIT_ANGLE,
  ORBIT_NODE,
  ORBIT_NORMAL,
  ORBIT_QUADRATURE,
  orbitVelocityDirection,
  type SatelliteState,
} from "./satellite.ts";
import { createColombiaDataTexture } from "./textures.ts";

/** Phase of a pass over Colombia. */
export type ScanPhase = "idle" | "approach" | "scan" | "leave";

/** The scan effect and its per-frame hooks. */
export interface ScanEffect {
  /** Meshes to add to the scene. */
  readonly objects: readonly Object3D[];
  /** Current phase and intensity, for the camera push-in and QA. */
  readonly status: {
    phase: ScanPhase;
    intensity: number;
    /** Damped 0..1 while scanning, used for the camera push-in. */
    push: number;
  };
  /**
   * Advances the state machine and every overlay.
   *
   * @param timeS - Scene time in seconds.
   * @param dt - Frame time in seconds (already clamped).
   * @param satellite - Live satellite state.
   */
  readonly update: (timeS: number, dt: number, satellite: SatelliteState) => void;
  /**
   * Jumps every damped value to its target (first frame, frozen time, reduced motion).
   *
   * @param still - Also show the "settled" look used for the reduced-motion still.
   */
  readonly snap: (still: boolean) => void;
  /**
   * Keeps line widths in CSS pixels.
   *
   * @param width - Viewport width in CSS pixels.
   * @param height - Viewport height in CSS pixels.
   */
  readonly setResolution: (width: number, height: number) => void;
  /** Releases geometries, materials and the data texture. */
  readonly dispose: () => void;
}

const TAU = Math.PI * 2;

interface Uniform<T> {
  value: T;
}

const WRAP_PI_GLSL = /* glsl */ `
float wrapPi(float angle) {
  return angle - 6.2831853 * floor((angle + 3.14159265) / 6.2831853);
}
`;

// ---------------------------------------------------------------------------------------------
// Beam: an open cone from the aperture to just below the surface, with bands travelling from the
// ground up to the sensor.

const beamVertexShader = /* glsl */ `
varying float vAlong;
varying vec3 vNormalView;
varying vec3 vViewDirection;

void main() {
  vAlong = -position.y; // 0 at the aperture, 1 at the base
  vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
  vNormalView = normalize(normalMatrix * normal);
  vViewDirection = normalize(-viewPosition.xyz);
  gl_Position = projectionMatrix * viewPosition;
}
`;

const beamFragmentShader = /* glsl */ `
#include <common>

uniform vec3 uColor;
uniform float uIntensity;
uniform float uLength;
uniform float uTime;
uniform vec4 uShape; // body gain, aperture hot spot, stripe length, stripe speed

varying float vAlong;
varying vec3 vNormalView;
varying vec3 vViewDirection;

void main() {
  // MSAA shades a partly covered pixel at its centre, which can lie well outside the cone's thin
  // triangles near the apex. There vAlong is extrapolated far below 0 and the hot spot's exp()
  // overflows to +Inf; the bloom then spreads that one pixel over the frame as a flash. Clamp it.
  float along = clamp(vAlong, 0.0, 1.0);
  float facing = pow(abs(dot(normalize(vNormalView), normalize(vViewDirection))), 1.3);
  float body = mix(1.0, 0.35, smoothstep(0.0, 0.6, along)) + 0.35 * smoothstep(0.82, 1.0, along);
  float wave = 0.5 + 0.5 * sin(6.2831853 * (along * uLength / uShape.z + uTime * uShape.w));
  float stripe = 0.68 + 0.32 * smoothstep(0.55, 1.0, wave);
  float hot = uShape.y * exp(-along * uLength / 0.9);
  vec3 color = uColor * (uShape.x * body * stripe * facing + hot) * uIntensity;
  gl_FragColor = vec4(color, max(color.r, max(color.g, color.b)));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

// ---------------------------------------------------------------------------------------------
// Footprint: an ellipse on the ground under the satellite, with the push-broom acquisition line.

const footprintVertexShader = /* glsl */ `
uniform vec3 uCenter;
uniform vec3 uCrossTrack;
uniform vec3 uAlongTrack;
uniform vec2 uSemiAxes;
uniform float uRadius;

varying vec2 vPlane;

void main() {
  vPlane = position.xy;
  vec3 direction = normalize(
    uCenter + position.x * uSemiAxes.x * uCrossTrack + position.y * uSemiAxes.y * uAlongTrack
  );
  gl_Position = projectionMatrix * viewMatrix * vec4(direction * uRadius, 1.0);
}
`;

const footprintFragmentShader = /* glsl */ `
#include <common>

uniform vec3 uColor;
uniform float uIntensity;

varying vec2 vPlane;

void main() {
  float radius = length(vPlane);
  float radiusWidth = fwidth(radius);
  float rim = 1.0 - smoothstep(0.0, 1.5 * radiusWidth, abs(radius - 1.0));
  float inside = 1.0 - smoothstep(1.0 - radiusWidth, 1.0 + radiusWidth, radius);
  float lineWidth = fwidth(vPlane.y);
  float scanLine = (1.0 - smoothstep(0.0, 1.5 * lineWidth + 0.015, abs(vPlane.y))) * inside;
  // Fading wake behind the satellite, as wide as the swath.
  float swath = 1.0 - smoothstep(0.85, 1.0, abs(vPlane.x));
  float wake = step(vPlane.y, 0.0) * exp(vPlane.y / 0.9) * swath * (1.0 - inside * 0.6);
  // Cross-track ticks along the acquisition line.
  float tick = 1.0 - smoothstep(0.0, 1.5 * fwidth(vPlane.x * 8.0), abs(fract(vPlane.x * 4.0 + 0.5) - 0.5));
  float ticks = tick * (1.0 - smoothstep(0.0, 0.08, abs(vPlane.y))) * inside;
  float energy = 0.45 * rim + 1.3 * scanLine + 0.22 * wake + 0.08 * inside + 0.6 * ticks;
  vec3 color = uColor * energy * uIntensity;
  gl_FragColor = vec4(color, max(color.r, max(color.g, color.b)));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

// ---------------------------------------------------------------------------------------------
// Colombia patch: cap, edge glow and the heat map in one draw, over a lat/lng grid.

const patchVertexShader = /* glsl */ `
varying vec2 vUv;
varying vec3 vPositionWorld;

void main() {
  vUv = uv;
  vec4 world = modelMatrix * vec4(position, 1.0);
  vPositionWorld = world.xyz;
  gl_Position = projectionMatrix * viewMatrix * world;
}
`;

const patchFragmentShader = /* glsl */ `
#include <common>

uniform sampler2D uData; // R mask, G heat, B edge glow, A rivers
uniform vec3 uCyan;
uniform vec3 uRamp[5];
uniform vec3 uContourColor;
uniform float uIntensity;
uniform float uHeat; // 0 hides the heat map (cap, glow and rivers stay)
uniform float uCap;
uniform float uOld;
uniform float uFront;
uniform float uSweep;
uniform vec3 uOrbitNode;
uniform vec3 uOrbitQuadrature;
uniform float uColombiaAngle;

varying vec2 vUv;
varying vec3 vPositionWorld;

${WRAP_PI_GLSL}

vec3 heatRamp(float h) {
  float x = clamp(h, 0.0, 1.0) * 4.0;
  vec3 color = mix(uRamp[0], uRamp[1], clamp(x, 0.0, 1.0));
  color = mix(color, uRamp[2], clamp(x - 1.0, 0.0, 1.0));
  color = mix(color, uRamp[3], clamp(x - 2.0, 0.0, 1.0));
  return mix(color, uRamp[4], clamp(x - 3.0, 0.0, 1.0));
}

void main() {
  vec4 data = texture2D(uData, vUv);
  float mask = data.r;
  float heat = data.g;
  float edgeGlow = data.b;
  float river = data.a;

  // Along-track position of this point on the orbit's angular scale, relative to Colombia.
  vec3 direction = normalize(vPositionWorld);
  float track = wrapPi(atan(dot(direction, uOrbitQuadrature), dot(direction, uOrbitNode)) - uColombiaAngle);
  float revealed = smoothstep(uFront + 0.004, uFront - 0.012, track) * uSweep;
  float visible = max(uOld, revealed);
  float fresh = step(track, uFront) * exp(-(uFront - track) / 0.02) * uSweep * uHeat;

  vec3 ramp = heatRamp(heat);
  float bands = heat * 6.0;
  float contour = 1.0 - smoothstep(0.0, 1.5 * fwidth(bands), abs(fract(bands + 0.5) - 0.5));
  ramp = mix(ramp, uContourColor, 0.18 * contour * step(0.15, heat));

  float heatAlpha = smoothstep(0.06, 0.3, heat) * (0.35 + 0.6 * heat) * visible * mask * uHeat;
  vec3 heatEmission = ramp * heat * (0.45 * fresh + 0.12 * visible) * mask * uHeat;
  float capAlpha = mask * (0.05 + 0.07 * uCap);
  vec3 glow = uCyan * edgeGlow * edgeGlow
    * (mask * (0.08 + 0.3 * uIntensity) + (1.0 - mask) * (0.04 + 0.18 * uIntensity));
  vec3 rivers = uCyan * river * mask * 0.08;

  // Heat over the cyan cap ("over" layer), plus additive glow.
  float alpha = heatAlpha + capAlpha * (1.0 - heatAlpha);
  vec3 straight = (ramp * heatAlpha + uCyan * capAlpha * (1.0 - heatAlpha)) / max(alpha, 1e-4);
  vec3 emission = heatEmission + glow + rivers;
  float edgeFade = smoothstep(0.0, 0.03, vUv.x) * smoothstep(0.0, 0.03, 1.0 - vUv.x)
    * smoothstep(0.0, 0.03, vUv.y) * smoothstep(0.0, 0.03, 1.0 - vUv.y);
  alpha *= edgeFade;
  emission *= edgeFade;

  // Encode the straight color before premultiplying: premultiplying first and then applying the
  // sRGB curve would inflate faint layers into a visible haze.
  #ifdef TONE_MAPPING
    straight = toneMapping(straight);
    emission = toneMapping(emission);
  #endif
  vec3 encoded = linearToOutputTexel(vec4(straight, 1.0)).rgb * alpha
    + linearToOutputTexel(vec4(emission, 1.0)).rgb;
  gl_FragColor = vec4(encoded, alpha);
}
`;

// ---------------------------------------------------------------------------------------------
// Rings: up to three pulses expanding from the centroid, in one draw.

const ringsVertexShader = /* glsl */ `
uniform vec3 uCenter;
uniform vec3 uTangentA;
uniform vec3 uTangentB;
uniform float uExtent;
uniform float uRadius;

varying vec2 vOffset;

void main() {
  vOffset = position.xy * uExtent; // radians from the centroid (small-angle)
  vec3 direction = normalize(uCenter + vOffset.x * uTangentA + vOffset.y * uTangentB);
  gl_Position = projectionMatrix * viewMatrix * vec4(direction * uRadius, 1.0);
}
`;

const ringsFragmentShader = /* glsl */ `
#include <common>

uniform vec3 uColor;
uniform vec3 uRings[3]; // radius, alpha, width (radians)

varying vec2 vOffset;

void main() {
  float distance = length(vOffset);
  float energy = 0.0;
  for (int i = 0; i < 3; i++) {
    vec3 ring = uRings[i];
    float offset = (distance - ring.x) / max(ring.z, 1e-4);
    energy += ring.y * exp(-offset * offset);
  }
  vec3 color = uColor * energy;
  gl_FragColor = vec4(color, max(color.r, max(color.g, color.b)));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

function createPatchGeometry(segments: readonly [number, number]): BufferGeometry {
  const { lngMin, lngMax, latMin, latMax } = GEO.patch;
  const [columns, rows] = segments;
  const positions: number[] = [];
  const uvs: number[] = [];
  const point = new Vector3();
  for (let j = 0; j <= rows; j += 1) {
    for (let i = 0; i <= columns; i += 1) {
      const u = i / columns;
      const v = j / rows;
      latLngToVector3(
        latMin + v * (latMax - latMin),
        lngMin + u * (lngMax - lngMin),
        SCAN.radii.patch,
        point,
      );
      positions.push(point.x, point.y, point.z);
      uvs.push(u, v);
    }
  }
  const indices: number[] = [];
  for (let j = 0; j < rows; j += 1) {
    for (let i = 0; i < columns; i += 1) {
      const a = j * (columns + 1) + i;
      const b = a + 1;
      const c = a + columns + 1;
      const d = c + 1;
      indices.push(a, b, c, b, d, c);
    }
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeBoundingSphere();
  return geometry;
}

function createBorderStroke(): { line: LineSegments2; material: LineMaterial } {
  const segments: number[] = [];
  const a = new Vector3();
  const b = new Vector3();
  for (const ring of COLOMBIA_RINGS) {
    for (let i = 0; i < ring.length; i += 1) {
      const [lngA, latA] = ring[i] ?? [0, 0];
      const [lngB, latB] = ring[(i + 1) % ring.length] ?? [0, 0];
      latLngToVector3(latA, lngA, SCAN.radii.stroke, a);
      latLngToVector3(latB, lngB, SCAN.radii.stroke, b);
      segments.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
  }
  const geometry = new LineSegmentsGeometry();
  geometry.setPositions(segments);
  const material = new LineMaterial({
    color: SCAN.colors.instrument,
    linewidth: SCAN.stroke.widthPx[0],
    worldUnits: false,
    transparent: true,
    blending: AdditiveBlending,
    depthWrite: false,
  });
  const line = new LineSegments2(geometry, material);
  line.name = "colombiaStroke";
  line.renderOrder = 6;
  return { line, material };
}

function overlayMaterial(
  name: string,
  vertexShader: string,
  fragmentShader: string,
  uniforms: Record<string, { value: unknown }>,
  additive: boolean,
): ShaderMaterial {
  return new ShaderMaterial({
    name,
    uniforms,
    vertexShader,
    fragmentShader,
    transparent: true,
    premultipliedAlpha: true,
    blending: additive ? AdditiveBlending : NormalBlending,
    depthWrite: false,
    depthTest: true,
  });
}

/**
 * Builds the scan effect: beam, footprint, Colombia patch (cap, glow and heat), border stroke and
 * ring pulses. The heat map is illustrative (blobs along the main rivers), not measured data, and
 * stays hidden unless {@link SCAN}.heat.visible is set.
 *
 * @param preset - Quality preset (geometry and texture sizes).
 * @param signal - Aborts the data texture generation between slices.
 * @param disabledEffects - Effects switched off for QA: `rings` and `heat`.
 * @returns The effect, ready to add to the scene.
 */
export async function createScan(
  preset: QualityPreset,
  signal?: AbortSignal,
  disabledEffects: ReadonlySet<HeroEffect> = new Set(),
): Promise<ScanEffect> {
  const heatVisible = SCAN.heat.visible && !disabledEffects.has("heat");
  const data: DataTexture = await createColombiaDataTexture(
    preset.scan.data[0],
    preset.scan.data[1],
    { heat: heatVisible },
    signal,
  );
  const cyan = new Color(SCAN.colors.instrument);

  // Beam: apex at the origin, base at y = −1; scaled every frame from the aperture to the ground.
  const beamGeometry = new ConeGeometry(1, 1, preset.scan.coneRadial, 16, true).translate(
    0,
    -0.5,
    0,
  );
  const beamMaterial = overlayMaterial(
    "scanBeam",
    beamVertexShader,
    beamFragmentShader,
    {
      uColor: { value: new Color(SCAN.colors.beam) },
      uIntensity: { value: 0 },
      uLength: { value: 1 },
      uTime: { value: 0 },
      uShape: {
        value: new Vector4(
          SCAN.beam.bodyGain,
          SCAN.beam.hot,
          SCAN.beam.stripeLength,
          SCAN.beam.stripeSpeed,
        ),
      },
    },
    true,
  );
  beamMaterial.side = DoubleSide;
  const beam = new Mesh(beamGeometry, beamMaterial);
  beam.name = "scanBeam";
  beam.renderOrder = 7;
  beam.frustumCulled = false;

  const [footprintColumns, footprintRows] = preset.scan.footprintSegments;
  const footprintGeometry = new PlaneGeometry(2.4, 4.2, footprintColumns, footprintRows).translate(
    0,
    -0.9,
    0,
  );
  const footprintMaterial = overlayMaterial(
    "scanFootprint",
    footprintVertexShader,
    footprintFragmentShader,
    {
      uCenter: { value: new Vector3() },
      uCrossTrack: { value: ORBIT_NORMAL.clone() },
      uAlongTrack: { value: new Vector3() },
      uSemiAxes: { value: new Vector2(SCAN.footprint.crossTrackRad, SCAN.footprint.alongTrackRad) },
      uRadius: { value: SCAN.radii.footprint },
      uColor: { value: cyan },
      uIntensity: { value: 0 },
    },
    true,
  );
  const footprint = new Mesh(footprintGeometry, footprintMaterial);
  footprint.name = "scanFootprint";
  footprint.renderOrder = 4;
  footprint.frustumCulled = false;

  const patchMaterial = overlayMaterial(
    "colombiaPatch",
    patchVertexShader,
    patchFragmentShader,
    {
      uData: { value: data },
      uCyan: { value: cyan },
      uRamp: { value: SCAN.heat.ramp.map((hex) => new Color(hex)) },
      uContourColor: { value: new Color(SCAN.heat.contourColor) },
      uIntensity: { value: 0 },
      uHeat: { value: heatVisible ? 1 : 0 },
      uCap: { value: 0 },
      uOld: { value: SCAN.heat.floor },
      uFront: { value: -SCAN.heat.frontLimit },
      uSweep: { value: 0 },
      uOrbitNode: { value: ORBIT_NODE },
      uOrbitQuadrature: { value: ORBIT_QUADRATURE },
      uColombiaAngle: { value: COLOMBIA_ORBIT_ANGLE },
    },
    false,
  );
  patchMaterial.polygonOffset = true;
  patchMaterial.polygonOffsetFactor = -1;
  patchMaterial.polygonOffsetUnits = -4;
  const patch = new Mesh(createPatchGeometry(preset.scan.patchSegments), patchMaterial);
  patch.name = "colombiaPatch";
  patch.renderOrder = 3;

  const { line: stroke, material: strokeMaterial } = createBorderStroke();

  // Ring pulses on a small tangent plane around the centroid.
  const tangentA = new Vector3().crossVectors(new Vector3(0, 1, 0), COLOMBIA_DIRECTION).normalize();
  const tangentB = new Vector3().crossVectors(COLOMBIA_DIRECTION, tangentA).normalize();
  const ringSlots = Array.from({ length: SCAN.rings.slots }, () => new Vector3(0, 0, 0.01));
  const ringsMaterial = overlayMaterial(
    "scanRings",
    ringsVertexShader,
    ringsFragmentShader,
    {
      uCenter: { value: COLOMBIA_DIRECTION },
      uTangentA: { value: tangentA },
      uTangentB: { value: tangentB },
      uExtent: { value: SCAN.rings.extentRad },
      uRadius: { value: SCAN.radii.rings },
      uColor: { value: new Color(SCAN.colors.rings).multiplyScalar(SCAN.rings.gain) },
      uRings: { value: ringSlots },
    },
    true,
  );
  const rings = new Mesh(
    new PlaneGeometry(2, 2, preset.scan.ringSegments, preset.scan.ringSegments),
    ringsMaterial,
  );
  rings.name = "scanRings";
  rings.renderOrder = 5;
  rings.frustumCulled = false;
  rings.visible = !disabledEffects.has("rings");

  const beamUniforms = beamMaterial.uniforms as {
    uIntensity: Uniform<number>;
    uLength: Uniform<number>;
    uTime: Uniform<number>;
  };
  const footprintUniforms = footprintMaterial.uniforms as {
    uCenter: Uniform<Vector3>;
    uAlongTrack: Uniform<Vector3>;
    uIntensity: Uniform<number>;
  };
  const patchUniforms = patchMaterial.uniforms as {
    uIntensity: Uniform<number>;
    uCap: Uniform<number>;
    uOld: Uniform<number>;
    uFront: Uniform<number>;
    uSweep: Uniform<number>;
  };

  // State machine and damped drivers.
  const status: ScanEffect["status"] = { phase: "idle", intensity: 0, push: 0 };
  const { thresholds } = SCAN;
  let previousAngleToColombia = Number.NaN;
  let previousIntensity = 0;
  let beamLevel = 0;
  let strokeLevel: number = SCAN.stroke.idle;
  let capLevel = 0;
  let old: number = SCAN.heat.floor;
  let sinceLastRing = 0;
  let initialized = false;
  const ringAges = Array.from({ length: SCAN.rings.slots }, () => Number.POSITIVE_INFINITY);
  const [psiIn, psiOut] = SCAN.intensityDeg.map((deg) => MathUtils.degToRad(deg)) as [
    number,
    number,
  ];

  function spawnRing(): void {
    // Reuse the oldest slot.
    let oldest = 0;
    for (let i = 1; i < ringAges.length; i += 1) {
      if ((ringAges[i] ?? 0) > (ringAges[oldest] ?? 0)) {
        oldest = i;
      }
    }
    ringAges[oldest] = 0;
  }

  function setPhase(next: ScanPhase): void {
    if (next === status.phase) {
      return;
    }
    status.phase = next;
    switch (next) {
      case "idle":
        old = 1;
        break;
      case "scan":
        sinceLastRing = 0;
        break;
      case "approach":
      case "leave":
        break;
    }
  }

  // Phase that matches a pass geometry without history (first frame or a time jump).
  function phaseFor(intensity: number, closing: boolean): ScanPhase {
    if (intensity >= thresholds.scan) {
      return "scan";
    }
    if (intensity > thresholds.approach) {
      return closing ? "approach" : "leave";
    }
    return "idle";
  }

  const alongTrack = new Vector3();
  const beamScale = new Vector3();

  let stillLook = false;
  let snapNext = true;

  function update(timeS: number, dt: number, satellite: SatelliteState): void {
    const psi = satellite.radial.angleTo(COLOMBIA_DIRECTION);
    const intensity = 1 - MathUtils.smoothstep(psi, psiIn, psiOut);
    const closing = Number.isNaN(previousAngleToColombia) ? true : psi < previousAngleToColombia;
    previousAngleToColombia = psi;
    status.intensity = intensity;

    if (!initialized) {
      status.phase = phaseFor(intensity, angleBehindColombia(satellite.angle) < 0);
      initialized = true;
    } else {
      switch (status.phase) {
        case "idle":
          if (intensity > thresholds.approach && closing) {
            setPhase("approach");
          }
          break;
        case "approach":
          if (intensity >= thresholds.scan) {
            setPhase("scan");
          } else if (intensity < thresholds.approach && !closing) {
            setPhase("idle");
          }
          break;
        case "scan":
          if (intensity < thresholds.leave && !closing) {
            setPhase("leave");
          }
          break;
        case "leave":
          if (intensity < thresholds.approach) {
            setPhase("idle");
          }
          break;
      }
    }

    // Rings: a "lock" pulse when the approach crosses the lock level, then a steady cadence.
    if (
      status.phase === "approach" &&
      previousIntensity < thresholds.lock &&
      intensity >= thresholds.lock
    ) {
      spawnRing();
    }
    if (status.phase === "scan") {
      sinceLastRing += dt;
      if (sinceLastRing >= SCAN.rings.cadenceS) {
        sinceLastRing -= SCAN.rings.cadenceS;
        spawnRing();
      }
    }
    previousIntensity = intensity;

    // Damped drivers.
    const { damping } = SCAN;
    const beamTarget = status.phase === "idle" ? 0 : intensity;
    const strokeTarget = SCAN.stroke.idle + SCAN.stroke.gain * intensity;
    const pushTarget = status.phase === "scan" ? 1 : 0;
    if (snapNext) {
      beamLevel = beamTarget;
      strokeLevel = strokeTarget;
      capLevel = intensity;
      status.push = pushTarget;
      if (stillLook) {
        old = 1;
      }
      snapNext = false;
    } else {
      beamLevel = MathUtils.damp(beamLevel, beamTarget, damping.beam, dt);
      strokeLevel = MathUtils.damp(
        strokeLevel,
        strokeTarget,
        strokeTarget > strokeLevel ? damping.strokeRise : damping.strokeFall,
        dt,
      );
      capLevel = MathUtils.damp(capLevel, intensity, damping.cap, dt);
      status.push = MathUtils.damp(status.push, pushTarget, damping.push, dt);
      if (status.phase === "idle") {
        old = SCAN.heat.floor + (old - SCAN.heat.floor) * Math.exp(-dt / SCAN.heat.agingS);
      }
    }

    // Beam from the aperture to just below the ground, aligned with the satellite.
    const apertureHeight = satellite.aperture.length() - GLOBE_RADIUS;
    const length = apertureHeight + SCAN.beam.sink;
    beam.position.copy(satellite.aperture);
    beam.quaternion.copy(satellite.attitude);
    beamScale.set(
      (SCAN.beam.crossTrack * length) / apertureHeight,
      length,
      (SCAN.beam.alongTrack * length) / apertureHeight,
    );
    beam.scale.copy(beamScale);
    beam.visible = beamLevel > 0.002;
    beamUniforms.uIntensity.value = beamLevel;
    beamUniforms.uLength.value = length;
    // The shader multiplies by the stripe speed; wrap to keep float precision.
    beamUniforms.uTime.value = timeS % 1000;

    orbitVelocityDirection(satellite.angle, alongTrack);
    footprintUniforms.uCenter.value.copy(satellite.radial);
    footprintUniforms.uAlongTrack.value.copy(alongTrack);
    footprintUniforms.uIntensity.value = beamLevel;
    footprint.visible = beam.visible;

    patchUniforms.uIntensity.value = intensity;
    patchUniforms.uCap.value = capLevel;
    patchUniforms.uOld.value = old;
    patchUniforms.uSweep.value = status.phase === "idle" ? 0 : 1;
    patchUniforms.uFront.value = MathUtils.clamp(
      angleBehindColombia(satellite.angle),
      -SCAN.heat.frontLimit,
      SCAN.heat.frontLimit,
    );

    strokeMaterial.color.copy(cyan).multiplyScalar(strokeLevel);
    const [widthIdle, widthScan] = SCAN.stroke.widthPx;
    strokeMaterial.linewidth = MathUtils.lerp(widthIdle, widthScan, intensity);

    const { lifeS, maxRadiusRad } = SCAN.rings;
    ringAges.forEach((age, index) => {
      const slot = ringSlots[index];
      if (slot === undefined) {
        return;
      }
      const nextAge = stillLook && index === 0 ? 0.45 * lifeS : age + dt;
      ringAges[index] = nextAge;
      const tau = nextAge / lifeS;
      if (tau >= 1) {
        slot.set(0, 0, 0.01);
        return;
      }
      slot.set(
        maxRadiusRad * (1 - (1 - tau) ** 3),
        (1 - tau) ** 2 * Math.max(intensity, stillLook ? 1 : 0),
        0.006 + 0.01 * tau,
      );
    });
  }

  return {
    objects: [patch, footprint, rings, stroke, beam],
    status,
    update,
    snap(still) {
      snapNext = true;
      stillLook = still;
    },
    setResolution(width, height) {
      strokeMaterial.resolution.set(width, height);
    },
    dispose() {
      for (const mesh of [beam, footprint, patch, rings]) {
        mesh.geometry.dispose();
        mesh.material.dispose();
      }
      stroke.geometry.dispose();
      strokeMaterial.dispose();
      data.dispose();
    },
  };
}

// Signed orbit angle from Colombia (negative before the pass, positive after).
function angleBehindColombia(angle: number): number {
  const delta = angle - COLOMBIA_ORBIT_ANGLE;
  return delta - TAU * Math.floor((delta + Math.PI) / TAU);
}
