// Renders the reference case's card thumbnail from the real case view: starts the Vite dev server,
// opens the case map in its development-only capture mode (`?view=case&capture=thumb`: the map
// alone at the final pose, no panels, back button, wallet corner or attribution line), waits for
// an idle map with every tile loaded, screenshots it at 1920x960 and writes two WebP files
// (1920 and 960 px wide, each under 200 KB) to public/cases/.
//
// It needs the network: the imagery comes from EOX's Sentinel-2 cloudless tiles. Without them it
// writes nothing (never a black, partial or substitute image). It never uses `?tiles=stub`.
//
// Usage (from the repository root or web/): npm run capture:thumbnail -w web
/* global document, window, Image */
import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { createServer } from "vite";

const WEB = fileURLToPath(new URL("..", import.meta.url));
const OUT_DIR = fileURLToPath(new URL("../public/cases/", import.meta.url));
const VIEWPORT = { width: 1920, height: 960 };
const OUTPUTS = [
  { file: "magdalena-reference.webp", width: 1920, height: 960 },
  { file: "magdalena-reference-960.webp", width: 960, height: 480 },
];
const MAX_BYTES = 200 * 1024;
const IMAGERY_HOST = "tiles.maps.eox.at";
// The map must stay loaded, with every tile in and no camera motion, this long before the shot.
const SETTLE_MS = 2000;
const TIMEOUT_MS = 180_000;

// Playwright is not a dependency of the app: use a local install, else a global one.
async function loadChromium() {
  for (const name of ["playwright", "@playwright/test"]) {
    try {
      const module = await import(name);
      return module.chromium ?? module.default.chromium;
    } catch {
      // Try the next one.
    }
  }
  try {
    const root = execSync("npm root -g", { encoding: "utf8" }).trim();
    const require = createRequire(`${root}/`);
    return require(`${root}/playwright`).chromium;
  } catch {
    throw new Error(
      "Playwright not found. Install it (npm i -D playwright, or npm i -g playwright) and its " +
        "Chromium (npx playwright install chromium), then run this again.",
    );
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForIdleMap(page) {
  const deadline = Date.now() + TIMEOUT_MS;
  let stableSince = null;
  while (Date.now() < deadline) {
    const stats = await page.evaluate(() => window.__caseQA?.stats() ?? null);
    const idle = stats !== null && stats.loaded && stats.tilesLoaded && !stats.moving;
    if (!idle) {
      stableSince = null;
    } else if (stableSince === null) {
      stableSince = Date.now();
    } else if (Date.now() - stableSince >= SETTLE_MS) {
      return stats;
    }
    await sleep(250);
  }
  throw new Error(`The case map did not settle within ${String(TIMEOUT_MS / 1000)} s.`);
}

// Encodes the screenshot as WebP in the browser (no image library needed), stepping the quality
// down until the file fits.
async function encodeWebp(page, png, width, height) {
  return page.evaluate(
    async ({ base64, width, height, maxBytes }) => {
      const image = new Image();
      image.src = `data:image/png;base64,${base64}`;
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      context.imageSmoothingQuality = "high";
      context.drawImage(image, 0, 0, width, height);
      // Qualities 0.86, 0.82, ... 0.50; the last one is kept whatever its size.
      for (let step = 86; step >= 50; step -= 4) {
        const quality = step / 100;
        const blob = await new Promise((resolve) => {
          canvas.toBlob(resolve, "image/webp", quality);
        });
        if (blob === null || blob.type !== "image/webp") {
          throw new Error("This browser cannot encode WebP.");
        }
        if (blob.size <= maxBytes || step - 4 < 50) {
          const bytes = new Uint8Array(await blob.arrayBuffer());
          let binary = "";
          for (const byte of bytes) {
            binary += String.fromCharCode(byte);
          }
          return { base64: window.btoa(binary), quality, size: blob.size };
        }
      }
      throw new Error("unreachable");
    },
    { base64: png.toString("base64"), width, height, maxBytes: MAX_BYTES },
  );
}

async function main() {
  const chromium = await loadChromium();
  const server = await createServer({
    root: WEB,
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    logLevel: "warn",
    server: { host: "127.0.0.1", port: 5180 },
  });
  await server.listen();
  const base = server.resolvedUrls?.local[0];
  let browser = null;
  try {
    if (base === undefined) {
      throw new Error("The dev server did not report a URL.");
    }
    browser = await chromium.launch({
      headless: true,
      // Let a machine without a usable GPU fall back to software WebGL.
      args: ["--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"],
    });
    const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
    const page = await context.newPage();
    const imagery = { ok: 0, failed: 0 };
    page.on("response", (response) => {
      if (new URL(response.url()).hostname === IMAGERY_HOST) {
        if (response.ok()) {
          imagery.ok += 1;
        } else {
          imagery.failed += 1;
        }
      }
    });
    page.on("requestfailed", (request) => {
      if (new URL(request.url()).hostname === IMAGERY_HOST) {
        imagery.failed += 1;
      }
    });

    const url = new URL(base);
    url.search = "?view=case&capture=thumb";
    console.log(`Opening ${url.href}`);
    await page.goto(url.href);
    await page.waitForSelector('.case-view[data-capture="thumb"]', { timeout: 60_000 });
    const stats = await waitForIdleMap(page);
    // The river line's reveal finishes after the map first settles.
    await sleep(1500);

    if (imagery.ok === 0 || imagery.failed > 0) {
      throw new Error(
        `The imagery did not load from ${IMAGERY_HOST} (${String(imagery.ok)} tiles loaded, ` +
          `${String(imagery.failed)} failed). Nothing was written. Run this on a machine that ` +
          "can reach the EOX tile server.",
      );
    }

    const png = await page.locator(".case-view__map").screenshot({ type: "png" });
    mkdirSync(OUT_DIR, { recursive: true });
    for (const output of OUTPUTS) {
      const encoded = await encodeWebp(page, png, output.width, output.height);
      if (encoded.size > MAX_BYTES) {
        throw new Error(
          `${output.file} is ${String(encoded.size)} bytes even at the lowest quality.`,
        );
      }
      writeFileSync(`${OUT_DIR}${output.file}`, Buffer.from(encoded.base64, "base64"));
      console.log(
        `Wrote public/cases/${output.file}: ${String(output.width)}x${String(output.height)}, ` +
          `${String(Math.round(encoded.size / 1024))} KB (quality ${encoded.quality.toFixed(2)}).`,
      );
    }
    console.log(
      `Pose: zoom ${stats.zoom.toFixed(2)}, pitch ${stats.pitch.toFixed(1)}, bearing ` +
        `${stats.bearing.toFixed(1)}; ${String(imagery.ok)} imagery tiles.`,
    );
  } finally {
    await browser?.close();
    await server.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
