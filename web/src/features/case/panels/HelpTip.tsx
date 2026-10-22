import { CircleHelp } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

const POP_WIDTH = 300; // a floating explanation's width (CSS), to keep it on screen
const POP_MARGIN = 8;

/** Props of {@link HelpTip}. */
export interface HelpTipProps {
  /** The button's accessible name, e.g. "About the expected range". */
  readonly label: string;
  /** The explanation shown under the row. */
  readonly children: ReactNode;
  /**
   * Open over the page instead of inline: for a (?) inside a box that clips its content, such as a
   * Water quality tile.
   */
  readonly float?: boolean;
}

/**
 * A "?" that explains the number beside it. It opens on click, tap, Enter or Space (never on hover
 * alone) and closes on a second press, Esc or a press elsewhere. The text opens inline, under the
 * row that holds the button (the row wraps), so a panel's own scrolling never clips it and it never
 * covers the button. The visible mark is small; its hit area is 44 × 44 px.
 *
 * @returns The button and its explanation.
 */
export function HelpTip({ label, children, float = false }: HelpTipProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const rootRef = useRef<HTMLSpanElement>(null);
  const popRef = useRef<HTMLSpanElement>(null);
  // Where a floating text opens: over the button, kept on screen, and the page it opens in.
  const [place, setPlace] = useState<{ left: number; bottom: number; host: Element } | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    const onDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.parentElement?.contains(target) && !popRef.current?.contains(target)) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown);
    };
  }, [open]);

  return (
    <>
      <span className="case-help" ref={rootRef}>
        <button
          type="button"
          className="case-help__button"
          aria-label={label}
          aria-expanded={open}
          aria-controls={id}
          onClick={(event) => {
            if (float && !open) {
              const rect = event.currentTarget.getBoundingClientRect();
              const width = Math.min(POP_WIDTH, window.innerWidth - 2 * POP_MARGIN);
              setPlace({
                left: Math.min(
                  Math.max(POP_MARGIN, rect.left + rect.width / 2 - width / 2),
                  window.innerWidth - width - POP_MARGIN,
                ),
                bottom: window.innerHeight - rect.top + 6,
                host: event.currentTarget.closest(".case-view") ?? document.body,
              });
            }
            setOpen(!open);
          }}
        >
          <CircleHelp size={15} strokeWidth={1.9} aria-hidden="true" />
        </button>
      </span>
      {float ? (
        open && place !== null ? (
          createPortal(
            <span
              ref={popRef}
              className="case-help__pop case-glass"
              id={id}
              role="note"
              style={{ left: `${String(place.left)}px`, bottom: `${String(place.bottom)}px` }}
            >
              {children}
            </span>,
            place.host,
          )
        ) : null
      ) : (
        <span className="case-help__text" id={id} hidden={!open}>
          {children}
        </span>
      )}
    </>
  );
}
