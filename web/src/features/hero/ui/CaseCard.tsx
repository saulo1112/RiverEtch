import { ArrowRight } from "lucide-react";
import { useEffect, useId, useState, type Ref } from "react";

import { IMAGERY } from "../../case/config.ts";
import { formatDate, LEVEL_LABELS } from "../../case/content.ts";
import type { ReachCase } from "../../reaches/catalog.ts";
import { loadReach } from "../../reaches/data.ts";
import { isUngauged } from "../../reaches/scene.ts";
import type { LngLat, Level } from "../../reaches/types.ts";
import { CASES } from "./content.ts";
import { caseThumbnail, previewLayers, thumbnailSrcSet, type PreviewStatus } from "./preview.ts";
import { ReachThumbnail } from "./ReachThumbnail.tsx";

/** Props of {@link CaseCard}. */
export interface CaseCardProps {
  /** The case. */
  readonly reachCase: ReachCase;
  /** Receives "Open case" (focus returns to it from the case view). */
  readonly openCaseRef?: Ref<HTMLButtonElement>;
  /** Opens the case (the preview and "Open case" both do). */
  readonly onOpenCase?: (caseId: string) => void;
  /** The pointer or the focus reached a way into the case: warm up the case view. */
  readonly onWarmUp?: () => void;
}

/** What the card shows from the reach's files. */
interface Summary {
  readonly level: Level | null;
  readonly mdsa: number | null;
  readonly lastPass: string | null;
  readonly passes: number;
  readonly centreline: readonly LngLat[];
}

// The outline's drawing box when it stands in for the thumbnail (2:1, like the image).
const FALLBACK_BOX = { width: 200, height: 100, padding: 12 } as const;
const baseUrl = import.meta.env.BASE_URL;
// About the card's width (the panel is at most 440 px wide; full width on phones).
const SIZES = "(max-width: 760px) 92vw, 420px";

/**
 * One case: a large preview on top (the captured view of the landed case, or the reach's
 * centreline until that image exists or if it fails), then the title, the place, its level with
 * the locked test's error, the last pass and "Open case". The preview opens the case too.
 *
 * @returns The card.
 */
export function CaseCard({ reachCase, openCaseRef, onOpenCase, onWarmUp }: CaseCardProps) {
  const titleId = useId();
  const [status, setStatus] = useState<PreviewStatus>("pending");
  const [summary, setSummary] = useState<Summary | null>(null);
  const hasImage = __CASE_THUMBNAILS__.includes(reachCase.id);
  const layers = previewLayers(hasImage, status);
  const { card: copy } = CASES;
  const thumbnail = caseThumbnail(reachCase.id);
  const open = () => {
    onOpenCase?.(reachCase.id);
  };

  useEffect(() => {
    let live = true;
    loadReach(reachCase.id)
      .then((reach) => {
        if (!live) {
          return;
        }
        const overall = reach.card?.levels.find((l) => l.predicted_range === "all");
        const line = reach.geometry?.features.find((f) => f.properties.kind === "centreline");
        setSummary({
          // A reach with no gauge has no level of its own: "unvalidated".
          level: overall?.level ?? (isUngauged(reach) ? "unvalidated" : null),
          mdsa: reach.card?.metrics?.lockbox.mdsa ?? null,
          lastPass: reach.series.at(-1)?.date ?? null,
          passes: reach.series.length,
          centreline: line?.geometry.type === "LineString" ? line.geometry.coordinates : [],
        });
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [reachCase.id]);

  return (
    <article className="hero-case hero-case--featured" aria-labelledby={titleId}>
      <div className="hero-case__media" data-image={layers.credit ? "loaded" : undefined}>
        <button
          type="button"
          className="hero-case__preview"
          onClick={open}
          onPointerEnter={onWarmUp}
          onFocus={onWarmUp}
        >
          <span className="hero-ui__visually-hidden">
            {copy.previewLabel} {reachCase.title}.
          </span>
          {layers.fallback && summary !== null ? (
            <ReachThumbnail
              className="hero-case__fallback"
              coordinates={summary.centreline}
              box={FALLBACK_BOX}
            />
          ) : null}
          {layers.image ? (
            <img
              className="hero-case__image"
              src={`${baseUrl}${thumbnail.narrow.path}`}
              srcSet={thumbnailSrcSet(baseUrl, reachCase.id)}
              sizes={SIZES}
              width={thumbnail.full.width}
              height={thumbnail.full.height}
              alt={copy.imageAlt}
              loading="eager"
              decoding="async"
              onLoad={() => {
                setStatus("loaded");
              }}
              onError={() => {
                setStatus("failed");
              }}
            />
          ) : null}
        </button>
        <p className="hero-case__flag hero-case__flag--real">{copy.realData}</p>
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
          {reachCase.title}
        </h2>
        <p className="hero-case__place">{reachCase.place}</p>
        {summary?.level == null ? null : (
          <ul className="hero-case__chips">
            <li className="hero-case__chip hero-case__chip--level" title={copy.levelHint}>
              {LEVEL_LABELS[summary.level]}
              {summary.mdsa === null ? "" : ` · ${summary.mdsa.toFixed(1)} % ${copy.error}`}
            </li>
          </ul>
        )}
        {summary?.lastPass == null ? null : (
          <p className="hero-case__meta">
            {copy.lastPass}:{" "}
            <time dateTime={summary.lastPass}>{formatDate(summary.lastPass, true)}</time> ·{" "}
            {String(summary.passes)} {copy.passes}
          </p>
        )}
        <button
          ref={openCaseRef}
          type="button"
          className="hero-btn hero-btn--solid hero-case__open"
          onClick={open}
          onPointerEnter={onWarmUp}
          onFocus={onWarmUp}
          aria-describedby={titleId}
        >
          {copy.open}
          <ArrowRight size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}
