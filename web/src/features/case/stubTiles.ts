// DEVELOPMENT ONLY (`?tiles=stub`): a `stub://` tile protocol that draws tiles on a canvas, so the
// flythrough can be checked without network access to the imagery and terrain servers. Imagery is a
// dark checker labelled with its z/x/y; elevation is continuous Terrarium-encoded hills. Add
// `&tileDelay=<ms>` to make every tile arrive late, like over a slow network
// (`window.__stubTileDelay` overrides it at run time).
import { addProtocol } from "maplibre-gl";

const SIZE = 256;
const TAU = Math.PI * 2;

// Two octaves of hills over the Web Mercator square: ~60 km ridges and ~6 km hills (metres).
function elevation(worldX: number, worldY: number): number {
  const ridges = Math.sin(TAU * 670 * worldX) * Math.cos(TAU * 610 * worldY);
  const hills = Math.sin(TAU * 6700 * worldX + 1.3) * Math.sin(TAU * 6100 * worldY + 0.4);
  return 260 + 420 * ridges + 90 * hills;
}

function drawImagery(context: OffscreenCanvasRenderingContext2D, z: number, x: number, y: number) {
  const cell = SIZE / 8;
  for (let row = 0; row < 8; row += 1) {
    for (let column = 0; column < 8; column += 1) {
      context.fillStyle = (row + column + x + y) % 2 === 0 ? "#0c1724" : "#122133";
      context.fillRect(column * cell, row * cell, cell, cell);
    }
  }
  context.strokeStyle = "#2a4a73";
  context.lineWidth = 2;
  context.strokeRect(1, 1, SIZE - 2, SIZE - 2);
  context.fillStyle = "#6f93c6";
  context.font = "600 18px ui-monospace, monospace";
  context.fillText(`${z}/${x}/${y}`, 12, 28);
}

function drawElevation(
  context: OffscreenCanvasRenderingContext2D,
  z: number,
  x: number,
  y: number,
) {
  const image = context.createImageData(SIZE, SIZE);
  const scale = SIZE * 2 ** z;
  for (let py = 0; py < SIZE; py += 1) {
    for (let px = 0; px < SIZE; px += 1) {
      // Terrarium: height = R * 256 + G + B / 256 - 32768.
      const value = elevation((x * SIZE + px + 0.5) / scale, (y * SIZE + py + 0.5) / scale) + 32768;
      const offset = (py * SIZE + px) * 4;
      image.data[offset] = Math.floor(value / 256);
      image.data[offset + 1] = Math.floor(value) % 256;
      image.data[offset + 2] = Math.floor((value % 1) * 256);
      image.data[offset + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
}

interface StubTilesWindow extends Window {
  // QA can change the latency mid-session (e.g. a slow network only on the way back).
  __stubTileDelay?: number;
}

// The mean latency added to every stub tile: `window.__stubTileDelay` if set, else `?tileDelay=`.
function tileDelayMs(): number {
  const override = (window as StubTilesWindow).__stubTileDelay;
  const value = override ?? Number(new URLSearchParams(window.location.search).get("tileDelay"));
  return Number.isFinite(value) && value > 0 ? value : 0;
}

// Resolves after `ms`, or rejects with an AbortError when MapLibre cancels the request.
function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("Tile request aborted", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal.addEventListener("abort", abort, { once: true });
  });
}

/** Registers the `stub://imagery/{z}/{x}/{y}` and `stub://dem/{z}/{x}/{y}` tile protocol. */
export function registerStubTiles(): void {
  addProtocol("stub", async ({ url }, abortController) => {
    const delayMs = tileDelayMs();
    if (delayMs > 0) {
      // 0.5–1.5× the mean, so tiles trickle in out of order as they do over a network.
      await wait(delayMs * (0.5 + Math.random()), abortController.signal);
    }
    const match = /^stub:\/\/(imagery|dem)\/(\d+)\/(\d+)\/(\d+)/.exec(url);
    if (match === null) {
      throw new Error(`Unknown stub tile: ${url}`);
    }
    const [, kind, z, x, y] = match;
    const canvas = new OffscreenCanvas(SIZE, SIZE);
    const context = canvas.getContext("2d");
    if (context === null) {
      throw new Error("No 2D canvas for stub tiles.");
    }
    const [tz, tx, ty] = [Number(z), Number(x), Number(y)];
    if (kind === "dem") {
      drawElevation(context, tz, tx, ty);
    } else {
      drawImagery(context, tz, tx, ty);
    }
    const blob = await canvas.convertToBlob({ type: "image/png" });
    return { data: await blob.arrayBuffer() };
  });
}
