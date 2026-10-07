import { ArrowLeft } from "lucide-react";
import type { Ref } from "react";

import { CASE_COPY, formatDate, formatSigned } from "../content.ts";
import type { CaseData } from "../types.ts";

/** Props of {@link AlertCard}. */
export interface AlertCardProps {
  /** The case. */
  readonly data: CaseData;
  /** Ref to the site heading, which receives focus when the view lands. */
  readonly headingRef?: Ref<HTMLHeadingElement>;
  /** Called by "Back to the globe". */
  readonly onBack: () => void;
}

/**
 * Top-left panel: the way back, the site heading and the alert with its three figures. Static;
 * "Challenge operator" stays disabled until the proof flow exists.
 *
 * @returns The alert panel.
 */
export function AlertCard({ data, headingRef, onBack }: AlertCardProps) {
  const lastRain = data.rainfall.at(-1);
  const rows = [
    {
      label: CASE_COPY.rows.anomaly,
      value: `${formatSigned(data.anomaly.zScore, 1)} σ vs baseline`,
    },
    {
      label: CASE_COPY.rows.rainfall,
      value: lastRain === undefined ? "–" : `${lastRain.mm.toFixed(1)} mm (last day)`,
    },
    {
      label: CASE_COPY.rows.delta,
      value: `ΔNDTI ${formatSigned(data.stats.deltaNdti, 2)}`,
    },
  ];
  return (
    <div className="case-panel case-top">
      <button type="button" className="case-btn case-btn--ghost case-top__back" onClick={onBack}>
        <ArrowLeft size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
        {CASE_COPY.back}
      </button>
      <article className="case-alert case-glass" aria-labelledby="case-alert-title">
        <h1 className="case-alert__site" id="case-site-title" ref={headingRef} tabIndex={-1}>
          {data.site.name}
          <span className="case-alert__site-note"> · {CASE_COPY.placeholderSite}</span>
        </h1>
        <div className="case-alert__head">
          <h2 className="case-alert__title" id="case-alert-title">
            <span className="case-alert__dot" aria-hidden="true" />
            {CASE_COPY.alertTitle}
          </h2>
          {data.illustrative ? <p className="case-chip">{CASE_COPY.illustrativeChip}</p> : null}
        </div>
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
        <button
          type="button"
          className="case-btn case-btn--solid case-alert__challenge"
          disabled
          aria-describedby="case-challenge-hint"
        >
          {CASE_COPY.challenge}
        </button>
        <p className="case-alert__hint" id="case-challenge-hint">
          {CASE_COPY.challengeHint}
        </p>
      </article>
    </div>
  );
}
