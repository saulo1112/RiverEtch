// Loads a reach's files from /data/reaches/<id>/ (served from the pipeline's committed examples,
// see vite.config.ts): once per reach, shared by the cases screen and the case view.
import { parseChecks, parseContext, parseThermalChecks } from "./checks.ts";
import type {
  MapsIndex,
  ModelCard,
  ReachData,
  ReachGeometry,
  ReachInfo,
  SeriesRow,
  TemperatureCard,
  ThermalRow,
} from "./types.ts";

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

const loads = new Map<string, Promise<ReachData>>();

/**
 * Loads a reach's info, series, card, gauge check, map index, geometry, the gauge's readings and,
 * where it has them, its water temperatures (cached; a failed load is retried on the next call).
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
  const base = reachBase(id);
  const pending = (async (): Promise<ReachData> => {
    const [info, series, maps, geometry, checks, context] = await Promise.all([
      fetchJson<ReachInfo>(`${base}reach.json`),
      fetchJson<SeriesRow[]>(`${base}series.json`),
      fetchJson<MapsIndex>(`${base}maps.json`),
      fetchJson<ReachGeometry>(`${base}geometry.geojson`),
      fetchText(`${base}checks/checks.csv`),
      fetchText(`${base}checks/context.csv`),
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
    };
  })();
  loads.set(id, pending);
  pending.catch(() => {
    loads.delete(id);
  });
  return pending;
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
