import { X } from "lucide-react";
import { useEffect, useId, useRef } from "react";

import { HOW_IT_WORKS } from "./content.ts";

/** Props of {@link HowItWorksDialog}. */
export interface HowItWorksDialogProps {
  /** Shows the dialog (modal) while true. */
  readonly open: boolean;
  /** The dialog closed: Esc, the close button, a press on the backdrop, or `open` turning false. */
  readonly onClose: () => void;
}

/**
 * "How it works": the three steps, what the record can and cannot say, and the maturity levels of
 * a reach. A native modal dialog, so the page behind it is inert and Esc closes it.
 *
 * @returns The dialog element (closed until `open`).
 */
export function HowItWorksDialog({ open, onClose }: HowItWorksDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();

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

  return (
    <dialog
      ref={dialogRef}
      className="hero-dialog"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => {
        // The body fills the dialog, so a press on the dialog itself is on the backdrop.
        if (event.target === event.currentTarget) {
          event.currentTarget.close();
        }
      }}
    >
      <div className="hero-dialog__body">
        <div className="hero-dialog__head">
          <h2 className="hero-dialog__title" id={titleId}>
            {HOW_IT_WORKS.title}
          </h2>
          <button
            type="button"
            className="hero-dialog__close"
            aria-label={HOW_IT_WORKS.close}
            onClick={() => dialogRef.current?.close()}
          >
            <X size={18} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
          </button>
        </div>
        <p className="hero-dialog__lead">{HOW_IT_WORKS.demo}</p>

        <ol className="hero-dialog__steps">
          {HOW_IT_WORKS.steps.map((step) => (
            <li key={step.number} className="hero-dialog__step">
              <p className="hero-dialog__step-label">
                <span className="hero-dialog__number" aria-hidden="true">
                  {step.number}
                </span>{" "}
                {step.label}
              </p>
              <p className="hero-dialog__text">{step.text}</p>
            </li>
          ))}
        </ol>

        <h3 className="hero-dialog__subtitle">{HOW_IT_WORKS.limitsTitle}</h3>
        <div className="hero-dialog__limits">
          <div>
            <h4 className="hero-dialog__list-title">{HOW_IT_WORKS.canTitle}</h4>
            <ul className="hero-dialog__list">
              {HOW_IT_WORKS.can.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="hero-dialog__list-title">{HOW_IT_WORKS.cannotTitle}</h4>
            <ul className="hero-dialog__list hero-dialog__list--cannot">
              {HOW_IT_WORKS.cannot.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>

        <h3 className="hero-dialog__subtitle">{HOW_IT_WORKS.maturityTitle}</h3>
        <ol className="hero-dialog__maturity">
          {HOW_IT_WORKS.maturity.map((level) => (
            <li key={level.label}>
              <span className="hero-dialog__level">{level.label}</span>
              <span className="hero-dialog__text">{level.text}</span>
            </li>
          ))}
        </ol>
        <p className="hero-dialog__note">{HOW_IT_WORKS.maturityNote}</p>
      </div>
    </dialog>
  );
}
