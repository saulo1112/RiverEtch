import { ArrowRight } from "lucide-react";

import { COPY } from "./content.ts";
import { Dotted } from "./Dotted.tsx";

/** Props of {@link Copy}. */
export interface CopyProps {
  /** Id of the headline, which labels the hero section. */
  readonly titleId: string;
}

/**
 * The hero's text column: eyebrow, two-line headline, subtitle and the two calls to action.
 *
 * @returns The headline block.
 */
export function Copy({ titleId }: CopyProps) {
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
        <a className="hero-btn hero-btn--solid" href={COPY.primary.href}>
          {COPY.primary.label}
          <ArrowRight size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
        </a>
        <a className="hero-btn hero-btn--ghost" href={COPY.secondary.href}>
          {COPY.secondary.label}
        </a>
      </div>
    </div>
  );
}
