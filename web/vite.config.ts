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

// Each reach's river and its sealed passes (the lines of its Sentinel-2 and Landsat ledgers), for
// the hero's evidence strip (src/features/hero/ui/evidence.ts). Counted when Vite starts.
function lineCount(path: string): number {
  return existsSync(path)
    ? readFileSync(path, "utf8")
        .split("\n")
        .filter((line) => line.trim() !== "").length
    : 0;
}
const reachFacts = Object.fromEntries(
  readdirSync(REACHES).flatMap((site) => {
    const folder = join(REACHES, site, "examples");
    const info = join(folder, "reach.json");
    if (!existsSync(info)) {
      return [];
    }
    const { river } = JSON.parse(readFileSync(info, "utf8")) as { river?: string };
    const sealed =
      lineCount(join(folder, "ledger.jsonl")) + lineCount(join(folder, "thermal", "ledger.jsonl"));
    return [[site, { river: river ?? site, sealed }]];
  }),
);

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

// The scoreboard's T0 (docs/water-quality/prospective.md): the block time of the first anchor of
// the frozen-artifacts ledger that covers the scoring rule's line, read from the anchoring log as
// `climate-pipeline reach score` reads it (null until the rule is anchored). Read when Vite starts.
const LEDGERS = fileURLToPath(new URL("../docs/ledgers/", import.meta.url));
function jsonLines<T>(path: string): T[] {
  return existsSync(path)
    ? readFileSync(path, "utf8")
        .split("\n")
        .filter((line) => line.trim() !== "")
        .map((line) => JSON.parse(line) as T)
    : [];
}
const ruleLine = jsonLines<{ path: string }>(join(LEDGERS, "frozen-artifacts.jsonl")).findIndex(
  (line) => line.path === "docs/water-quality/prospective.md",
);
const prospectiveT0: string | null =
  ruleLine < 0
    ? null
    : (jsonLines<{ label: string; lines: number; timestampUtc: string }>(
        join(LEDGERS, "anchors.jsonl"),
      )
        .filter((a) => a.label === "terrachain:riveretch:frozen-artifacts" && a.lines > ruleLine)
        .map((a) => a.timestampUtc)
        .sort()[0] ?? null);

// The reaches with an outcomes ledger (`reach score`), so the web requests only files that exist.
const outcomes = readdirSync(REACHES).filter((site) =>
  existsSync(join(REACHES, site, "examples", "outcomes", "ledger.jsonl")),
);

// The validation's results for the All rivers tab, as committed (parsed by
// src/features/case/rivers.ts, which the tests run on the same files).
const RESULTS = fileURLToPath(new URL("../docs/water-quality/results/", import.meta.url));
const v5Results = {
  levels: readFileSync(join(RESULTS, "v5_levels.csv"), "utf8"),
  scores: readFileSync(join(RESULTS, "v5_scores.csv"), "utf8"),
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), reachData()],
  define: {
    __CASE_THUMBNAILS__: JSON.stringify(thumbnails),
    __LEDGER_ANCHOR__: JSON.stringify(ledgerAnchor),
    __PROSPECTIVE_T0__: JSON.stringify(prospectiveT0),
    __OUTCOMES__: JSON.stringify(outcomes),
    __REACH_FACTS__: JSON.stringify(reachFacts),
    __V5_RESULTS__: JSON.stringify(v5Results),
  },
});
