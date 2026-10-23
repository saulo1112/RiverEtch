import { ChevronLeft, ChevronRight } from "lucide-react";

import { CASE_COPY } from "../content.ts";
import { HelpTip } from "./HelpTip.tsx";

/** Props of {@link YearStep}. */
export interface YearStepProps {
  /** The years, newest first (the sealed year first). */
  readonly years: readonly number[];
  /** The year shown (or asked for, while it loads). */
  readonly year: number;
  readonly onYear: (year: number) => void;
  /** The group's name (default: which year the case shows). */
  readonly label?: string;
}

/**
 * The year above a calendar's month (the case file's date, and Compare): a step to an earlier or a
 * later year, and what that year is, sealed records or recomputed and not sealed (with a "?" that
 * says why, in plain words; its text opens under the row).
 *
 * @param props - The step's props.
 * @param props.years - The years, newest first.
 * @param props.year - The year shown.
 * @param props.onYear - Called with a year chosen.
 * @param props.label - The group's name.
 * @returns The step.
 */
export function YearStep({ years, year, onYear, label }: YearStepProps) {
  const copy = CASE_COPY.archive;
  const at = years.indexOf(year);
  const sealed = at === 0;
  return (
    <div className="case-calendar__years" role="group" aria-label={label ?? copy.yearLabel}>
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
      {sealed ? null : <HelpTip label={copy.whyLabel}>{copy.why}</HelpTip>}
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
