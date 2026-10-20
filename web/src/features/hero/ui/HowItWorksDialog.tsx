import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { CASE_COPY } from "../../case/content.ts";
import { oneDecimal } from "../../case/rivers.ts";
import { HOW_IT_WORKS } from "./content.ts";
import { Fingerprint } from "./how/Fingerprint.tsx";
import { FlowChart } from "./how/FlowChart.tsx";
import { unpackStation } from "./how/flow.ts";
import { headline, neverSaw, ownRiver } from "./how/numbers.ts";
import { StationBars } from "./how/StationBars.tsx";
import "./how/how.css";

/** Props of {@link HowItWorksDialog}. */
export interface HowItWorksDialogProps {
  /** Shows the dialog (modal) while true. */
  readonly open: boolean;
  /** The dialog closed: Esc, the close button, a press on the backdrop, or `open` turning false. */
  readonly onClose: () => void;
  /** Opens a case (the "Try it" chapter). */
  readonly onOpenCase?: (caseId: string) => void;
}

const copy = HOW_IT_WORKS;
// Every number below comes from a committed file, cut or parsed at build time (vite.config.ts).
const FLOW = __HOW_FLOW__.map(unpackStation);
const HEADLINE = headline(__V5_RESULTS__.levels, __V5_RESULTS__.scores);
const NEVER = neverSaw(__TRANSFER_SCORES__);
const OWN = ownRiver(__V5_RESULTS__.levels, __V5_RESULTS__.scores);

function Problem() {
  return (
    <>
      <p className="how-lead">{copy.problem.lead}</p>
      <p className="how-text">{copy.problem.more}</p>
      {FLOW.length === 0 ? null : <FlowChart stations={FLOW} />}
    </>
  );
}

function Reads() {
  return (
    <>
      <div className="how-reads">
        {copy.reads.cards.map((c) => (
          <article key={c.title} className="how-read">
            <h3 className="how-read__title">{c.title}</h3>
            <p className="how-small">{c.term}</p>
            <p className="how-text">{c.text}</p>
            <p className="how-source">
              <a href={c.url} target="_blank" rel="noopener noreferrer">
                {c.source}
              </a>
            </p>
          </article>
        ))}
      </div>
      <div className="how-station">
        <h3 className="how-read__title">{copy.reads.stationTitle}</h3>
        <p className="how-text">{copy.reads.stationText}</p>
      </div>
    </>
  );
}

function Print() {
  return (
    <>
      <p className="how-lead">{copy.fingerprint.lead}</p>
      <Fingerprint />
      <h3 className="how-sub">{copy.fingerprint.boardsTitle}</h3>
      <ol className="how-boards">
        {copy.fingerprint.boards.map((b) => (
          <li key={b.title} className="how-board">
            <p className="how-board__title">{b.title}</p>
            <p className="how-text">{b.text}</p>
            <p className="how-small">{b.term}</p>
          </li>
        ))}
      </ol>
    </>
  );
}

function Works() {
  return (
    <>
      {HEADLINE === null ? null : (
        <div className="how-big">
          <p className="how-big__figure">
            <span className="how-big__about">{copy.works.bigAbout}</span>
            <span className="how-big__value">{HEADLINE.times}</span>
            <span className="how-big__unit">{copy.works.bigUnit}</span>
          </p>
          <div>
            <p className="how-big__label">{copy.works.bigLabel}</p>
            <p className="how-text">
              {copy.works.bigNote(
                CASE_COPY.rivers.names[HEADLINE.site] ?? HEADLINE.site,
                oneDecimal(HEADLINE.satellite),
                oneDecimal(HEADLINE.guess),
              )}
            </p>
            <p className="how-small">
              {copy.works.tally(HEADLINE.good, HEADLINE.none, HEADLINE.worse, HEADLINE.n)}
            </p>
          </div>
        </div>
      )}
      <StationBars never={NEVER} own={OWN} />
      <p className="how-text how-works__class">
        {copy.works.classLine(__TRANSFER_POOLED__.class_agreement, __TRANSFER_POOLED__.n)}
      </p>
    </>
  );
}

function Try({ onOpenCase }: { readonly onOpenCase?: (caseId: string) => void }) {
  return (
    <>
      <p className="how-lead">{copy.try.lead}</p>
      <ol className="how-steps">
        {copy.try.steps.map((s, k) => (
          <li key={s} className="how-step">
            <span className="how-step__number" aria-hidden="true">
              {k + 1}
            </span>
            <span className="how-step__text">{s}</span>
          </li>
        ))}
      </ol>
      <div className="how-try">
        <button
          type="button"
          className="how-try__card"
          onClick={() => onOpenCase?.("mississippi-belle-chasse")}
        >
          <span className="how-try__title">{copy.try.gauged}</span>
          <span className="how-small">{copy.try.gaugedNote}</span>
          <ArrowRight className="how-try__arrow" size={18} strokeWidth={1.75} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="how-try__card"
          onClick={() => onOpenCase?.("mississippi-st-joseph")}
        >
          <span className="how-try__title">{copy.try.ungauged}</span>
          <span className="how-small">{copy.try.ungaugedNote}</span>
          <ArrowRight className="how-try__arrow" size={18} strokeWidth={1.75} aria-hidden="true" />
        </button>
      </div>
      <p className="how-small">{copy.try.tour}</p>
    </>
  );
}

function Limits() {
  return (
    <ul className="how-limits">
      {copy.limits.map((l) => (
        <li key={l.title} className="how-limit">
          <h3 className="how-limit__title">{l.title}</h3>
          <p className="how-text">{l.text}</p>
        </li>
      ))}
    </ul>
  );
}

/**
 * "How it works", in six short chapters, one idea each: the problem (one station, one point; a
 * real low-flow year), what the satellite reads, the fingerprint (a live check on a real reading),
 * whether it works (the middle station and the rivers it never saw, failures included), a way to
 * try it, and its limits. A rail lists the chapters (a progress strip on a phone); the arrow keys
 * step through them; a native modal dialog, so Esc closes it.
 *
 * @returns The dialog element (closed until `open`).
 */
export function HowItWorksDialog({ open, onClose, onOpenCase }: HowItWorksDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  const [index, setIndex] = useState(0);
  const chapters = copy.chapters;
  const chapter = chapters[index] ?? chapters[0];

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) {
      return;
    }
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  // A new chapter takes the focus at its heading, so it is read out.
  const moved = useRef(false);
  useEffect(() => {
    if (moved.current) {
      headingRef.current?.focus({ preventScroll: true });
    }
  }, [index]);

  const go = (to: number) => {
    moved.current = true;
    setIndex(Math.min(Math.max(0, to), chapters.length - 1));
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDialogElement>) => {
    // A text field, or a chart that steps through its own marks, keeps its arrow keys.
    const target = event.target as HTMLElement;
    if (
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.closest("[data-own-keys]") !== null
    ) {
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      go(index + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      go(index - 1);
    }
  };
  const body = useMemo(() => {
    switch (chapter.id) {
      case "problem":
        return <Problem />;
      case "reads":
        return <Reads />;
      case "fingerprint":
        return <Print />;
      case "works":
        return <Works />;
      case "try":
        return <Try onOpenCase={onOpenCase} />;
      default:
        return <Limits />;
    }
  }, [chapter.id, onOpenCase]);

  return (
    <dialog
      ref={dialogRef}
      className="how"
      aria-labelledby={titleId}
      onClose={() => {
        moved.current = false;
        setIndex(0);
        onClose();
      }}
      onKeyDown={onKeyDown}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          event.currentTarget.close();
        }
      }}
    >
      <div className="how__frame">
        <nav className="how__rail" aria-label={copy.chaptersLabel}>
          <p className="how__name" id={titleId}>
            {copy.title}
          </p>
          <ol className="how__chapters">
            {chapters.map((c, k) => (
              <li key={c.id}>
                <button
                  type="button"
                  className="how__chapter"
                  aria-current={k === index ? "step" : undefined}
                  data-done={k < index}
                  onClick={() => {
                    go(k);
                  }}
                >
                  <span className="how__chapter-number" aria-hidden="true">
                    {k + 1}
                  </span>
                  <span className="how__chapter-text">{c.short}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>
        <section className="how__stage" aria-labelledby={`${titleId}-chapter`}>
          <header className="how__head">
            <p className="how__count">{copy.count(index + 1, chapters.length)}</p>
            <h2 className="how__title" id={`${titleId}-chapter`} ref={headingRef} tabIndex={-1}>
              {chapter.title}
            </h2>
            <button
              type="button"
              className="how__close"
              aria-label={copy.close}
              onClick={() => dialogRef.current?.close()}
            >
              <X size={18} strokeWidth={1.75} aria-hidden="true" />
            </button>
          </header>
          <div className="how__body" key={chapter.id}>
            {body}
          </div>
          <footer className="how__foot">
            <button
              type="button"
              className="how__nav"
              disabled={index === 0}
              onClick={() => {
                go(index - 1);
              }}
            >
              <ArrowLeft size={16} strokeWidth={1.75} aria-hidden="true" />
              {copy.back}
            </button>
            {index < chapters.length - 1 ? (
              <button
                type="button"
                className="how__nav how__nav--next"
                onClick={() => {
                  go(index + 1);
                }}
              >
                {chapters[index + 1]?.short ?? copy.next}
                <ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />
              </button>
            ) : (
              <button
                type="button"
                className="how__nav how__nav--next"
                onClick={() => dialogRef.current?.close()}
              >
                {copy.close}
              </button>
            )}
          </footer>
        </section>
      </div>
    </dialog>
  );
}
