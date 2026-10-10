import { ArrowLeft } from "lucide-react";
import type { Ref } from "react";

import { alertTitle, CASE_COPY, CASE_MATURITY, formatDate, formatSigned } from "../content.ts";
import type { CaseData } from "../types.ts";
import { canShowPhysicalUnits } from "../units.ts";

/** Props of {@link AlertCard}. */
export interface AlertCardProps {
  /** The case. */
  readonly data: CaseData;
  /** Ref to the site heading, which receives focus when the view lands. */
  readonly headingRef?: Ref<HTMLHeadingElement>;
  /** Called by "Back to your cases". */
  readonly onBack: () => void;
}

/**
 * Top-left panel: the way back and the case file: the site, the verdict on the latest scene and
 * its three figures, all relative (index departure, rainfall, upstream versus downstream). Static;
 * the operator's private reply stays disabled in this demo.
 *
 * @returns The alert panel.
 */
export function AlertCard({ data, headingRef, onBack }: AlertCardProps) {
  const lastRain = data.rainfall.at(-1);
  const rows = [
    {
      label: CASE_COPY.rows.departure,
      value: `${formatSigned(data.anomaly.zScore, 1)} ${CASE_COPY.vsBaseline}`,
    },
    {
      label: CASE_COPY.rows.rainfall,
      value: lastRain === undefined ? "–" : `${lastRain.mm.toFixed(1)} mm (${CASE_COPY.lastDay})`,
    },
    {
      label: CASE_COPY.rows.delta,
      value: `ΔNDTI ${formatSigned(data.stats.deltaNdti, 2)} (${CASE_COPY.relative})`,
    },
  ];
  return (
    <div className="case-panel case-top">
      <button type="button" className="case-btn case-btn--ghost case-top__back" onClick={onBack}>
        <ArrowLeft size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
        {CASE_COPY.back}
      </button>
      <article className="case-alert case-glass" aria-labelledby="case-site-title">
        <p className="case-alert__label">{CASE_COPY.caseFile}</p>
        <h1 className="case-alert__site" id="case-site-title" ref={headingRef} tabIndex={-1}>
          {data.site.name}
          {data.illustrative ? (
            <span className="case-alert__site-note"> {CASE_COPY.syntheticNote}</span>
          ) : null}
        </h1>
        <h2 className="case-alert__title">
          <span className="case-alert__dot" aria-hidden="true" />
          {alertTitle(data.classification)}
        </h2>
        <ul className="case-alert__chips">
          {data.illustrative ? <li className="case-chip">{CASE_COPY.illustrativeChip}</li> : null}
          <li className="case-chip case-chip--quiet" title={CASE_MATURITY.hint}>
            {CASE_MATURITY.label}
          </li>
        </ul>
        <p className="case-alert__scene">
          {CASE_COPY.scenePrefix} · {formatDate(data.anomaly.sceneDate, true)}
        </p>
        <dl className="case-alert__rows">
          {rows.map((row) => (
            <div className="case-alert__row" key={row.label}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
        {canShowPhysicalUnits(data) ? null : (
          <p className="case-alert__relative">{CASE_COPY.relativeNote}</p>
        )}
        <button
          type="button"
          className="case-btn case-btn--ghost case-alert__reply"
          disabled
          aria-describedby="case-reply-hint"
        >
          {CASE_COPY.reply}
        </button>
        <p className="case-alert__hint" id="case-reply-hint">
          {CASE_COPY.replyHint}
        </p>
      </article>
    </div>
  );
}
