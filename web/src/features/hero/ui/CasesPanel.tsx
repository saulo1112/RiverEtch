import { ArrowLeft } from "lucide-react";
import type { Ref } from "react";

import { REACH_CASES } from "../../reaches/catalog.ts";
import { CaseCard } from "./CaseCard.tsx";
import { CASES } from "./content.ts";
import { RequestCard } from "./request/RequestCard.tsx";

/** Props of {@link CasesPanel}. */
export interface CasesPanelProps {
  /** Id of the heading, which labels the hero section while this screen shows. */
  readonly titleId: string;
  /** Receives the heading (focus moves to it when the screen opens). */
  readonly headingRef?: Ref<HTMLHeadingElement>;
  /** Receives "Open case" (focus returns to it from the case view). */
  readonly openCaseRef?: Ref<HTMLButtonElement>;
  /** Back to the entry screen. */
  readonly onBack: () => void;
  /** "Open case": starts the flythrough into that case. */
  readonly onOpenCase?: (caseId: string) => void;
  /** The pointer or the focus reached "Open case": warm up the case view. */
  readonly onWarmUp?: () => void;
  /** "Request a study reach": opens the request form (no card without it). */
  readonly onRequest?: () => void;
  /** Receives the request card's button (focus returns to it from the form). */
  readonly requestRef?: Ref<HTMLButtonElement>;
}

/**
 * The cases screen: the demo's two gauged reaches, each with a large preview that opens its case
 * view, and a compact card that offers to request a study reach.
 *
 * @returns The cases panel.
 */
export function CasesPanel({
  titleId,
  headingRef,
  openCaseRef,
  onBack,
  onOpenCase,
  onWarmUp,
  onRequest,
  requestRef,
}: CasesPanelProps) {
  return (
    <section className="hero-panel hero-cases hero-ui__glass" aria-labelledby={titleId}>
      <div className="hero-panel__head">
        <h1 ref={headingRef} className="hero-panel__title" id={titleId} tabIndex={-1}>
          {CASES.heading}
        </h1>
        <button
          type="button"
          className="hero-panel__back"
          onClick={onBack}
          aria-label={CASES.backLabel}
        >
          <ArrowLeft size={15} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
          {CASES.back}
        </button>
        <p className="hero-panel__note">{CASES.note}</p>
      </div>
      <ul className="hero-cases__list" aria-label={CASES.listLabel}>
        {REACH_CASES.map((reachCase, index) => (
          <li key={reachCase.id}>
            <CaseCard
              reachCase={reachCase}
              openCaseRef={index === 0 ? openCaseRef : undefined}
              onOpenCase={onOpenCase}
              onWarmUp={onWarmUp}
            />
          </li>
        ))}
        {onRequest === undefined ? null : (
          <li>
            <RequestCard onRequest={onRequest} buttonRef={requestRef} />
          </li>
        )}
      </ul>
    </section>
  );
}
