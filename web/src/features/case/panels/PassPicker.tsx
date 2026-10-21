import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { platformName, turbidity } from "../../reaches/scene.ts";
import type { ReachData, SeriesRow } from "../../reaches/types.ts";
import { focusForVisitor } from "../../ui/modality.ts";
import {
  CALENDAR_KEYS,
  monthOf,
  monthWeeks,
  passDays,
  passMonths,
  stepDay,
  type CalendarKey,
} from "../calendar.ts";
import { CASE_COPY, formatDate, formatValue } from "../content.ts";

const copy = CASE_COPY.calendar;

/** Props of {@link PassPicker}. */
export interface PassPickerProps {
  readonly reach: ReachData;
  /** The pass shown as chosen (null: none yet). */
  readonly selected: number | null;
  /** A pass that cannot be chosen (Compare: the one already on the map). */
  readonly disabled?: number | null;
  /** A pass chosen; `done` is false while its day has another pass the visitor may still pick. */
  readonly onPick: (index: number, done: boolean) => void;
  readonly label: string;
  /** Move the focus to the chosen day once shown (a popover that just opened). */
  readonly autoFocus?: boolean;
}

// A pass's result in a few words: its value or class, or that it has none.
function result(row: SeriesRow): string {
  const estimate = turbidity(row);
  if (typeof estimate?.value === "number") {
    return `${formatValue(estimate.value)} ${estimate.unit}`;
  }
  if (estimate?.fnuClass != null) {
    return CASE_COPY.ungauged.classes[estimate.fnuClass];
  }
  return copy.noReading;
}

const hasReading = (row: SeriesRow | undefined) =>
  row !== undefined && result(row) !== copy.noReading;

const monthTitle = (month: string) =>
  new Date(`${month}-01T00:00:00Z`).toLocaleString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });

/**
 * The year's passes as a calendar: a month at a time, each day with a pass a button (a filled dot
 * when it has a reading, a ring when cloud, glint or the model's range left it without one), the
 * other days greyed. A day two satellites passed on lists both passes under the month. The arrow
 * keys move among the days with a pass, across months.
 *
 * @param props - The picker's props.
 * @param props.reach - The reach, with its year's passes.
 * @param props.selected - The pass shown as chosen.
 * @param props.disabled - A pass that cannot be chosen.
 * @param props.onPick - Called with a chosen pass.
 * @param props.label - The calendar's name.
 * @param props.autoFocus - Focus the chosen day once shown.
 * @returns The calendar.
 */
export function PassPicker({
  reach,
  selected,
  disabled = null,
  onPick,
  label,
  autoFocus = false,
}: PassPickerProps) {
  const { series } = reach;
  const byDay = useMemo(() => passDays(series), [series]);
  const sortedDays = useMemo(() => [...byDay.keys()].sort(), [byDay]);
  const months = useMemo(() => passMonths(sortedDays), [sortedDays]);
  // The days that can be chosen: a day whose only pass is the disabled one cannot.
  const pickDays = useMemo(
    () => sortedDays.filter((d) => (byDay.get(d) ?? []).some((k) => k !== disabled)),
    [sortedDays, byDay, disabled],
  );
  const anchor = series[selected ?? disabled ?? series.length - 1]?.date ?? sortedDays.at(-1);
  // The focus starts on the anchor's day, or the nearest one that can be chosen, in its month
  // when there is one.
  const near =
    anchor === undefined || pickDays.includes(anchor)
      ? []
      : [stepDay(pickDays, anchor, "ArrowLeft"), stepDay(pickDays, anchor, "ArrowRight")];
  const start =
    anchor === undefined || pickDays.includes(anchor)
      ? anchor
      : (near.find((d) => d !== null && monthOf(d) === monthOf(anchor)) ??
        near.find((d) => d !== null));
  const [month, setMonth] = useState(() =>
    start == null ? (anchor === undefined ? "" : monthOf(anchor)) : monthOf(start),
  );
  const [day, setDay] = useState<string | null>(() =>
    selected === null ? null : (series[selected]?.date ?? null),
  );
  const [focusDay, setFocusDay] = useState<string | null>(start ?? null);
  const rootRef = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef(autoFocus);

  // The focus follows the keys (and lands on the chosen day when the picker opens).
  useEffect(() => {
    if (!pendingFocus.current || focusDay === null) {
      return;
    }
    pendingFocus.current = false;
    focusForVisitor(rootRef.current?.querySelector<HTMLElement>(`[data-day="${focusDay}"]`));
  }, [focusDay, month]);

  const at = months.indexOf(month);
  const inMonth = pickDays.filter((d) => monthOf(d) === month);
  // One day of the month takes the Tab key: the focused day, else its first day with a pass.
  const tabDay = focusDay !== null && monthOf(focusDay) === month ? focusDay : inMonth[0];

  const choose = (iso: string) => {
    const passes = (byDay.get(iso) ?? []).filter((k) => k !== disabled);
    const first =
      passes.find((k) => k === selected) ?? passes.find((k) => hasReading(series[k])) ?? passes[0];
    if (first === undefined) {
      return;
    }
    setDay(iso);
    setFocusDay(iso);
    onPick(first, passes.length === 1);
  };

  const onKey = (event: KeyboardEvent<HTMLButtonElement>, iso: string) => {
    if (!CALENDAR_KEYS.has(event.key)) {
      return;
    }
    event.preventDefault();
    const next = stepDay(pickDays, iso, event.key as CalendarKey);
    if (next !== null) {
      pendingFocus.current = true;
      setFocusDay(next);
      setMonth(monthOf(next));
    }
  };

  const shown = day === null ? [] : (byDay.get(day) ?? []);
  return (
    <div className="case-calendar" ref={rootRef} role="group" aria-label={label}>
      <div className="case-calendar__head">
        <button
          type="button"
          className="case-calendar__nav"
          aria-label={copy.previous}
          disabled={at <= 0}
          onClick={() => {
            setMonth(months[at - 1] ?? month);
          }}
        >
          <ChevronLeft size={16} strokeWidth={1.8} aria-hidden="true" />
        </button>
        <p className="case-calendar__month" aria-live="polite">
          {monthTitle(month)}
        </p>
        <button
          type="button"
          className="case-calendar__nav"
          aria-label={copy.next}
          disabled={at < 0 || at >= months.length - 1}
          onClick={() => {
            setMonth(months[at + 1] ?? month);
          }}
        >
          <ChevronRight size={16} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </div>
      <table className="case-calendar__table">
        <caption className="case-visually-hidden">{monthTitle(month)}</caption>
        <thead>
          <tr>
            {copy.weekdays.map(([short, long]) => (
              <th key={long} scope="col" abbr={long}>
                {short}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {monthWeeks(month).map((week, w) => (
            <tr key={week.find((d) => d !== null) ?? String(w)}>
              {week.map((iso, d) => {
                if (iso === null) {
                  return <td key={`${String(w)}-${String(d)}`} />;
                }
                const passes = byDay.get(iso) ?? [];
                const number = Number(iso.slice(8));
                if (passes.length === 0) {
                  return (
                    <td key={iso}>
                      <span className="case-calendar__day" data-empty="true">
                        {number}
                      </span>
                    </td>
                  );
                }
                const rows = passes.map((k) => series[k]).filter((r) => r !== undefined);
                const words =
                  rows.length === 1
                    ? rows.map(result).join("")
                    : `${copy.passes(rows.length)}: ${rows.map(result).join(", ")}`;
                return (
                  <td key={iso}>
                    <button
                      type="button"
                      className="case-calendar__day"
                      data-day={iso}
                      data-read={rows.some(hasReading)}
                      data-selected={selected !== null && passes.includes(selected)}
                      aria-pressed={selected !== null && passes.includes(selected)}
                      aria-label={`${formatDate(iso, true)}: ${words}`}
                      tabIndex={iso === tabDay ? 0 : -1}
                      disabled={passes.every((k) => k === disabled)}
                      onClick={() => {
                        choose(iso);
                      }}
                      onKeyDown={(event) => {
                        onKey(event, iso);
                      }}
                    >
                      {number}
                      <span className="case-calendar__dot" aria-hidden="true" />
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {day === null || shown.length < 2 ? null : (
        <div
          className="case-calendar__passes"
          role="group"
          aria-label={copy.passesOn(shown.length, formatDate(day))}
        >
          <p className="case-calendar__passes-title">
            {copy.passesOn(shown.length, formatDate(day))}
          </p>
          {shown.map((k) => {
            const row = series[k];
            return row === undefined ? null : (
              <button
                key={row.sceneId}
                type="button"
                className="case-calendar__pass"
                aria-pressed={k === selected}
                disabled={k === disabled}
                onClick={() => {
                  onPick(k, true);
                }}
              >
                {platformName(row)} · {result(row)}
              </button>
            );
          })}
        </div>
      )}
      <p className="case-calendar__key">
        <span>
          <span className="case-calendar__swatch" data-read="true" aria-hidden="true" />
          {copy.keyRead}
        </span>
        <span>
          <span className="case-calendar__swatch" data-read="false" aria-hidden="true" />
          {copy.keyNone}
        </span>
        <span>{copy.keyEmpty}</span>
      </p>
    </div>
  );
}
