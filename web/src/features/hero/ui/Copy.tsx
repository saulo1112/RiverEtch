import { ArrowRight } from "lucide-react";

import { COPY } from "./content.ts";
import { Dotted } from "./Dotted.tsx";
import { useLift } from "./useLift.ts";

/** Props of {@link Copy}. */
export interface CopyProps {
  /** Id of the headline, which labels the hero section. */
  readonly titleId: string;
  /** "Explore the case": starts the flythrough. */
  readonly onExplore?: () => void;
  /** The pointer or the focus reached "Explore the case": warm up the case view. */
  readonly onWarmUp?: () => void;
  /** Focus "Explore the case" on mount (back from the case view). */
  readonly focusExplore?: boolean;
}

/**
 * The hero's text column: eyebrow, two-line headline, subtitle and the two calls to action ("Explore
 * the case" starts the flythrough; "How it works" is still a placeholder link).
 *
 * @returns The headline block.
 */
export function Copy({ titleId, onExplore, onWarmUp, focusExplore = false }: CopyProps) {
  const primaryLift = useLift<HTMLButtonElement>();
  const secondaryLift = useLift<HTMLAnchorElement>();
  return (
    <div className="hero-copy">
      <p className="hero-eyebrow">
        <span className="hero-eyebrow__dot" aria-hidden="true" />
        <span className="hero-eyebrow__text">
          <Dotted items={COPY.eyebrow} />
        </span>
      </p>
      <h1 className="hero-title" id={titleId}>
        <span className="hero-title__line">{COPY.title[0]}</span>{" "}
        <span className="hero-title__line hero-title__line--quiet">{COPY.title[1]}</span>
      </h1>
      <p className="hero-sub">{COPY.subtitle}</p>
      <div className="hero-ctas">
        <button
          ref={primaryLift}
          type="button"
          className="hero-btn hero-btn--solid hero-btn--lift"
          onClick={onExplore}
          onPointerEnter={onWarmUp}
          onFocus={onWarmUp}
          // Only when coming back from the case view, so keyboard focus is not lost.
          autoFocus={focusExplore}
        >
          {COPY.primary.label}
          <ArrowRight size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
        </button>
        <a
          ref={secondaryLift}
          className="hero-btn hero-btn--ghost hero-btn--lift"
          href={COPY.secondary.href}
        >
          {COPY.secondary.label}
        </a>
      </div>
    </div>
  );
}
