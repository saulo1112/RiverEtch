// Development-only timing marks for the flythrough (`window.__flightQA`), read by headless QA.
// Production builds drop the body: `import.meta.env.DEV` is a compile-time constant.

interface FlightQAWindow extends Window {
  __flightQA?: { marks: [string, number][] };
}

/**
 * Records a flythrough milestone with its `performance.now()` time (development builds only).
 *
 * @param label - Milestone name, e.g. `"crossfade"`.
 */
export function markFlight(label: string): void {
  if (!import.meta.env.DEV) {
    return;
  }
  const qa = window as FlightQAWindow;
  qa.__flightQA ??= { marks: [] };
  qa.__flightQA.marks.push([label, Math.round(performance.now())]);
}
