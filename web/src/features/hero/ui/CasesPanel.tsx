import { ArrowLeft, CircleHelp } from "lucide-react";
import { useId, useState, type Ref } from "react";

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

// The two kinds of case, in the catalog's order within each; a kind with no case is left out.
const GROUPS = [
  {
    id: "station",
    title: CASES.groups.station,
    note: CASES.groups.stationNote,
    cases: REACH_CASES.filter((c) => c.gauged),
  },
  {
    id: "none",
    title: CASES.groups.none,
    note: CASES.groups.noneNote,
    cases: REACH_CASES.filter((c) => !c.gauged),
  },
].filter((g) => g.cases.length > 0);
// The case focus returns to from the case view: the first one shown.
const FIRST = GROUPS[0]?.cases[0]?.id;

/**
 * The cases screen in two groups: the rivers checked against a station (the satellite's reading
 * beside the station's own) and the rivers with none (what RiverEtch is for), each case with a
 * large preview that opens its case view; then a compact card that offers to request a study
 * reach.
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
  const whyId = useId();
  const [whyOpen, setWhyOpen] = useState(false);
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
        <p className="hero-panel__note hero-cases__note">
          {CASES.note}
          <button
            type="button"
            className="hero-cases__why"
            aria-label={CASES.kindsLabel}
            aria-expanded={whyOpen}
            aria-controls={whyId}
            onClick={() => {
              setWhyOpen(!whyOpen);
            }}
          >
            <CircleHelp size={15} strokeWidth={1.9} aria-hidden="true" />
          </button>
        </p>
        <p className="hero-cases__why-text" id={whyId} hidden={!whyOpen}>
          {CASES.kinds}
        </p>
      </div>
      {GROUPS.map((group) => (
        <section
          key={group.id}
          className="hero-cases__group"
          aria-labelledby={`${titleId}-${group.id}`}
        >
          <h2 className="hero-cases__group-title" id={`${titleId}-${group.id}`}>
            {group.title}
          </h2>
          <p className="hero-cases__group-note">{group.note}</p>
          <ul className="hero-cases__list">
            {group.cases.map((reachCase) => (
              <li key={reachCase.id}>
                <CaseCard
                  reachCase={reachCase}
                  openCaseRef={reachCase.id === FIRST ? openCaseRef : undefined}
                  onOpenCase={onOpenCase}
                  onWarmUp={onWarmUp}
                />
              </li>
            ))}
          </ul>
        </section>
      ))}
      {onRequest === undefined ? null : (
        <div className="hero-cases__request">
          <RequestCard onRequest={onRequest} buttonRef={requestRef} />
        </div>
      )}
    </section>
  );
}
