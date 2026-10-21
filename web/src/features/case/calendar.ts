// The day chooser's calendar (the case file's date, and Compare): the months that hold passes, each
// as weeks from Monday, the passes of each day, and where a key moves among the days with a pass.
// Days are ISO dates ("2026-06-15"), read in UTC so no time zone shifts them.

/** A key the calendar moves by. */
export type CalendarKey = "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown" | "Home" | "End";

/** The keys {@link stepDay} handles. */
export const CALENDAR_KEYS: ReadonlySet<string> = new Set<CalendarKey>([
  "ArrowLeft",
  "ArrowRight",
  "ArrowUp",
  "ArrowDown",
  "Home",
  "End",
]);

const DAY_MS = 86_400_000;

const toTime = (day: string) => Date.parse(`${day}T00:00:00Z`);
const toDay = (time: number) => new Date(time).toISOString().slice(0, 10);

/**
 * The month of a day.
 *
 * @param day - An ISO day.
 * @returns Its "YYYY-MM".
 */
export function monthOf(day: string): string {
  return day.slice(0, 7);
}

/**
 * A day moved by whole days.
 *
 * @param day - An ISO day.
 * @param days - How many days (negative: earlier).
 * @returns The ISO day.
 */
export function addDays(day: string, days: number): string {
  return toDay(toTime(day) + days * DAY_MS);
}

/**
 * The passes of each day, in series order (two satellites may pass on the same day).
 *
 * @param series - The year's passes.
 * @returns ISO day to the indices of its passes.
 */
export function passDays(series: readonly { readonly date: string }[]): Map<string, number[]> {
  const out = new Map<string, number[]>();
  series.forEach((row, index) => {
    const list = out.get(row.date);
    if (list === undefined) {
      out.set(row.date, [index]);
    } else {
      list.push(index);
    }
  });
  return out;
}

/**
 * Every month from the first day's to the last's, so a month with no pass can still be shown.
 *
 * @param days - ISO days, in any order.
 * @returns The months ("YYYY-MM"), oldest first (empty with no day).
 */
export function passMonths(days: Iterable<string>): string[] {
  const sorted = [...days].sort();
  const first = sorted[0];
  const last = sorted.at(-1);
  if (first === undefined || last === undefined) {
    return [];
  }
  const out: string[] = [];
  let [year, month] = monthOf(first).split("-").map(Number) as [number, number];
  const end = monthOf(last);
  for (;;) {
    const key = `${String(year)}-${String(month).padStart(2, "0")}`;
    out.push(key);
    if (key >= end) {
      return out;
    }
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
}

/**
 * A month as weeks from Monday.
 *
 * @param month - "YYYY-MM".
 * @returns Each week's seven cells: an ISO day of the month, or null before or after it.
 */
export function monthWeeks(month: string): (string | null)[][] {
  const first = `${month}-01`;
  const lead = (new Date(toTime(first)).getUTCDay() + 6) % 7; // Monday 0 … Sunday 6
  const cells: (string | null)[] = Array.from({ length: lead }, () => null);
  for (let day = first; monthOf(day) === month; day = addDays(day, 1)) {
    cells.push(day);
  }
  while (cells.length % 7 !== 0) {
    cells.push(null);
  }
  const weeks: (string | null)[][] = [];
  for (let k = 0; k < cells.length; k += 7) {
    weeks.push(cells.slice(k, k + 7));
  }
  return weeks;
}

/**
 * Where a key moves among the days with a pass: left and right to the previous and next such day;
 * up and down to the nearest one at least a week earlier or later; Home and End to the month's
 * first and last.
 *
 * @param days - The days with a pass, sorted.
 * @param day - The day the focus is on.
 * @param key - The key.
 * @returns The day to move to (null: nowhere to go).
 */
export function stepDay(days: readonly string[], day: string, key: CalendarKey): string | null {
  switch (key) {
    case "ArrowLeft":
      return days.filter((d) => d < day).at(-1) ?? null;
    case "ArrowRight":
      return days.find((d) => d > day) ?? null;
    case "ArrowUp": {
      const limit = addDays(day, -7);
      return days.filter((d) => d <= limit).at(-1) ?? null;
    }
    case "ArrowDown": {
      const limit = addDays(day, 7);
      return days.find((d) => d >= limit) ?? null;
    }
    case "Home":
      return days.find((d) => monthOf(d) === monthOf(day)) ?? null;
    case "End":
      return days.filter((d) => monthOf(d) === monthOf(day)).at(-1) ?? null;
  }
}
