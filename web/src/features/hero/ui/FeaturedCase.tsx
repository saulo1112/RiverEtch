import { ArrowRight } from "lucide-react";
import { useId, useState, type Ref } from "react";

import { IMAGERY } from "../../case/config.ts";
import { formatDate } from "../../case/content.ts";
import { REFERENCE_REACH } from "../../case/reachGeometry.ts";
import { ILLUSTRATIVE_CASE } from "../../case/sample.ts";
import { CASES } from "./content.ts";
import { CASE_THUMBNAIL, previewLayers, thumbnailSrcSet, type PreviewStatus } from "./preview.ts";
import { ReachThumbnail } from "./ReachThumbnail.tsx";

/** Props of {@link FeaturedCase}. */
export interface FeaturedCaseProps {
  /** Receives "Open case" (focus returns to it from the case view). */
  readonly openCaseRef?: Ref<HTMLButtonElement>;
  /** Opens the case (the preview and "Open case" both do). */
  readonly onOpenCase?: () => void;
  /** The pointer or the focus reached a way into the case: warm up the case view. */
  readonly onWarmUp?: () => void;
}

// The outline's drawing box when it stands in for the thumbnail (2:1, like the image).
const FALLBACK_BOX = { width: 200, height: 100, padding: 10 } as const;
const lastScene = ILLUSTRATIVE_CASE.samples.at(-1)?.date ?? null;
const baseUrl = import.meta.env.BASE_URL;
// About the card's width (the panel is at most 440 px wide; full width on phones).
const SIZES = "(max-width: 760px) 92vw, 420px";

/**
 * The featured reference case: a large preview of the case view on top (the captured thumbnail of
 * the landed map, or the reach's outline until that image exists or if it fails), then the title,
 * the description, the chips, the last scene and "Open case". The preview opens the case too. The
 * "Illustrative data" label sits on its top corner and the imagery's credit on its lower edge.
 *
 * @returns The featured card.
 */
export function FeaturedCase({ openCaseRef, onOpenCase, onWarmUp }: FeaturedCaseProps) {
  const titleId = useId();
  const [status, setStatus] = useState<PreviewStatus>("pending");
  const layers = previewLayers(__CASE_THUMBNAIL__, status);
  const { reference } = CASES;
  return (
    <article className="hero-case hero-case--featured" aria-labelledby={titleId}>
      <div className="hero-case__media" data-image={layers.credit ? "loaded" : undefined}>
        <button
          type="button"
          className="hero-case__preview"
          onClick={onOpenCase}
          onPointerEnter={onWarmUp}
          onFocus={onWarmUp}
        >
          <span className="hero-ui__visually-hidden">{reference.previewLabel}</span>
          {layers.fallback ? (
            <ReachThumbnail className="hero-case__fallback" box={FALLBACK_BOX} />
          ) : null}
          {layers.image ? (
            <img
              className="hero-case__image"
              src={`${baseUrl}${CASE_THUMBNAIL.narrow.path}`}
              srcSet={thumbnailSrcSet(baseUrl)}
              sizes={SIZES}
              width={CASE_THUMBNAIL.full.width}
              height={CASE_THUMBNAIL.full.height}
              alt={reference.imageAlt}
              loading="eager"
              decoding="async"
              fetchPriority="high"
              onLoad={() => {
                setStatus("loaded");
              }}
              onError={() => {
                setStatus("failed");
              }}
            />
          ) : null}
        </button>
        <p className="hero-case__flag">{reference.illustrative}</p>
        {layers.credit ? (
          <p className="hero-case__credit">
            <a href={IMAGERY.homepage} target="_blank" rel="noopener noreferrer">
              {IMAGERY.attribution}
              <span className="hero-ui__visually-hidden"> {CASES.externalHint}</span>
            </a>
          </p>
        ) : null}
      </div>
      <div className="hero-case__body">
        <h2 className="hero-case__title" id={titleId}>
          {reference.title}
        </h2>
        <p className="hero-case__place">{REFERENCE_REACH.properties.name}</p>
        <p className="hero-case__desc">{reference.description}</p>
        <ul className="hero-case__chips">
          <li className="hero-case__chip" title={reference.maturityHint}>
            <span className="hero-ui__visually-hidden">{reference.maturityPrefix} </span>
            {reference.maturity}
          </li>
          <li className="hero-case__chip hero-case__chip--synthetic">{reference.synthetic}</li>
        </ul>
        {lastScene === null ? null : (
          <p className="hero-case__meta">
            {reference.lastScene}: <time dateTime={lastScene}>{formatDate(lastScene, true)}</time>
          </p>
        )}
        <button
          ref={openCaseRef}
          type="button"
          className="hero-btn hero-btn--solid hero-case__open"
          onClick={onOpenCase}
          onPointerEnter={onWarmUp}
          onFocus={onWarmUp}
          aria-describedby={titleId}
        >
          {reference.open}
          <ArrowRight size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}
