import { ArrowRight } from "lucide-react";
import { useCallback, type Ref, type RefCallback } from "react";

import { COPY, INDICATORS, type Indicator } from "./content.ts";
import { riversTested } from "./how/numbers.ts";
import { Dotted } from "./Dotted.tsx";
import { useLift } from "./useLift.ts";

/** Props of {@link Copy}. */
export interface CopyProps {
  /** Id of the headline, which labels the hero section. */
  readonly titleId: string;
  /** "Explore your cases": opens the cases screen. */
  readonly onOpenCases: () => void;
  /** "How it works": opens the dialog. */
  readonly onHowItWorks: () => void;
  /** The pointer or the focus reached "Explore your cases": warm up the case view. */
  readonly onWarmUp?: () => void;
  /** Receives "Explore your cases" (focus comes back to it from the cases screen). */
  readonly exploreRef?: Ref<HTMLButtonElement>;
  /** Receives "How it works" (focus comes back to it from the dialog). */
  readonly howItWorksRef?: Ref<HTMLButtonElement>;
}

// Sets a ref of either kind.
function assignRef<T>(ref: Ref<T> | undefined, value: T | null): void {
  if (typeof ref === "function") {
    ref(value);
  } else if (ref !== null && ref !== undefined) {
    ref.current = value;
  }
}

// Attaches an element to an outside ref and to the lift effect; the cleanup detaches both.
function composeRef<T extends HTMLElement>(
  element: T | null,
  ref: Ref<T> | undefined,
  lift: RefCallback<T>,
): () => void {
  assignRef(ref, element);
  const cleanup = lift(element);
  return () => {
    if (typeof cleanup === "function") {
      cleanup();
    }
    assignRef(ref, null);
  };
}

// The indicators' figures: the rivers are counted from the transfer test's committed results;
// the check is one button, and the record has three separate checks (Ethereum, Bitcoin, ML-DSA).
const FIGURES: Readonly<Record<Indicator["id"], string>> = {
  rivers: String(riversTested(__TRANSFER_SCORES__)),
  check: "1",
  proofs: "3",
};

/**
 * The entry screen's text column: eyebrow, two-line headline, subtitle, the two calls to action
 * ("Explore your cases" opens the demo workspace's cases; "How it works" opens the dialog) and three
 * indicators under them.
 *
 * @returns The headline block.
 */
export function Copy({
  titleId,
  onOpenCases,
  onHowItWorks,
  onWarmUp,
  exploreRef,
  howItWorksRef,
}: CopyProps) {
  const primaryLift = useLift<HTMLButtonElement>();
  const secondaryLift = useLift<HTMLButtonElement>();
  const primaryRef = useCallback(
    (element: HTMLButtonElement | null) => composeRef(element, exploreRef, primaryLift),
    [exploreRef, primaryLift],
  );
  const secondaryRef = useCallback(
    (element: HTMLButtonElement | null) => composeRef(element, howItWorksRef, secondaryLift),
    [howItWorksRef, secondaryLift],
  );
  return (
    <div className="hero-copy">
      <p className="hero-eyebrow">
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
          ref={primaryRef}
          type="button"
          className="hero-btn hero-btn--solid hero-btn--lift"
          onClick={onOpenCases}
          onPointerEnter={onWarmUp}
          onFocus={onWarmUp}
        >
          {COPY.primary.label}
          <ArrowRight size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
        </button>
        <button
          ref={secondaryRef}
          type="button"
          className="hero-btn hero-btn--ghost hero-btn--how hero-btn--lift"
          onClick={onHowItWorks}
          aria-haspopup="dialog"
        >
          {COPY.secondary.label}
        </button>
      </div>
      <ul className="hero-indicators">
        {INDICATORS.map((item) => (
          <li key={item.id} className="hero-indicator">
            <p className="hero-indicator__head">
              <span className="hero-indicator__figure">{FIGURES[item.id]}</span>
              <span className="hero-indicator__label">{item.label}</span>
            </p>
            <p className="hero-indicator__desc">{item.description}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
