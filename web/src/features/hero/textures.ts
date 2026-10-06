import {
  CanvasTexture,
  ImageBitmapLoader,
  LinearMipmapLinearFilter,
  NoColorSpace,
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
