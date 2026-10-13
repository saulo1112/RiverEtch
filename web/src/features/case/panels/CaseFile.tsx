import { ArrowLeft, ExternalLink } from "lucide-react";
import type { Ref } from "react";

import type { ReachCase } from "../../reaches/catalog.ts";
import { gaugeAt, turbidity } from "../../reaches/scene.ts";
import type { ReachData, SeriesRow } from "../../reaches/types.ts";
import { CASE_COPY, formatDate, formatValue, LEVEL_LABELS } from "../content.ts";

/** Props of {@link CaseFile}. */
export interface CaseFileProps {
  /** The case. */
  readonly reachCase: ReachCase;
  /** Its data. */
  readonly reach: ReachData;
  /** The selected pass (null before the series loads). */
  readonly row: SeriesRow | null;
  /** Ref to the site heading, which receives focus when the view lands. */
  readonly headingRef?: Ref<HTMLHeadingElement>;
  /** Called by "Back to your cases". */
  readonly onBack: () => void;
}

const PLATFORMS: Record<string, string> = {
  "sentinel-2a": "Sentinel-2A",
  "sentinel-2b": "Sentinel-2B",
  "sentinel-2c": "Sentinel-2C",
};

function platform(row: SeriesRow): string {
  const key = row.sceneId.split(":").at(-1) ?? "";
  return PLATFORMS[key.split("_")[0] ?? ""] ?? "";
}

// Where the value sits in its interval, on a log scale (0..1).
function intervalPosition(value: number, low: number, high: number): number {
  return Math.min(1, Math.max(0, Math.log(value / low) / Math.log(high / low)));
}

/**
 * Top-left panel: the way back and the case file: the reach, its card's level, the selected pass
 * with its turbidity in FNU and 90 % interval (or why it has none), the gauge's own reading at the
 * overpass, and the error the locked test measured.
 *
 * @returns The case file panel.
 */
export function CaseFile({ reachCase, reach, row, headingRef, onBack }: CaseFileProps) {
  const card = reach.card;
  const overall = card?.levels.find((l) => l.predicted_range === "all");
  const lockbox = card?.metrics.lockbox;
  const estimate = row === null ? null : turbidity(row);
  const value = typeof estimate?.value === "number" ? estimate.value : null;
  const interval = estimate?.interval ?? null;
  const gauge = row === null ? null : gaugeAt(reach, row);
  const unit = estimate?.unit ?? card?.unit ?? "FNU";
  return (
    <div className="case-panel case-top" data-frame="">
      <button type="button" className="case-btn case-btn--ghost case-top__back" onClick={onBack}>
        <ArrowLeft size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
        {CASE_COPY.back}
      </button>
      <article className="case-file case-glass" aria-labelledby="case-site-title">
        <p className="case-file__label">{CASE_COPY.caseFile}</p>
        <h1 className="case-file__site" id="case-site-title" ref={headingRef} tabIndex={-1}>
          {reachCase.title}
        </h1>
        <p className="case-file__place">{reachCase.place}</p>
        <ul className="case-file__chips">
          {overall === undefined ? null : (
            <li className="case-chip case-chip--level" data-level={overall.level}>
              {LEVEL_LABELS[overall.level]}
            </li>
          )}
          <li className="case-chip case-chip--quiet">{CASE_COPY.pipelineChip}</li>
        </ul>

        {row === null ? null : (
          <section className="case-file__reading" aria-label={CASE_COPY.turbidity}>
            <p className="case-file__scene">
              {CASE_COPY.scenePrefix} · {formatDate(row.date, true)}
              {platform(row) === "" ? "" : ` · ${platform(row)}`}
            </p>
            <p className="case-file__metric">{CASE_COPY.turbidity}</p>
            {value !== null && interval !== null ? (
              <>
                <p className="case-file__value">
                  {formatValue(value)}
                  <span className="case-file__unit"> {unit}</span>
                </p>
                <div className="case-file__interval">
                  <div className="case-file__bar" aria-hidden="true">
                    <span
                      className="case-file__bar-mark"
                      style={{
                        left: `${(intervalPosition(value, interval.low, interval.high) * 100).toFixed(1)}%`,
                      }}
                    />
                  </div>
                  <p className="case-file__range">
                    <span>{formatValue(interval.low)}</span>
                    <span>{CASE_COPY.interval}</span>
                    <span>{formatValue(interval.high)}</span>
                  </p>
                </div>
              </>
            ) : (
              <>
                <p className="case-file__none">{CASE_COPY.noValue}</p>
                <p className="case-file__why">
                  {estimate?.abstainReason ?? CASE_COPY.rangeWithoutLevel}
                </p>
              </>
            )}
            <p className="case-file__gauge">
              <span className="case-file__gauge-dot" aria-hidden="true" />
              {gauge === null ? (
                CASE_COPY.gaugeNone
              ) : (
                <>
                  {CASE_COPY.gaugeAt}:{" "}
                  <strong>
                    {formatValue(gauge.value ?? 0)} {unit}
                  </strong>{" "}
                  ({gauge.approval.toLowerCase()})
                </>
              )}
            </p>
          </section>
        )}

        {lockbox === undefined ? null : (
          <dl className="case-file__validation">
            <div>
              <dt>{CASE_COPY.validation.lead}</dt>
              <dd>
                <strong>{lockbox.mdsa.toFixed(1)} %</strong> {CASE_COPY.validation.error}{" "}
                {CASE_COPY.validation.on} {String(lockbox.n)} {CASE_COPY.validation.overpasses}
              </dd>
            </div>
            <div>
              <dt>{CASE_COPY.validation.baseline}</dt>
              <dd>{lockbox.null_mdsa.toFixed(1)} %</dd>
            </div>
          </dl>
        )}

        {reach.info.station.url === undefined ? null : (
          <a
            className="case-file__link"
            href={reach.info.station.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {CASE_COPY.gaugeLink} · {reach.info.station.id.replace("USGS-", "")}
            <ExternalLink size={13} strokeWidth={1.75} aria-hidden="true" />
            <span className="case-visually-hidden"> {CASE_COPY.externalHint}</span>
          </a>
        )}
      </article>
    </div>
  );
}
