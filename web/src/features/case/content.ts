// Every string of the case view, and the formatters its panels share.

/** Labels of the case view. */
export const CASE_COPY = {
  back: "Back to the globe",
  placeholderSite: "Placeholder site",
  alertTitle: "Anomaly detected",
  illustrativeChip: "Illustrative data",
  illustrativeLabel: "Illustrative sample data",
  scenePrefix: "Sentinel-2 scene",
  rows: {
    anomaly: "Turbidity anomaly",
    rainfall: "Rainfall upstream",
    delta: "Upstream vs downstream",
  },
  challenge: "Challenge operator",
  challengeHint: "Not available yet",
  legendTitle: "NDTI (relative index)",
  legendLow: "Low",
  legendHigh: "High",
  noData: "Cloud / no data",
  timelineTitle: "Scenes and rainfall",
  laneScenes: "NDTI downstream, per scene",
  laneRain: "Rainfall upstream, mm per day",
  onset: "Anomaly onset",
  cloudy: "cloud / no data",
  externalHint: "(opens in a new tab)",
  mapUnavailable: "The map could not load in this browser.",
  announceCase: "Case view:",
  announceBack: "Back to the globe.",
} as const;

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
