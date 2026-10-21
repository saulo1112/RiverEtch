import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, normalize, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

import { packStation } from "./src/features/hero/ui/how/flow.ts";

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
// The passes a ledger seals: its distinct scenes (a pass read again with a newer card adds a
// line, not a pass), else its lines (a ledger whose lines name no scene).
function passCount(path: string): number {
  if (!existsSync(path)) {
    return 0;
  }
  const lines = readFileSync(path, "utf8")
    .split("\n")
    .filter((line) => line.trim() !== "")
    .map((line) => JSON.parse(line) as { sceneId?: string; file?: string });
  return new Set(lines.map((l, k) => l.sceneId ?? l.file ?? String(k))).size;
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
      passCount(join(folder, "ledger.jsonl")) + passCount(join(folder, "thermal", "ledger.jsonl"));
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
// The key that signs ledger heads (frozen in docs/ledgers/frozen-artifacts.jsonl).
const mlDsaKey = (
  JSON.parse(
    readFileSync(fileURLToPath(new URL("../docs/keys/ml-dsa-65.json", import.meta.url)), "utf8"),
  ) as { publicKey: string }
).publicKey;
// The test on rivers the model never saw (preregistration-transfer.md), run once.
const transferScores = readFileSync(join(RESULTS, "transfer", "transfer_scores.csv"), "utf8");
// Published measurements beside a reach with no station (docs/water-quality/published/<reach>.json):
// looked up after its readings were known, labelled so, and named by no record.
const PUBLISHED = fileURLToPath(new URL("../docs/water-quality/published/", import.meta.url));
const published = existsSync(PUBLISHED)
  ? Object.fromEntries(
      readdirSync(PUBLISHED)
        .filter((name) => name.endsWith(".json"))
        .map((name) => [
          name.replace(/\.json$/, ""),
          JSON.parse(readFileSync(join(PUBLISHED, name), "utf8")) as unknown,
        ]),
    )
  : {};
// Its pooled result on the sediment-carrying rivers: the class agreement an ungauged reach states.
const transferPooled = JSON.parse(
  readFileSync(join(RESULTS, "transfer", "transfer_pooled.json"), "utf8"),
) as { class_agreement: number; n: number };
// The four-class test (preregistration-four-classes.md), run once: whether the ungauged reaches
// show four classes, and the counts the chapter states (null before it ran).
const fourPath = join(RESULTS, "four-classes", "four_classes.json");
const fourClasses = existsSync(fourPath)
  ? (JSON.parse(readFileSync(fourPath, "utf8")) as {
      passes: boolean;
      model_matched: number;
      baseline_matched: number;
      n: number;
    })
  : null;
// "How it works": the two gauged demo stations' daily flow through the satellite years, their
// low-flow and high-flow lines and the satellite's usable passes, packed at build time by
// src/features/hero/ui/how/flow.ts (the tests run it on the full files and recount every year
// against climate.json).
const HOW_SITES = ["mississippi-belle-chasse", "platte-louisville"];
const v5Passes = readFileSync(
  fileURLToPath(new URL("../docs/water-quality/inputs/usgs-v5/turbidity.csv", import.meta.url)),
  "utf8",
);
const howFlow = HOW_SITES.map((site) =>
  packStation(
    readFileSync(join(REACHES, site, "examples", "climate.json"), "utf8"),
    readFileSync(join(REACHES, site, "climate", "daily.csv"), "utf8"),
    v5Passes,
  ),
).filter((station) => station !== null);

// "How it works": what the turbidity models learned from, read from the committed cards: the most
// satellite-station pairs a station's model learned from, and the no-station model's trees and
// pairs (docs/water-quality/ungauged/mississippi-st-joseph/turbidity.json, the A4 model).
const MODELS = join(RESULTS, "models");
const modelPairs = readdirSync(MODELS)
  .map((site) => join(MODELS, site, "turbidity.json"))
  .filter((path) => existsSync(path))
  .map((path) => JSON.parse(readFileSync(path, "utf8")) as { trainingPairs?: { usgs?: number } })
  .flatMap((card) =>
    typeof card.trainingPairs?.usgs === "number" ? [card.trainingPairs.usgs] : [],
  );
const noStationCard = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL(
        "../docs/water-quality/ungauged/mississippi-st-joseph/turbidity.json",
        import.meta.url,
      ),
    ),
    "utf8",
  ),
) as { chosen: { n_estimators: number }; trainingPairs: { usgs: number; groups: number } };
const howModels = {
  maxPairs: Math.max(...modelPairs),
  trees: noStationCard.chosen.n_estimators,
  pairs: noStationCard.trainingPairs.usgs,
  groups: noStationCard.trainingPairs.groups,
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
    __TRANSFER_SCORES__: JSON.stringify(transferScores),
    __PUBLISHED__: JSON.stringify(published),
    __HOW_FLOW__: JSON.stringify(howFlow),
    __HOW_MODELS__: JSON.stringify(howModels),
    __TRANSFER_POOLED__: JSON.stringify(transferPooled),
    __FOUR_CLASSES__: JSON.stringify(fourClasses),
    __ML_DSA_PUBLIC_KEY__: JSON.stringify(mlDsaKey),
  },
});
