import {
  AdditiveBlending,
  BufferGeometry,
  Float32BufferAttribute,
  Points,
  ShaderMaterial,
  Vector3,
} from "three";

import { STARFIELD } from "./config.ts";
import { mulberry32 } from "./textures.ts";

/** A starfield and the hooks the frame loop needs. */
export interface Starfield {
  /** The points object to add to the scene. */
  readonly object: Points;
  /**
   * Advances the twinkle animation.
   *
   * @param timeS - Scene time in seconds.
   */
  readonly update: (timeS: number) => void;
  /**
   * Keeps point sizes in CSS pixels.
   *
   * @param pixelRatio - The renderer's current pixel ratio.
   */
  readonly setPixelRatio: (pixelRatio: number) => void;
  /** Releases the geometry and the material. */
  readonly dispose: () => void;
}

// Approximate blackbody colors (linear RGB) from 3500 K to 12000 K.
const STAR_COLORS: readonly (readonly [number, number, number])[] = [
  [1.0, 0.72, 0.42],
  [1.0, 0.89, 0.76],
  [1.0, 1.0, 1.0],
  [0.8, 0.87, 1.0],
  [0.68, 0.78, 1.0],
];

const vertexShader = /* glsl */ `
uniform float uTime;
uniform float uPixelRatio;

attribute vec3 aColor;
attribute float aBrightness;
attribute float aSize;
attribute vec3 aTwinkle; // depth, frequency (Hz), phase

varying vec3 vColor;

void main() {
  float wave = 0.5 + 0.5 * sin(6.2831853 * aTwinkle.y * uTime + aTwinkle.z);
  float twinkle = 1.0 - aTwinkle.x * wave * wave * wave * wave;
  vColor = aColor * aBrightness * twinkle;
  gl_PointSize = aSize * uPixelRatio;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const fragmentShader = /* glsl */ `
varying vec3 vColor;

void main() {
  vec2 offset = gl_PointCoord - 0.5;
  float falloff = exp(-dot(offset, offset) * 18.0);
  vec3 color = vColor * falloff;
  // Premultiplied output; alpha lets the glow show over the transparent canvas.
  gl_FragColor = vec4(color, max(color.r, max(color.g, color.b)));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

// Gaussian sample (Box-Muller) from the seeded generator.
function gaussian(random: () => number): number {
  const u = Math.max(random(), 1e-9);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * random());
}

/**
 * Builds a seeded starfield on a thick shell around the scene, with a faint Milky Way band,
 * varied colors, sizes and brightness, and a slow twinkle on faint stars only.
 *
 * @param count - Number of stars.
 * @param pixelRatio - Initial renderer pixel ratio.
 * @returns The points object plus update and dispose hooks.
 */
export function createStarfield(count: number, pixelRatio: number): Starfield {
  const random = mulberry32(STARFIELD.seed);
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const brightness = new Float32Array(count);
  const sizes = new Float32Array(count);
  const twinkles = new Float32Array(count * 3);

  // Milky Way band: a great circle whose normal is tilted from +Y.
  const tilt = (STARFIELD.bandTiltDeg * Math.PI) / 180;
  const bandNormal = new Vector3(Math.sin(tilt), Math.cos(tilt), 0.35).normalize();
  const bandU = new Vector3(0, 0, 1).cross(bandNormal).normalize();
  const bandV = new Vector3().crossVectors(bandNormal, bandU);
  const bandSigma = (STARFIELD.bandSigmaDeg * Math.PI) / 180;
  const direction = new Vector3();

  const [radiusMin, radiusMax] = STARFIELD.radius;
  const [brightnessMin, brightnessRange] = STARFIELD.brightness;
  const [sizeMin, sizeRange] = STARFIELD.size;
  const [depthMin, depthMax] = STARFIELD.twinkleDepth;
  const [hzMin, hzMax] = STARFIELD.twinkleHz;

  for (let i = 0; i < count; i += 1) {
    if (random() < STARFIELD.bandShare) {
      const along = random() * Math.PI * 2;
      const across = gaussian(random) * bandSigma;
      direction
        .copy(bandU)
        .multiplyScalar(Math.cos(along))
        .addScaledVector(bandV, Math.sin(along))
        .multiplyScalar(Math.cos(across))
        .addScaledVector(bandNormal, Math.sin(across));
    } else {
      const z = random() * 2 - 1;
      const angle = random() * Math.PI * 2;
      const ring = Math.sqrt(1 - z * z);
      direction.set(ring * Math.cos(angle), z, ring * Math.sin(angle));
    }
    const radius = radiusMin + random() * (radiusMax - radiusMin);
    positions.set([direction.x * radius, direction.y * radius, direction.z * radius], i * 3);

    const b = brightnessMin + brightnessRange * random() ** STARFIELD.brightnessExponent;
    brightness[i] = b;
    sizes[i] = sizeMin + sizeRange * b ** 0.6;

    // Blend two neighbouring blackbody colors, then desaturate by 40%.
    const t = random() * (STAR_COLORS.length - 1);
    const index = Math.floor(t);
    const from = STAR_COLORS[index] ?? [1, 1, 1];
    const to = STAR_COLORS[Math.min(index + 1, STAR_COLORS.length - 1)] ?? from;
    const mix = t - index;
    for (let channel = 0; channel < 3; channel += 1) {
      const value = (from[channel] ?? 1) * (1 - mix) + (to[channel] ?? 1) * mix;
      colors[i * 3 + channel] = value * 0.6 + 0.4;
    }

    // Only faint stars twinkle; bright ones stay steady.
    const twinkling = b < 0.45 && random() < STARFIELD.twinkleShare;
    twinkles.set(
      twinkling
        ? [
            depthMin + random() * (depthMax - depthMin),
            hzMin + random() * (hzMax - hzMin),
            random() * Math.PI * 2,
          ]
        : [0, 0, 0],
      i * 3,
    );
  }

  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
  geometry.setAttribute("aColor", new Float32BufferAttribute(colors, 3));
  geometry.setAttribute("aBrightness", new Float32BufferAttribute(brightness, 1));
  geometry.setAttribute("aSize", new Float32BufferAttribute(sizes, 1));
  geometry.setAttribute("aTwinkle", new Float32BufferAttribute(twinkles, 3));

  const material = new ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uPixelRatio: { value: pixelRatio } },
    vertexShader,
    fragmentShader,
    blending: AdditiveBlending,
    premultipliedAlpha: true,
    transparent: true,
    depthWrite: false,
  });

  const object = new Points(geometry, material);
  object.name = "starfield";
  object.frustumCulled = false;
  object.renderOrder = -10;

  const { uTime, uPixelRatio } = material.uniforms as {
    uTime: { value: number };
    uPixelRatio: { value: number };
  };

  return {
    object,
    update(timeS) {
      uTime.value = timeS;
    },
    setPixelRatio(value) {
      uPixelRatio.value = value;
    },
    dispose() {
      geometry.dispose();
      material.dispose();
    },
  };
}
