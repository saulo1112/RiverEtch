// Every string of the case view, and the formatters its panels share. A value in FNU appears only
// with its level, its interval and the error its locked test measured; NDTI stays relative.
import type { Level } from "../reaches/types.ts";

/** Labels of the case view. */
export const CASE_COPY = {
  back: "Back to your cases",
  caseFile: "Case file",
  pipelineChip: "Pipeline records · 2026",
  scenePrefix: "Sentinel-2 pass",
  turbidity: "Turbidity at the gauge",
  interval: "90 % interval",
  gaugeAt: "USGS gauge at the overpass",
  gaugeNone: "no gauge value at the overpass",
  gaugeLink: "Gauge page (USGS)",
  noValue: "No value for this pass",
  rangeWithoutLevel:
    "The prediction fell in a range the locked test did not rate, so no value is published.",
  validation: {
    lead: "Locked test",
    error: "typical error",
    on: "on",
    overpasses: "overpasses it never saw",
    baseline: "Median of past values",
  },
  record: {
    title: "Record",
    scene: "Scene",
    images: "Sentinel-2 images",
    processing: "Processing",
    code: "Code",
    card: "Model card",
    seal: "Record SHA-256",
    verify: "Verify this record",
    verifying: "Verifying…",
    alter: "Alter one value first",
    download: "Download the record (JSON)",
    sealed: "Its content matches its seal (SHA-256)",
    broken: "Its content no longer matches its seal",
    inLedger: "Listed in the reach's ledger",
    notInLedger: "Not found in the ledger",
    chain: "Ledger chain intact",
    chainBroken: "Ledger chain broken",
    lines: "lines",
    cardOk: "Model card matches the hash the record names",
    cardBad: "Model card does not match the hash the record names",
    altered: "Changed in memory",
    notAnchored: "Not anchored on a public chain yet: the seal and the ledger are checked here.",
    failed: "The record could not be checked.",
  },
  legendTitle: "NDTI per pixel (relative)",
  legendLow: "Low",
  legendHigh: "High",
  legendRange: "within this reach's 2026 passes",
  noData: "Cloud, glint or no data on this pass",
  parts: "Sub-reaches each record measures",
  window: "The gauge window (where turbidity is estimated)",
  timelineTitle: "Turbidity, 2026",
  timelineSatellite: "Satellite estimate (FNU) and its 90 % interval",
  timelineGauge: "USGS gauge at the overpass (provisional)",
  timelineNoValue: "Pass without a value",
  timelineHint: "Select a pass to see its map and record.",
  externalHint: "(opens in a new tab)",
  mapUnavailable: "The map could not load in this browser.",
  loading: "Loading the reach…",
  loadFailed: "The reach's records could not be loaded.",
  announceCase: "Case file:",
  announceBack: "Back to your cases.",
} as const;

/** How each level reads on a panel. */
export const LEVEL_LABELS = {
  validated: "Validated",
  estimated: "Estimated",
  indicative: "Indicative",
  none: "No level",
} as const satisfies Record<Level, string>;

const dayMonth = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const dayMonthYear = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/**
 * Formats an ISO date (`YYYY-MM-DD`) for the panels.
 *
 * @param isoDate - The date.
 * @param withYear - Also show the year.
 * @returns E.g. "14 Mar" or "14 Mar 2025".
 */
export function formatDate(isoDate: string, withYear = false): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  return (withYear ? dayMonthYear : dayMonth).format(date);
}

/**
 * Formats a number with an explicit sign (and a true minus sign).
 *
 * @param value - The number.
 * @param digits - Decimal places.
 * @returns E.g. "+0.11" or "−0.04".
 */
export function formatSigned(value: number, digits: number): string {
  const text = Math.abs(value).toFixed(digits);
  return value < 0 ? `−${text}` : `+${text}`;
}

/**
 * Formats a turbidity value for a panel: one decimal under 100, none above.
 *
 * @param value - The value.
 * @returns E.g. "30.5" or "124".
 */
export function formatValue(value: number): string {
  return value < 100 ? value.toFixed(1) : value.toFixed(0);
}

/**
 * Whole days from one ISO date to another.
 *
 * @param from - Start date.
 * @param to - End date.
 * @returns `to - from` in days.
 */
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}
