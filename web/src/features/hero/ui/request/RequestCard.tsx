import { Plus } from "lucide-react";
import type { Ref } from "react";

import { REQUEST } from "./content.ts";

/** Props of {@link RequestCard}. */
export interface RequestCardProps {
  /** Opens the request form. */
  readonly onRequest: () => void;
  /** Receives the button (focus returns to it from the form). */
  readonly buttonRef?: Ref<HTMLButtonElement>;
}

/**
 * The dashed card at the end of the cases list that opens "Request a study reach".
 *
 * @returns The card's button.
 */
export function RequestCard({ onRequest, buttonRef }: RequestCardProps) {
  return (
    <button ref={buttonRef} type="button" className="hero-request-card" onClick={onRequest}>
      <Plus size={18} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
      <span className="hero-request-card__text">
        <span className="hero-request-card__title">{REQUEST.card.title}</span>
        <span className="hero-request-card__hint">{REQUEST.card.text}</span>
      </span>
    </button>
  );
}
