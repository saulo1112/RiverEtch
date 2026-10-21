import { CalendarDays } from "lucide-react";
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
 * @returns The button, and the calendar while it is open.
 */
export function DayChooser({ reach, selected, onSelect }: DayChooserProps) {
  const [place, setPlace] = useState<{ top: number; left: number; host: Element } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const open = place !== null;
  const date = reach.series[selected]?.date;

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
              <PassPicker
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
            </div>,
            place.host,
          )}
    </>
  );
}
