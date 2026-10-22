// Loads a reach's files once per reach, shared by the cases screen and the case view: from the
// daily run's published copy (the repository's data branch, docs/release.md) when it can be read,
// else from this build's snapshot under /data/reaches/<id>/ (the pipeline's committed examples,
// see vite.config.ts). The data say which they came from.
import type { HeadSignature } from "../chain/mldsa.ts";
import type { ProofEntry } from "../chain/witness.ts";
import { parseChecks, parseContext, parseThermalChecks } from "./checks.ts";
import type {
  AlongPass,
  AlongPlan,
  ClimateRecord,
  HistoryRow,
  MapsIndex,
  ModelCard,
  Outcome,
  ReachData,
  ReachGeometry,
  ReachInfo,
  SeriesRow,
  TemperatureCard,
  ThermalRow,
} from "./types.ts";

/** The daily run's published files: the repository's data branch, read raw. */
export const LIVE_ROOT = "https://raw.githubusercontent.com/saulo1112/RiverEtch/data/";

// A build can opt out (VITE_RIVERETCH_LIVE=off), e.g. to show its own snapshot only.
const LIVE = import.meta.env.VITE_RIVERETCH_LIVE !== "off";

/**
 * Where the daily run publishes a reach's files.
 *
 * @param id - The reach's site id.
 * @returns A URL ending with a slash.
 */
export function liveBase(id: string): string {
  return `${LIVE_ROOT}docs/water-quality/reach/${id}/examples/`;
}

/**
 * The folder a reach's files are served from.
 *
 * @param id - The reach's site id.
 * @returns A URL path ending with a slash.
 */
export function reachBase(id: string): string {
  return `${import.meta.env.BASE_URL}data/reaches/${id}/`;
}

// A missing file is null: a 404, or the app's own page from a host that falls back to it.
async function fetchText(url: string): Promise<string | null> {
  try {
    const response = await fetch(url);
    const html = response.headers.get("content-type")?.startsWith("text/html") ?? false;
    return response.ok && !html ? await response.text() : null;
  } catch {
    return null;
  }
}

async function fetchJson<T>(url: string): Promise<T | null> {
  const text = await fetchText(url);
  try {
    return text === null ? null : (JSON.parse(text) as T);
  } catch {
    return null;
  }
}

// A JSON Lines file's records (a line that does not parse is left out).
function jsonLines<T>(text: string | null): T[] {
  return (text ?? "").split("\n").flatMap((line) => {
    if (line.trim() === "") {
      return [];
    }
    try {
      return [JSON.parse(line) as T];
    } catch {
      return [];
    }
  });
}

const loads = new Map<string, Promise<ReachData>>();

/**
 * Loads a reach's info, series, card, gauge check, map index, geometry, the gauge's readings, its
 * climate context, its prospective outcomes and, where it has them, its water temperatures
 * (cached; a failed load is retried on the next call).
 * The info and the series are required; any other file may be missing.
 *
 * @param id - The reach's site id.
 * @returns The data.
 */
export function loadReach(id: string): Promise<ReachData> {
  const cached = loads.get(id);
  if (cached !== undefined) {
    return cached;
  }
  const pending = (async (): Promise<ReachData> => {
    const live = LIVE ? await fetchJson<SeriesRow[]>(`${liveBase(id)}series.json`) : null;
    const source = live === null ? "snapshot" : "live";
    const base = live === null ? reachBase(id) : liveBase(id);
    const [info, series, maps, geometry, checks, context, climate, outcomes, plan, along, history] =
      await Promise.all([
        fetchJson<ReachInfo>(`${base}reach.json`),
        live ?? fetchJson<SeriesRow[]>(`${base}series.json`),
        fetchJson<MapsIndex>(`${base}maps.json`),
        fetchJson<ReachGeometry>(`${base}geometry.geojson`),
        fetchText(`${base}checks/checks.csv`),
        fetchText(`${base}checks/context.csv`),
        fetchJson<ClimateRecord>(`${base}climate.json`),
        // The snapshot asks only for files this build has; the live copy may have newer ones.
        source === "live" || __OUTCOMES__.includes(id)
          ? fetchText(`${base}outcomes/ledger.jsonl`)
          : null,
        // Along the river and the station's earlier years (absent until the reach has them).
        fetchJson<AlongPlan>(`${base}along/windows.json`),
        fetchJson<AlongPass[]>(`${base}along/series.json`),
        fetchJson<HistoryRow[]>(`${base}history.json`),
      ]);
    if (info === null || series === null) {
      throw new Error(`${id}: the reach's files could not be loaded`);
    }
    // Water temperature (v6) only where reach.json names its card.
    const cardPath = info.cards.turbidity;
    const tempPath = info.cards.water_temperature;
    const [card, tempCard, thermal, thermalChecks] = await Promise.all([
      cardPath === undefined ? null : fetchJson<ModelCard>(`${base}${cardPath}`),
      tempPath === undefined ? null : fetchJson<TemperatureCard>(`${base}${tempPath}`),
      tempPath === undefined ? null : fetchJson<ThermalRow[]>(`${base}thermal/series.json`),
      tempPath === undefined ? null : fetchText(`${base}thermal/checks.csv`),
    ]);
    return {
      base,
      source,
      info,
      series,
      card,
      checks: checks === null ? [] : parseChecks(checks),
      maps,
      geometry,
      thermal:
        thermal === null
          ? null
          : {
              series: thermal,
              checks: thermalChecks === null ? [] : parseThermalChecks(thermalChecks),
              card: tempCard,
            },
      context: context === null ? [] : parseContext(context),
      climate,
      outcomes: jsonLines<Outcome>(outcomes),
      along: plan === null || along === null ? null : { plan, passes: along },
      history,
    };
  })();
  loads.set(id, pending);
  pending.catch(() => {
    loads.delete(id);
  });
  return pending;
}

/** The daily run's status (`status.json` on the data branch, pipeline/src/climate_pipeline/status.py). */
export interface RunStatus {
  readonly updatedUtc: string;
  readonly run: { readonly url: string; readonly ok: boolean };
  readonly lastSuccessUtc: string | null;
  readonly lastSealed: {
    readonly reach: string;
    readonly sceneId: string;
    readonly date: string;
  } | null;
  readonly lastAnchor: {
    readonly label: string;
    readonly lines: number;
    readonly block: number;
    readonly timestampUtc: string;
    readonly tx: string;
  } | null;
  readonly lastBitcoin: {
    readonly file: string;
    readonly height: number;
    readonly blockTime: string | null;
  } | null;
  readonly pendingBitcoin: number;
  readonly proofs?: readonly ProofEntry[];
  readonly failures: readonly {
    readonly utc: string;
    readonly run: string;
    readonly step: string;
    readonly exit: number;
    readonly reason: string;
  }[];
}

/**
 * The daily run's status, read live (null when the data branch cannot be read).
 *
 * @returns The status.
 */
export function loadStatus(): Promise<RunStatus | null> {
  return LIVE ? fetchJson<RunStatus>(`${LIVE_ROOT}status.json`) : Promise.resolve(null);
}

/**
 * The signatures of ledger heads (`docs/ledgers/signatures.jsonl` on the data branch).
 *
 * @returns Its lines (empty when none is published or it cannot be read).
 */
export async function loadSignatures(): Promise<HeadSignature[]> {
  return LIVE
    ? jsonLines<HeadSignature>(await fetchText(`${LIVE_ROOT}docs/ledgers/signatures.jsonl`))
    : [];
}

/**
 * A published proof's bytes.
 *
 * @param file - Its path on the data branch.
 * @returns The bytes (null when it cannot be read).
 */
export async function loadProof(file: string): Promise<Uint8Array | null> {
  try {
    const response = await fetch(`${LIVE_ROOT}${file}`);
    return response.ok ? new Uint8Array(await response.arrayBuffer()) : null;
  } catch {
    return null;
  }
}

/**
 * Fetches a file of a reach as text (a record, the ledger, a card), for verification.
 *
 * @param base - The reach's folder ({@link reachBase}).
 * @param path - The file, relative to it.
 * @returns Its text.
 */
export async function loadText(base: string, path: string): Promise<string> {
  const text = await fetchText(`${base}${path}`);
  if (text === null) {
    throw new Error(`${path} could not be loaded`);
  }
  return text;
}
