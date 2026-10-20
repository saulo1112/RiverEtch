import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import { CASE_COPY } from "../content.ts";
import { layout, type Box } from "../tour.ts";
import type { BottomTab } from "./Timeline.tsx";

/** Props of {@link GuidedTour}. */
export interface GuidedTourProps {
  /** Open or closed. */
  readonly open: boolean;
  /** The reach has no gauge (its steps say so). */
  readonly ungauged: boolean;
  /** Shows a bottom tab (a step that points into one). */
  readonly onTab: (tab: BottomTab) => void;
  /** The tour closed (finished or skipped): the caller shows the tab it started on again. */
  readonly onClose: () => void;
}

interface Step {
  /** The `data-tour` mark of the control it points at (null: none, the card is centred). */
  readonly target: string | null;
  /** The bottom tab it needs open. */
  readonly tab?: BottomTab;
  readonly title: string;
  readonly body: string;
}

// The part of an element that is visible: its box cut by every ancestor that clips its overflow
// (a panel that scrolls), so the ring never frames what another panel covers.
function visibleBox(element: Element): Box {
  const r = element.getBoundingClientRect();
  let left = r.left;
  let top = r.top;
  let right = r.right;
  let bottom = r.bottom;
  for (let p = element.parentElement; p !== null; p = p.parentElement) {
    const style = getComputedStyle(p);
    if (/(auto|scroll|hidden|clip)/.test(`${style.overflowX} ${style.overflowY}`)) {
      const c = p.getBoundingClientRect();
      left = Math.max(left, c.left);
      top = Math.max(top, c.top);
      right = Math.min(right, c.right);
      bottom = Math.min(bottom, c.bottom);
    }
  }
  return { left, top, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}

// The steps, from the case's copy: each points at a control that exists on this reach.
function steps(ungauged: boolean): Step[] {
  const t = CASE_COPY.tour;
  return [
    { target: "summary", title: t.summaryTitle, body: ungauged ? t.summaryUngauged : t.summary },
    { target: "trust", title: t.trustTitle, body: t.trust },
    { target: "verify", title: t.verifyTitle, body: t.verify },
    { target: "alter", title: t.alterTitle, body: t.alter },
    { target: "layers", title: t.layersTitle, body: t.layers },
    { target: "tabs", title: t.tabsTitle, body: ungauged ? t.tabsUngauged : t.tabs },
    { target: "never", tab: "rivers", title: t.neverTitle, body: t.never },
    { target: null, title: t.endTitle, body: t.end },
  ];
}

/**
 * The guided tour of a case, in eight steps: the screen dims, a ring frames the control a step is
 * about, and a card beside it (a sheet on a phone) says what it is, with an arrow at it. The steps
 * show only what exists on this reach. A modal dialog: the focus stays in the card, the arrow
 * keys step, and Escape or "Skip tour" ends it; the focus then returns where it was.
 *
 * @returns The tour (nothing while closed).
 */
export function GuidedTour({ open, ungauged, onTab, onClose }: GuidedTourProps) {
  const copy = CASE_COPY.tour;
  const titleId = useId();
  const bodyId = useId();
  const cardRef = useRef<HTMLDivElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<Box | null>(null);
  const [cardSize, setCardSize] = useState({ width: 340, height: 220 });
  const [view, setView] = useState({ width: 0, height: 0 });
  const all = steps(ungauged);
  const step = all[Math.min(index, all.length - 1)];
  const last = index >= all.length - 1;

  const close = useCallback(() => {
    setIndex(0);
    setRect(null);
    setView({ width: 0, height: 0 });
    onClose();
    // After the panels stop being inert (the next frame), the focus goes back where it was.
    const to = returnTo.current;
    window.requestAnimationFrame(() => to?.focus());
  }, [onClose]);

  // Opening: remember where the focus was.
  useEffect(() => {
    if (open) {
      returnTo.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
    }
  }, [open]);

  // Each step: open its tab, bring its control into view and measure it (again on resize).
  useLayoutEffect(() => {
    if (!open || step === undefined) {
      return undefined;
    }
    if (step.tab !== undefined) {
      onTab(step.tab);
    }
    const measure = () => {
      const element =
        step.target === null ? null : document.querySelector(`[data-tour="${step.target}"]`);
      element?.scrollIntoView({ block: "nearest", inline: "nearest" });
      setRect(element === null ? null : visibleBox(element));
      setView({ width: window.innerWidth, height: window.innerHeight });
    };
    const frame = window.requestAnimationFrame(measure);
    window.addEventListener("resize", measure);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", measure);
    };
  }, [open, step, onTab]);

  // The card's own size, for its placement.
  const shown = open && view.width > 0;
  useLayoutEffect(() => {
    const card = cardRef.current;
    if (!shown || card === null) {
      return undefined;
    }
    const observer = new ResizeObserver(() => {
      setCardSize({ width: card.offsetWidth, height: card.offsetHeight });
    });
    observer.observe(card);
    return () => {
      observer.disconnect();
    };
  }, [shown]);

  // The card takes the focus at each step, so a screen reader reads it.
  useEffect(() => {
    if (shown) {
      cardRef.current?.focus();
    }
  }, [shown, index]);

  if (!shown || step === undefined) {
    return null;
  }
  const place = layout(rect, cardSize, view);
  const go = (to: number) => {
    setIndex(Math.min(Math.max(0, to), all.length - 1));
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "ArrowRight" && !last) {
      event.preventDefault();
      go(index + 1);
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      go(index - 1);
    } else if (event.key === "Tab") {
      // Keep the focus in the card.
      const buttons = Array.from(cardRef.current?.querySelectorAll("button") ?? []);
      const first = buttons[0];
      const end = buttons.at(-1);
      const at = document.activeElement;
      if (event.shiftKey && (at === first || at === cardRef.current)) {
        event.preventDefault();
        end?.focus();
      } else if (!event.shiftKey && at === end) {
        event.preventDefault();
        first?.focus();
      }
    }
  };
  return (
    <div className="case-tour" onKeyDown={onKeyDown}>
      {/* Blocks the page under the tour; the ring's shadow is the dimming. */}
      <div className="case-tour__block" aria-hidden="true" />
      {place.ring === null ? (
        <div className="case-tour__dim" aria-hidden="true" />
      ) : (
        <div
          className="case-tour__ring"
          aria-hidden="true"
          style={{
            left: `${String(place.ring.left)}px`,
            top: `${String(place.ring.top)}px`,
            width: `${String(place.ring.width)}px`,
            height: `${String(place.ring.height)}px`,
          }}
        />
      )}
      <div
        ref={cardRef}
        className="case-tour__card"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        tabIndex={-1}
        style={{
          left: `${String(place.card.left)}px`,
          top: `${String(place.card.top)}px`,
          width: `${String(place.card.width)}px`,
        }}
      >
        {place.arrow === null ? null : (
          <span
            className="case-tour__arrow"
            data-side={place.arrow.side}
            aria-hidden="true"
            style={
              place.arrow.side === "left" || place.arrow.side === "right"
                ? { top: `${String(place.arrow.at)}px` }
                : { left: `${String(place.arrow.at)}px` }
            }
          />
        )}
        <div className="case-tour__head">
          <ol className="case-tour__progress" aria-hidden="true">
            {all.map((s, k) => (
              <li key={s.title} data-state={k < index ? "done" : k === index ? "now" : "next"} />
            ))}
          </ol>
          <p className="case-tour__count">{copy.count(index + 1, all.length)}</p>
        </div>
        <h2 className="case-tour__title" id={titleId}>
          {step.title}
        </h2>
        <p className="case-tour__body" id={bodyId}>
          {step.body}
        </p>
        <div className="case-tour__actions">
          {last ? null : (
            <button type="button" className="case-tour__skip" onClick={close}>
              {copy.skip}
            </button>
          )}
          <span className="case-tour__spacer" />
          {index === 0 ? null : (
            <button
              type="button"
              className="case-btn case-btn--ghost case-tour__btn"
              onClick={() => {
                go(index - 1);
              }}
            >
              {copy.back}
            </button>
          )}
          <button
            type="button"
            className="case-btn case-btn--solid case-tour__btn"
            onClick={() => {
              if (last) {
                close();
              } else {
                go(index + 1);
              }
            }}
          >
            {last ? copy.finish : copy.next}
          </button>
        </div>
      </div>
    </div>
  );
}
