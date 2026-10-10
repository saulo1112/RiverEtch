import {
  CanvasTexture,
  DataTexture,
  ImageBitmapLoader,
  LinearFilter,
  LinearMipmapLinearFilter,
  MathUtils,
  NoColorSpace,
  RepeatWrapping,
  SRGBColorSpace,
  Texture,
  type WebGLRenderer,
} from "three";

/**
 * Deterministic pseudo-random generator (mulberry32), so procedural textures look the same on
 * every load.
 *
 * @param seed - Any 32-bit integer.
 * @returns A function returning floats in [0, 1).
 */
export function mulberry32(seed: number): () => number {
  let state = seed >>> 0;

  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Loads a texture from `public/textures/`, decoding it off the main thread.
 *
 * @param fileName - File name inside `public/textures/`.
 * @param renderer - Renderer used to read the maximum anisotropy.
 * @param signal - Aborts the load when the hero unmounts.
 * @param kind - `"color"` for sRGB images, `"data"` for masks that must not be color-converted.
 * @returns A texture with mipmaps; its ImageBitmap is closed when the texture is disposed.
 */
export async function loadTexture(
  fileName: string,
  renderer: WebGLRenderer,
  signal: AbortSignal,
  kind: "color" | "data",
): Promise<Texture> {
  const loader = new ImageBitmapLoader();
  // Cancel the download and decode if the hero unmounts first.
  signal.addEventListener(
    "abort",
    () => {
      loader.abort();
    },
    { once: true },
  );
  loader.setOptions({
    imageOrientation: "flipY",
    premultiplyAlpha: "none",
    colorSpaceConversion: kind === "data" ? "none" : "default",
  });
  const bitmap = await loader.loadAsync(`${import.meta.env.BASE_URL}textures/${fileName}`);
  if (signal.aborted) {
    bitmap.close();
    throw new DOMException("Hero unmounted while loading a texture.", "AbortError");
  }

  const texture = new Texture(bitmap);
  // The bitmap is already flipped at decode time.
  texture.flipY = false;
  texture.colorSpace = kind === "color" ? SRGBColorSpace : NoColorSpace;
  texture.minFilter = LinearMipmapLinearFilter;
  texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  texture.needsUpdate = true;
  texture.addEventListener("dispose", () => {
    bitmap.close();
  });

  return texture;
}

/**
 * Builds a placeholder Earth map (dark ocean with soft land masses) for when the real texture
 * cannot be loaded.
 *
 * @returns An sRGB canvas texture in equirectangular layout.
 */
export function createFallbackEarthTexture(): CanvasTexture {
  const width = 1024;
  const height = 512;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (context !== null) {
    const ocean = context.createLinearGradient(0, 0, 0, height);
    ocean.addColorStop(0, "#071634");
    ocean.addColorStop(0.5, "#0b2047");
    ocean.addColorStop(1, "#071634");
    context.fillStyle = ocean;
    context.fillRect(0, 0, width, height);

    const random = mulberry32(170);
    context.filter = "blur(6px)";
    for (let i = 0; i < 70; i += 1) {
      const x = random() * width;
      const y = height * (0.15 + random() * 0.7);
      const radius = 12 + random() * 46;
      context.fillStyle = random() > 0.5 ? "#2c3a17" : "#4a4326";
      context.beginPath();
      context.ellipse(x, y, radius * 1.4, radius, random() * Math.PI, 0, Math.PI * 2);
      context.fill();
    }
  }

  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  return texture;
}

// ---------------------------------------------------------------------------------------------
// Procedural satellite textures. All of them are seeded, so the satellite looks the same on every
// load, and the foil maps tile seamlessly.

/**
 * Resolves on a macrotask, so long texture generation can be split into slices. Unlike
 * requestAnimationFrame it also runs in background tabs.
 *
 * @param signal - Optional abort signal; the promise rejects if it fired in the meantime.
 * @returns A promise that resolves after the browser had a chance to run other work.
 */
export async function yieldToBrowser(signal?: AbortSignal): Promise<void> {
  await new Promise((resolve) => {
    setTimeout(resolve, 0);
  });
  signal?.throwIfAborted();
}

function wrapIndex(value: number, size: number): number {
  return ((value % size) + size) % size;
}

// Cheaper wrap for values at most one period outside [0, size) (hot loops).
function wrapNear(value: number, size: number): number {
  return value < 0 ? value + size : value >= size ? value - size : value;
}

function gaussianSample(random: () => number): number {
  const u = Math.max(random(), 1e-9);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * random());
}

// Tileable value noise on a `period` x `period` lattice; x and y are in lattice units.
function createTileableNoise(
  period: number,
  random: () => number,
): (x: number, y: number) => number {
  const lattice = new Float32Array(period * period);
  for (let i = 0; i < lattice.length; i += 1) {
    lattice[i] = random();
  }
  return (x, y) => {
    const xFloor = Math.floor(x);
    const yFloor = Math.floor(y);
    const fx = x - xFloor;
    const fy = y - yFloor;
    const x0 = wrapIndex(xFloor, period);
    const y0 = wrapIndex(yFloor, period);
    const x1 = (x0 + 1) % period;
    const y1 = (y0 + 1) % period;
    const sx = fx * fx * (3 - 2 * fx);
    const sy = fy * fy * (3 - 2 * fy);
    const a = lattice[y0 * period + x0] ?? 0;
    const b = lattice[y0 * period + x1] ?? 0;
    const c = lattice[y1 * period + x0] ?? 0;
    const d = lattice[y1 * period + x1] ?? 0;
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
  };
}

function createDataTexture(
  data: Uint8Array,
  width: number,
  height: number,
  color: boolean,
  anisotropy: number,
): DataTexture {
  const texture = new DataTexture(data, width, height);
  texture.colorSpace = color ? SRGBColorSpace : NoColorSpace;
  texture.wrapS = RepeatWrapping;
  texture.wrapT = RepeatWrapping;
  texture.magFilter = LinearFilter;
  texture.minFilter = LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  texture.anisotropy = anisotropy;
  texture.needsUpdate = true;
  return texture;
}

function configureCanvasTexture(
  canvas: HTMLCanvasElement,
  color: boolean,
  anisotropy: number,
): CanvasTexture {
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = color ? SRGBColorSpace : NoColorSpace;
  texture.minFilter = LinearMipmapLinearFilter;
  texture.anisotropy = anisotropy;
  return texture;
}

function createCanvas(
  width: number,
  height: number,
  willReadFrequently = false,
): CanvasRenderingContext2D {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently });
  if (context === null) {
    throw new Error("2D canvas is not available for the satellite textures.");
  }
  return context;
}

/** Crinkled multi-layer insulation (MLI) foil maps. */
export interface FoilTextures {
  /** Tangent-space normal map. */
  readonly normal: DataTexture;
  /** R = ambient occlusion, G = roughness, B = 1. */
  readonly orm: DataTexture;
  /** Grey albedo variation (sRGB), multiplied with the foil color. */
  readonly albedo: DataTexture;
}

/**
 * Generates tileable foil maps from a height field made of pillowy noise, Worley facets, long
 * wrinkles along two dominant directions and fine noise. Yields to the browser between passes.
 *
 * @param size - Texture size in texels (square).
 * @param creaseCount - Number of creases.
 * @param anisotropy - Anisotropic filtering level.
 * @param signal - Aborts the generation between slices.
 * @returns Normal, occlusion/roughness and albedo maps.
 */
export async function createFoilTextures(
  size: number,
  creaseCount: number,
  anisotropy: number,
  signal?: AbortSignal,
): Promise<FoilTextures> {
  const random = mulberry32(0x6f11);
  const count = size * size;
  const height = new Float32Array(count);

  // 1. Pillowy fbm.
  const octaves = [4, 8, 16, 32].map((period) => ({
    period,
    noise: createTileableNoise(period, random),
  }));
  const tone = new Float32Array(count);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let value = 0;
      let amplitude = 0.5;
      for (const { period, noise } of octaves) {
        value += amplitude * noise((x / size) * period, (y / size) * period);
        amplitude *= 0.5;
      }
      height[y * size + x] = 0.45 * value;
      tone[y * size + x] = value;
    }
  }
  await yieldToBrowser(signal);

  // 2. Worley F2 - F1 at two scales: flat facets separated by V-shaped folds, like crumpled foil.
  for (const [cells, weight] of [
    [3, 0.45],
    [12, 0.16],
  ] as const) {
    const featureX = new Float32Array(cells * cells);
    const featureY = new Float32Array(cells * cells);
    for (let i = 0; i < cells * cells; i += 1) {
      featureX[i] = random();
      featureY[i] = random();
    }
    for (let y = 0; y < size; y += 1) {
      const gy = (y / size) * cells;
      const cy = Math.floor(gy);
      for (let x = 0; x < size; x += 1) {
        const gx = (x / size) * cells;
        const cx = Math.floor(gx);
        let f1 = 81;
        let f2 = 81;
        for (let dy = -1; dy <= 1; dy += 1) {
          for (let dx = -1; dx <= 1; dx += 1) {
            const index = wrapNear(cy + dy, cells) * cells + wrapNear(cx + dx, cells);
            const px = cx + dx + (featureX[index] ?? 0);
            const py = cy + dy + (featureY[index] ?? 0);
            // Squared distances; the square roots are taken once per texel below.
            const distance = (px - gx) * (px - gx) + (py - gy) * (py - gy);
            if (distance < f1) {
              f2 = f1;
              f1 = distance;
            } else if (distance < f2) {
              f2 = distance;
            }
          }
        }
        height[y * size + x] =
          (height[y * size + x] ?? 0) + weight * (Math.sqrt(f2) - Math.sqrt(f1));
      }
    }
  }
  await yieldToBrowser(signal);

  // 3. Long wrinkles on two dominant axes: smooth ridges and sharper folds with soft ends.
  const texel = size / 512;
  for (let c = 0; c < creaseCount; c += 1) {
    const angle = ((random() < 0.5 ? 25 : 115) + gaussianSample(random) * 18) * (Math.PI / 180);
    const length = size * (0.15 + 0.35 * random());
    const amplitude = (random() < 0.5 ? -1 : 1) * (0.04 + 0.1 * random());
    const halfWidth = (10 + 16 * random()) * texel;
    const sharp = random() < 0.15;
    const centerX = random() * size;
    const centerY = random() * size;
    const dirX = Math.cos(angle);
    const dirY = Math.sin(angle);
    const startX = centerX - (dirX * length) / 2;
    const startY = centerY - (dirY * length) / 2;
    // Walk the major axis and only visit the band within `halfWidth` of the segment.
    const alongX = Math.abs(dirX) >= Math.abs(dirY);
    const major = alongX ? dirX : dirY;
    const minor = alongX ? dirY : dirX;
    const majorStart = alongX ? startX : startY;
    const minorStart = alongX ? startY : startX;
    const band = halfWidth / Math.abs(major);
    const first = Math.floor(Math.min(majorStart, majorStart + major * length) - halfWidth);
    const last = Math.ceil(Math.max(majorStart, majorStart + major * length) + halfWidth);
    for (let m = first; m <= last; m += 1) {
      const centerMinor = minorStart + ((m - majorStart) / major) * minor;
      for (let n = Math.floor(centerMinor - band); n <= Math.ceil(centerMinor + band); n += 1) {
        const x = alongX ? m : n;
        const y = alongX ? n : m;
        const rx = x - startX;
        const ry = y - startY;
        const along = (rx * dirX + ry * dirY) / length;
        if (along <= 0 || along >= 1) {
          continue;
        }
        const across = Math.abs(rx * -dirY + ry * dirX) / halfWidth;
        if (across >= 1) {
          continue;
        }
        const taper =
          MathUtils.smoothstep(along, 0, 0.2) * (1 - MathUtils.smoothstep(along, 0.8, 1));
        const profile = sharp ? 1 - across : (1 - across * across) ** 2;
        const index = wrapIndex(y, size) * size + wrapIndex(x, size);
        height[index] = (height[index] ?? 0) + amplitude * taper * profile;
      }
    }
  }

  // 4. Fine noise with ~6 texel features.
  const microPeriod = Math.max(4, Math.round(size / 6));
  const micro = createTileableNoise(microPeriod, random);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      height[y * size + x] =
        (height[y * size + x] ?? 0) +
        0.03 * micro((x / size) * microPeriod, (y / size) * microPeriod);
    }
  }

  await yieldToBrowser(signal);

  // Box blur (radius 3, wrapping) for the cavity term of the occlusion.
  const blurred = new Float32Array(count);
  const temp = new Float32Array(count);
  const radius = 3;
  const taps = radius * 2 + 1;
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let sum = 0;
      for (let k = -radius; k <= radius; k += 1) {
        sum += height[y * size + wrapNear(x + k, size)] ?? 0;
      }
      temp[y * size + x] = sum / taps;
    }
  }
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let sum = 0;
      for (let k = -radius; k <= radius; k += 1) {
        sum += temp[wrapNear(y + k, size) * size + x] ?? 0;
      }
      blurred[y * size + x] = sum / taps;
    }
  }

  const normalData = new Uint8Array(count * 4);
  const ormData = new Uint8Array(count * 4);
  const albedoData = new Uint8Array(count * 4);
  const at = (x: number, y: number) => height[wrapNear(y, size) * size + wrapNear(x, size)] ?? 0;
  const slope = 2.4 * (size / 64);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const i = y * size + x;
      // Sobel with wrapping; DataTexture rows run bottom to top, so +y is texture-up.
      const dx =
        at(x + 1, y - 1) +
        2 * at(x + 1, y) +
        at(x + 1, y + 1) -
        at(x - 1, y - 1) -
        2 * at(x - 1, y) -
        at(x - 1, y + 1);
      const dy =
        at(x - 1, y + 1) +
        2 * at(x, y + 1) +
        at(x + 1, y + 1) -
        at(x - 1, y - 1) -
        2 * at(x, y - 1) -
        at(x + 1, y - 1);
      const nx = (-slope * dx) / 8;
      const ny = (-slope * dy) / 8;
      const inverseLength = 1 / Math.hypot(nx, ny, 1);
      normalData[i * 4] = Math.round((nx * inverseLength * 0.5 + 0.5) * 255);
      normalData[i * 4 + 1] = Math.round((ny * inverseLength * 0.5 + 0.5) * 255);
      normalData[i * 4 + 2] = Math.round((inverseLength * 0.5 + 0.5) * 255);
      normalData[i * 4 + 3] = 255;

      const h = height[i] ?? 0;
      const cavity = Math.max((blurred[i] ?? 0) - h, 0);
      const laplacian = Math.abs(4 * h - at(x + 1, y) - at(x - 1, y) - at(x, y + 1) - at(x, y - 1));
      ormData[i * 4] = Math.round(MathUtils.clamp(1 - cavity * 5, 0.45, 1) * 255);
      // Rough enough that the key light breaks into foil sparkle instead of a flat glare.
      ormData[i * 4 + 1] = Math.round((0.42 + 0.12 * Math.min(laplacian * 30, 1)) * 255);
      ormData[i * 4 + 2] = 255;
      ormData[i * 4 + 3] = 255;

      const grey = Math.round(MathUtils.clamp(0.88 + 0.16 * (tone[i] ?? 0.5), 0, 1) * 255);
      albedoData[i * 4] = grey;
      albedoData[i * 4 + 1] = grey;
      albedoData[i * 4 + 2] = grey;
      albedoData[i * 4 + 3] = 255;
    }
  }

  return {
    normal: createDataTexture(normalData, size, size, false, anisotropy),
    orm: createDataTexture(ormData, size, size, false, anisotropy),
    albedo: createDataTexture(albedoData, size, size, true, anisotropy),
  };
}

/** Solar-panel face maps (one panel; the texture spans its +Y face). */
export interface CellTextures {
  /** Cell, busbar and frame colors (sRGB). */
  readonly albedo: CanvasTexture;
  /** Faint blue glow of the cells only (sRGB). */
  readonly emissive: CanvasTexture;
  /** Per-cell tilt normal map. */
  readonly normal: CanvasTexture;
  /** R = 1, G = roughness, B = metalness. */
  readonly orm: CanvasTexture;
}

/** Cell layout of a solar panel. */
export interface CellLayout {
  /** Cells along the panel's X axis. */
  readonly columns: number;
  /** Cells along the panel's Z axis. */
  readonly rows: number;
  /** Substrate gap between cells, as a share of the texture's shorter side. */
  readonly gapFraction: number;
  /** Substrate color between the cells (sRGB hex). */
  readonly gapColor: string;
  /** Range of the cells' HSL lightness, in percent. */
  readonly lightness: readonly [number, number];
}

/**
 * Draws a solar panel: a bright frame, cropped-corner cells on a light substrate, busbars and fine
 * fingers. Every line is at least two texels wide so it survives mipmapping.
 *
 * @param width - Texture width in texels (along the panel's X axis).
 * @param height - Texture height in texels (along the panel's Z axis).
 * @param anisotropy - Anisotropic filtering level.
 * @param layout - Cell grid, substrate gap and cell lightness.
 * @returns Albedo, emissive, normal and roughness/metalness maps.
 */
export function createCellTextures(
  width: number,
  height: number,
  anisotropy: number,
  layout: CellLayout,
): CellTextures {
  const random = mulberry32(0xce11);
  const albedo = createCanvas(width, height);
  const emissive = createCanvas(width, height);
  const normal = createCanvas(width, height);
  const orm = createCanvas(width, height);

  // Base layers: frame everywhere, then the inner area as dark gaps.
  albedo.fillStyle = "#c8cbd0";
  albedo.fillRect(0, 0, width, height);
  emissive.fillStyle = "#000000";
  emissive.fillRect(0, 0, width, height);
  normal.fillStyle = "rgb(128,128,255)";
  normal.fillRect(0, 0, width, height);
  orm.fillStyle = `rgb(255,${Math.round(0.38 * 255)},255)`;
  orm.fillRect(0, 0, width, height);

  const frame = Math.max(2, Math.round(Math.min(width, height) * 0.025));
  const innerWidth = width - frame * 2;
  const innerHeight = height - frame * 2;
  // Substrate between the cells: light enough that the grid reads at hero scale.
  albedo.fillStyle = layout.gapColor;
  albedo.fillRect(frame, frame, innerWidth, innerHeight);
  orm.fillStyle = `rgb(255,${Math.round(0.7 * 255)},0)`;
  orm.fillRect(frame, frame, innerWidth, innerHeight);

  const { columns, rows } = layout;
  const gap = Math.max(2, Math.round(Math.min(width, height) * layout.gapFraction));
  const cellWidth = (innerWidth - gap * (columns + 1)) / columns;
  const cellHeight = (innerHeight - gap * (rows + 1)) / rows;
  const crop = Math.min(cellWidth, cellHeight) * 0.14;
  const busbar = Math.max(2, cellHeight * 0.035);
  const finger = Math.max(2, Math.round(cellWidth / 48));

  const cellPath = (x: number, y: number) => {
    const path = new Path2D();
    path.moveTo(x + crop, y);
    path.lineTo(x + cellWidth - crop, y);
    path.lineTo(x + cellWidth, y + crop);
    path.lineTo(x + cellWidth, y + cellHeight - crop);
    path.lineTo(x + cellWidth - crop, y + cellHeight);
    path.lineTo(x + crop, y + cellHeight);
    path.lineTo(x, y + cellHeight - crop);
    path.lineTo(x, y + crop);
    path.closePath();
    return path;
  };

  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const x = frame + gap + column * (cellWidth + gap);
      const y = frame + gap + row * (cellHeight + gap);
      const path = cellPath(x, y);

      // Deep blue-violet cells with a small per-cell hue and lightness jitter.
      const [lightnessMin, lightnessMax] = layout.lightness;
      const hue = 221 + random() * 8 + gaussianSample(random) * 3;
      const lightness =
        lightnessMin + random() * (lightnessMax - lightnessMin) + gaussianSample(random) * 1.2;
      albedo.fillStyle = `hsl(${hue.toFixed(1)} 62% ${lightness.toFixed(1)}%)`;
      albedo.fill(path);
      emissive.fillStyle = "#1b2b6e";
      emissive.fill(path);
      const tiltX = Math.round(
        128 + MathUtils.clamp(gaussianSample(random) * 0.01, -0.03, 0.03) * 127,
      );
      const tiltY = Math.round(
        128 + MathUtils.clamp(gaussianSample(random) * 0.01, -0.03, 0.03) * 127,
      );
      normal.fillStyle = `rgb(${tiltX},${tiltY},255)`;
      normal.fill(path);
      // Cover glass: a broad, faint sheen. The sun's mirror glint is drawn separately as a band.
      orm.fillStyle = `rgb(255,${Math.round(0.5 * 255)},0)`;
      orm.fill(path);

      // Fine fingers across the cell, then two busbars along it.
      albedo.save();
      albedo.clip(path);
      albedo.fillStyle = "rgba(150,160,190,0.07)";
      for (let fx = x + finger; fx < x + cellWidth; fx += cellWidth / 24) {
        albedo.fillRect(Math.round(fx), y, finger, cellHeight);
      }
      albedo.restore();
      for (const fraction of [1 / 3, 2 / 3]) {
        const by = Math.round(y + cellHeight * fraction - busbar / 2);
        albedo.fillStyle = "#c8cbd0";
        albedo.fillRect(x, by, cellWidth, busbar);
        emissive.fillStyle = "#000000";
        emissive.fillRect(x, by, cellWidth, busbar);
        orm.fillStyle = `rgb(255,${Math.round(0.3 * 255)},0)`;
        orm.fillRect(x, by, cellWidth, busbar);
      }
    }
  }

  return {
    albedo: configureCanvasTexture(albedo.canvas, true, anisotropy),
    emissive: configureCanvasTexture(emissive.canvas, true, anisotropy),
    normal: configureCanvasTexture(normal.canvas, false, anisotropy),
    orm: configureCanvasTexture(orm.canvas, false, anisotropy),
  };
}

/** Optical solar reflector (radiator mirror tiles) maps. */
export interface OsrTextures {
  /** Per-tile tilt normal map. */
  readonly normal: CanvasTexture;
  /** R = occlusion (dark seams), G = roughness, B = 1. */
  readonly orm: CanvasTexture;
}

/**
 * Draws 5 x 7 mirror tiles with slightly different tilts and dark seams.
 *
 * @param size - Texture size in texels (square).
 * @param anisotropy - Anisotropic filtering level.
 * @returns Normal and occlusion/roughness maps.
 */
export function createOsrTextures(size: number, anisotropy: number): OsrTextures {
  const random = mulberry32(0x05e);
  const normal = createCanvas(size, size);
  const orm = createCanvas(size, size);
  normal.fillStyle = "rgb(128,128,255)";
  normal.fillRect(0, 0, size, size);
  orm.fillStyle = `rgb(90,${Math.round(0.6 * 255)},255)`;
  orm.fillRect(0, 0, size, size);

  const columns = 5;
  const rows = 7;
  const seam = Math.max(2, Math.round(size / 160));
  const tileWidth = size / columns;
  const tileHeight = size / rows;
  // Tile tilts of about 0.8 degrees (sigma), so neighbouring mirrors catch the light differently.
  const tilt = () =>
    Math.round(128 + MathUtils.clamp(gaussianSample(random) * 0.014, -0.04, 0.04) * 127);
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const x = Math.round(column * tileWidth) + seam;
      const y = Math.round(row * tileHeight) + seam;
      const w = Math.round(tileWidth) - seam * 2;
      const h = Math.round(tileHeight) - seam * 2;
      normal.fillStyle = `rgb(${tilt()},${tilt()},255)`;
      normal.fillRect(x, y, w, h);
      orm.fillStyle = `rgb(255,${Math.round(0.05 * 255)},255)`;
      orm.fillRect(x, y, w, h);
    }
  }

  return {
    normal: configureCanvasTexture(normal.canvas, false, anisotropy),
    orm: configureCanvasTexture(orm.canvas, false, anisotropy),
  };
}

/**
 * Soft round glow for additive sprites (used instead of bloom on the low preset).
 *
 * @returns A 128 x 128 white radial falloff in the alpha channel.
 */
export function createGlowTexture(): CanvasTexture {
  const size = 128;
  const context = createCanvas(size, size);
  const gradient = context.createRadialGradient(
    size / 2,
    size / 2,
    0,
    size / 2,
    size / 2,
    size / 2,
  );
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.2, "rgba(255,255,255,0.55)");
  gradient.addColorStop(0.5, "rgba(255,255,255,0.12)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, size, size);
  return new CanvasTexture(context.canvas);
}
