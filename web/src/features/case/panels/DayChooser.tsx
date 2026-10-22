import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { ReachData } from "../../reaches/types.ts";
import { focusForVisitor } from "../../ui/modality.ts";
import { CASE_COPY, formatDate } from "../content.ts";
import { PassPicker } from "./PassPicker.tsx";

const copy = CASE_COPY.calendar;
const WIDTH = 280; // the popover's width (CSS), to keep it on screen
const MARGIN = 8;

/** Props of {@link DayChooser}. */
export interface DayChooserProps {
  readonly reach: ReachData;
  /** Index of the selected pass. */
  readonly selected: number;
  readonly onSelect: (index: number) => void;
  /** The years the case can show, newest first (the sealed year first); one: no year control. */
  readonly years?: readonly number[];
  /** The year asked for (it may still be loading). */
  readonly year?: number;
  readonly onYear?: (year: number) => void;
}

// The year above the month: a step to an earlier or a later year, and what that year is.
function YearStep({
  years,
  year,
  onYear,
}: {
  readonly years: readonly number[];
  readonly year: number;
  readonly onYear: (year: number) => void;
}) {
  const copy = CASE_COPY.archive;
  const at = years.indexOf(year);
  const sealed = at === 0;
  return (
    <div className="case-calendar__years" role="group" aria-label={copy.yearLabel}>
      <button
        type="button"
        className="case-calendar__nav"
        aria-label={copy.earlier}
        disabled={at < 0 || at >= years.length - 1}
        onClick={() => {
          onYear(years[at + 1] ?? year);
        }}
      >
        <ChevronLeft size={16} strokeWidth={1.8} aria-hidden="true" />
      </button>
      <p className="case-calendar__year" aria-live="polite">
        <span className="case-calendar__year-number">{year}</span>
        <span className="case-calendar__year-note" data-sealed={sealed}>
          {sealed ? copy.sealedYear : copy.label}
        </span>
      </p>
      <button
        type="button"
        className="case-calendar__nav"
        aria-label={copy.later}
        disabled={at <= 0}
        onClick={() => {
          onYear(years[at - 1] ?? year);
        }}
      >
        <ChevronRight size={16} strokeWidth={1.8} aria-hidden="true" />
      </button>
    </div>
  );
}

/**
 * The selected pass's date as a button that opens the year's passes as a calendar, to see the
 * river on any day the satellite passed. The calendar is drawn over the map (the case file
 * scrolls, so it would clip it), under the button, and closes on a pick, a click outside,
 * Escape or a resize.
 *
 * @param props - The chooser's props.
 * @param props.reach - The reach, with its year's passes.
 * @param props.selected - Index of the selected pass.
 * @param props.onSelect - Called with the pass chosen.
 * @param props.years - The years the case can show, newest first.
 * @param props.year - The year asked for.
 * @param props.onYear - Called with a year chosen.
 * @returns The button, and the calendar while it is open.
 */
export function DayChooser({
  reach,
  selected,
  onSelect,
  years = [],
  year,
  onYear,
}: DayChooserProps) {
  const [place, setPlace] = useState<{ top: number; left: number; host: Element } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const open = place !== null;
  const date = reach.series[selected]?.date;
  // The year the calendar shows (the reach given may still be the year before the one asked for).
  const shownYear = Number((reach.series.at(-1)?.date ?? "2026").slice(0, 4));

  const close = (refocus: boolean) => {
    setPlace(null);
    if (refocus) {
      focusForVisitor(buttonRef.current);
    }
  };

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!popRef.current?.contains(target) && !buttonRef.current?.contains(target)) {
        setPlace(null);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPlace(null);
        focusForVisitor(buttonRef.current);
      }
    };
    const onResize = () => {
      setPlace(null);
    };
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
    };
  }, [open]);

  if (date === undefined) {
    return null;
  }
  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="case-file__date"
        aria-label={copy.choose(formatDate(date, true))}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => {
          if (open) {
            close(false);
            return;
          }
          const button = buttonRef.current;
          if (button !== null) {
            const rect = button.getBoundingClientRect();
            const width = Math.min(WIDTH, window.innerWidth - 2 * MARGIN);
            const left = Math.min(
              Math.max(MARGIN, rect.left - 12),
              window.innerWidth - width - MARGIN,
            );
            // Inside the case view, whose tokens (glass, type) it uses.
            const host = button.closest(".case-view") ?? document.body;
            setPlace({ top: rect.bottom + MARGIN, left, host });
          }
        }}
      >
        {formatDate(date, true)}
        <CalendarDays size={13} strokeWidth={1.8} aria-hidden="true" />
      </button>
      {place === null
        ? null
        : createPortal(
            <div
              ref={popRef}
              id={id}
              className="case-calendar-pop case-glass"
              style={{ top: `${String(place.top)}px`, left: `${String(place.left)}px` }}
            >
              {years.length > 1 && year !== undefined && onYear !== undefined ? (
                <YearStep years={years} year={year} onYear={onYear} />
              ) : null}
              {year !== undefined && shownYear !== year ? (
                <p className="case-calendar__loading">{CASE_COPY.archive.loading(String(year))}</p>
              ) : (
                <PassPicker
                  key={shownYear}
                  reach={reach}
                  selected={selected}
                  label={copy.label}
                  autoFocus
                  onPick={(index, done) => {
                    onSelect(index);
                    if (done) {
                      close(true);
                    }
                  }}
                />
              )}
            </div>,
            place.host,
          )}
    </>
  );
}
