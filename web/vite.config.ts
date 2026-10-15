import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, normalize, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// The pipeline's committed files for the web (docs/water-quality/reach/README.md): each reach's
// examples folder, served as /data/reaches/<id>/ in development and copied there by the build, so
// the repository keeps one copy.
const REACHES = fileURLToPath(new URL("../docs/water-quality/reach/", import.meta.url));
const TYPES: Record<string, string> = {
  ".json": "application/json",
  ".geojson": "application/geo+json",
  ".jsonl": "application/jsonl",
  ".csv": "text/csv",
  ".png": "image/png",
  ".webp": "image/webp",
};

// The cases with a thumbnail, rendered by `npm run capture:thumbnail`
// (scripts/capture-case-thumbnail.mjs). Until both sizes exist a card draws the reach's outline
// and requests no image, so it never shows a broken image. Checked when Vite starts.
const thumbnails = readdirSync(REACHES).filter((site) =>
  [`${site}.webp`, `${site}-960.webp`].every((name) =>
    existsSync(fileURLToPath(new URL(`./public/cases/${name}`, import.meta.url))),
  ),
);

// The ledger anchor's Sepolia address, from Hardhat Ignition's committed deployment (null until
// it is deployed; VITE_LEDGER_ANCHOR_ADDRESS overrides it at runtime).
const DEPLOYMENT = fileURLToPath(
  new URL(
    "../contracts/ignition/deployments/chain-11155111/deployed_addresses.json",
    import.meta.url,
  ),
);
const ledgerAnchor: string | null = existsSync(DEPLOYMENT)
  ? ((JSON.parse(readFileSync(DEPLOYMENT, "utf8")) as Record<string, string>)[
      "LedgerAnchorModule#LedgerAnchor"
    ] ?? null)
  : null;

function examplesFile(path: string): string | null {
  const [site, ...rest] = path.split("/").filter(Boolean);
  if (site === undefined || rest.length === 0) {
    return null;
  }
  const file = normalize(join(REACHES, site, "examples", ...rest));
  const inside = !relative(join(REACHES, site, "examples"), file).startsWith("..");
  return inside && existsSync(file) && statSync(file).isFile() ? file : null;
}

function listFiles(folder: string): string[] {
  return readdirSync(folder, { recursive: true, encoding: "utf8" })
    .map((name) => join(folder, name))
    .filter((path) => statSync(path).isFile());
}

function reachData(): Plugin {
  const serve = (
    req: { url?: string },
    res: {
      statusCode: number;
      setHeader: (k: string, v: string) => void;
      end: (b?: Buffer) => void;
    },
  ) => {
    const path = decodeURIComponent((req.url ?? "").split("?")[0] ?? "");
    const file = examplesFile(path);
    // A file a reach does not have is missing, not the app's page.
    if (file === null) {
      res.statusCode = 404;
      res.end();
      return;
    }
    res.setHeader("Content-Type", TYPES[extname(file)] ?? "application/octet-stream");
    res.end(readFileSync(file));
  };
  return {
    name: "reach-data",
    configureServer(server) {
      server.middlewares.use("/data/reaches", serve);
    },
    configurePreviewServer(server) {
      server.middlewares.use("/data/reaches", serve);
    },
    generateBundle() {
      for (const site of readdirSync(REACHES)) {
        const folder = join(REACHES, site, "examples");
        if (!existsSync(folder)) {
          continue;
        }
        for (const file of listFiles(folder)) {
          const name = relative(folder, file).split(sep).join("/");
          this.emitFile({
            type: "asset",
            fileName: `data/reaches/${site}/${name}`,
            source: readFileSync(file),
          });
        }
      }
    },
  };
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), reachData()],
  define: {
    __CASE_THUMBNAILS__: JSON.stringify(thumbnails),
    __LEDGER_ANCHOR__: JSON.stringify(ledgerAnchor),
  },
});
