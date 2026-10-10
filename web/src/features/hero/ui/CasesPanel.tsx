import { ArrowLeft, ArrowRight } from "lucide-react";
import { useId, type Ref } from "react";

import { formatDate } from "../../case/content.ts";
import { REFERENCE_REACH } from "../../case/reachGeometry.ts";
import { ILLUSTRATIVE_CASE } from "../../case/sample.ts";
import { CASES } from "./content.ts";
import { RequestCard } from "./request/RequestCard.tsx";
import { reachThumbnailPath } from "./thumbnail.ts";

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
  /** "Open case": starts the flythrough into the reference case. */
  readonly onOpenCase?: () => void;
  /** The pointer or the focus reached "Open case": warm up the case view. */
  readonly onWarmUp?: () => void;
  /** "Request a study reach": opens the request form (no card without it). */
  readonly onRequest?: () => void;
  /** Receives the request card's button (focus returns to it from the form). */
  readonly requestRef?: Ref<HTMLButtonElement>;
}

const THUMBNAIL = { width: 48, height: 96, padding: 8 } as const;
const thumbnailPath = reachThumbnailPath(REFERENCE_REACH.geometry.coordinates, THUMBNAIL);
const lastScene = ILLUSTRATIVE_CASE.samples.at(-1)?.date ?? null;

/**
 * The cases screen: the demo analyst's cases, all illustrative. The reference reach opens the case
 * view; the Sinú reach was evaluated and found no robust signal, so it has no case to open.
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
  const referenceTitleId = useId();
  const evaluatedTitleId = useId();
  const { reference, evaluated } = CASES;
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
        <li>
          <article className="hero-case" aria-labelledby={referenceTitleId}>
            <svg
              className="hero-case__thumb"
              viewBox={`0 0 ${String(THUMBNAIL.width)} ${String(THUMBNAIL.height)}`}
              role="img"
              aria-label={reference.thumbnail}
            >
              <path d={thumbnailPath} />
            </svg>
            <div className="hero-case__body">
              <h2 className="hero-case__title" id={referenceTitleId}>
                {reference.title}
              </h2>
              <p className="hero-case__place">{REFERENCE_REACH.properties.name}</p>
              <ul className="hero-case__chips">
                <li className="hero-case__chip" title={reference.maturityHint}>
                  <span className="hero-ui__visually-hidden">{reference.maturityPrefix} </span>
                  {reference.maturity}
                </li>
                <li className="hero-case__chip hero-case__chip--synthetic">
                  {reference.synthetic}
                </li>
              </ul>
              {lastScene === null ? null : (
                <p className="hero-case__meta">
                  {reference.lastScene}:{" "}
                  <time dateTime={lastScene}>{formatDate(lastScene, true)}</time>
                </p>
              )}
              <button
                ref={openCaseRef}
                type="button"
                className="hero-btn hero-btn--solid hero-case__open"
                onClick={onOpenCase}
                onPointerEnter={onWarmUp}
                onFocus={onWarmUp}
                aria-describedby={referenceTitleId}
              >
                {reference.open}
                <ArrowRight size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
              </button>
            </div>
          </article>
        </li>
        <li>
          <article className="hero-case hero-case--closed" aria-labelledby={evaluatedTitleId}>
            <div className="hero-case__body">
              <h2 className="hero-case__title" id={evaluatedTitleId}>
                {evaluated.title}
              </h2>
              <p className="hero-case__place">{evaluated.place}</p>
              <ul className="hero-case__chips">
                <li className="hero-case__chip">{evaluated.status}</li>
              </ul>
              <figure className="hero-case__quote">
                <blockquote>
                  <p>{evaluated.quote}</p>
                </blockquote>
                <figcaption>{evaluated.source}</figcaption>
              </figure>
              <p className="hero-case__closed">{evaluated.closed}</p>
            </div>
          </article>
        </li>
        {onRequest === undefined ? null : (
          <li>
            <RequestCard onRequest={onRequest} buttonRef={requestRef} />
          </li>
        )}
      </ul>
    </section>
  );
}
