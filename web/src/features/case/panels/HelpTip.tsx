import { CircleHelp } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

/** Props of {@link HelpTip}. */
export interface HelpTipProps {
  /** The button's accessible name, e.g. "About the expected range". */
  readonly label: string;
  /** The explanation shown under the row. */
  readonly children: ReactNode;
}

/**
 * A "?" that explains the number beside it. It opens on click, tap, Enter or Space (never on hover
 * alone) and closes on a second press, Esc or a press elsewhere. The text opens inline, under the
 * row that holds the button (the row wraps), so a panel's own scrolling never clips it and it never
 * covers the button. The visible mark is small; its hit area is 44 × 44 px.
 *
 * @returns The button and its explanation.
 */
export function HelpTip({ label, children }: HelpTipProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const rootRef = useRef<HTMLSpanElement>(null);

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
      if (!rootRef.current?.parentElement?.contains(event.target as Node)) {
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
          onClick={() => {
            setOpen(!open);
          }}
        >
          <CircleHelp size={15} strokeWidth={1.9} aria-hidden="true" />
        </button>
      </span>
      <span className="case-help__text" id={id} hidden={!open}>
        {children}
      </span>
    </>
  );
}
