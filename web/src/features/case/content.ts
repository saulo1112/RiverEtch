// Every string of the case view, and the formatters its panels share.
import type { CaseClassification } from "./types.ts";

/** Labels of the case view. NDTI is relative: no physical units, causes or compliance claims. */
export const CASE_COPY = {
  back: "Back to your cases",
  caseFile: "Case file",
  syntheticNote: "(synthetic event)",
  illustrativeChip: "Illustrative data",
  illustrativeLabel: "Illustrative sample data",
  scenePrefix: "Sentinel-2 scene",
  rows: {
    departure: "Index departure",
    rainfall: "Rainfall upstream",
    delta: "Upstream vs downstream",
  },
  vsBaseline: "σ vs baseline",
  lastDay: "last day",
  relative: "relative",
  // Shown while no in-situ calibration has passed (always, for now): see units.ts.
  relativeNote: "Relative index: no physical units until calibrated in situ.",
  reply: "Operator reply (private)",
  replyHint: "Not available in this demo",
  record: {
    title: "Record",
    note: "Illustrative · not anchored in this demo",
    scene: "Scene",
    version: "Processing version",
    parameters: "Parameters",
    root: "Anchored root",
    placeholder: "illustrative",
    notAnchored: "not anchored in this demo",
    recompute: "Recompute this observation",
    recomputeHint: "Not available yet",
  },
  legendTitle: "NDTI (relative index)",
  legendLow: "Low",
  legendHigh: "High",
  noData: "Cloud / no data",
  timelineTitle: "Scenes and rainfall",
  laneScenes: "NDTI downstream, per scene",
  laneRain: "Rainfall upstream, mm per day",
  onset: "Departure onset",
  cloudy: "cloud / no data",
  externalHint: "(opens in a new tab)",
  mapUnavailable: "The map could not load in this browser.",
  announceCase: "Case file:",
  announceBack: "Back to your cases.",
} as const;

/** Maturity of the reference reach: one constant drives the chip and its explanation. */
export const CASE_MATURITY = {
  label: "Observable: index departures only",
  hint: "Maturity: Observable. Next come Baselined, then Validated in situ (calibrated, with a stated error).",
} as const;

/** The alert's title for each verdict. */
export const ALERT_TITLES = {
  normal: "No departure from the baseline",
  explained_by_climate: "Departure explained by rainfall",
  candidate_human_pressure: "Departure not explained by rainfall",
} as const satisfies Record<CaseClassification, string>;

/**
 * The alert's title for a verdict.
 *
 * @param classification - The verdict on the latest scene.
 * @returns E.g. "Departure not explained by rainfall".
 */
export function alertTitle(classification: CaseClassification): string {
  return ALERT_TITLES[classification];
}

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
 * Whole days from one ISO date to another.
 *
 * @param from - Start date.
 * @param to - End date.
 * @returns `to - from` in days.
 */
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}
