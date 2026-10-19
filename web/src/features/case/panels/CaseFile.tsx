import { ArrowLeft, ExternalLink } from "lucide-react";
import { useId, type Ref } from "react";

import type { ReachCase } from "../../reaches/catalog.ts";
import { gaugeAt, thermalValidatedAt, turbidity } from "../../reaches/scene.ts";
import type { ReachData, SeriesRow, ThermalRow } from "../../reaches/types.ts";
import {
  CASE_COPY,
  formatCelsius,
  formatDate,
  formatValue,
  landsatName,
  LEVEL_LABELS,
} from "../content.ts";
import { DisclosureButton } from "./DisclosureButton.tsx";
import { usePanelOpen } from "./usePanelOpen.ts";

/** Props of {@link CaseFile}. */
export interface CaseFileProps {
  /** The case. */
  readonly reachCase: ReachCase;
  /** Its data. */
  readonly reach: ReachData;
  /** The selected pass (null before the series loads). */
  readonly row: SeriesRow | null;
  /** The water-temperature pass to show (null: the reach has none). */
  readonly thermal?: ThermalRow | null;
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

// The water temperature from Landsat (v6): the pass's value, its 90 % half-width, its level and
// the error its locked test measured, beside the day-of-year average's.
function Temperature({
  reach,
  thermal,
}: {
  readonly reach: ReachData;
  readonly thermal: ThermalRow;
}) {
  const copy = CASE_COPY.thermal;
  const { estimate } = thermal;
  const value = typeof estimate.value === "number" ? estimate.value : null;
  const half =
    estimate.interval == null ? null : (estimate.interval.high - estimate.interval.low) / 2;
  const lockbox = reach.thermal?.card?.metrics.lockbox;
  const baseline = reach.thermal?.card?.metrics.null_lockbox;
  const upstream = thermalValidatedAt(reach);
  return (
    <section className="case-file__section case-file__thermal" aria-label={copy.title}>
      <p className="case-file__metric">
        {copy.title} · {landsatName(thermal.platform)} · {formatDate(thermal.date)}
      </p>
      <p className="case-file__thermal-value">
        {value === null ? (
          CASE_COPY.noValue
        ) : (
          <>
            <strong>{formatCelsius(value)}</strong> °C
            {half === null ? null : <span> ± {half.toFixed(1)}</span>}
          </>
        )}
        <span className="case-chip case-chip--level" data-level={estimate.level}>
          {LEVEL_LABELS[estimate.level]}
        </span>
      </p>
      {lockbox === undefined ? null : (
        <p className="case-file__note">
          {copy.lead}: <strong>{lockbox.mae.toFixed(1)} °C</strong> {copy.error} {copy.on}{" "}
          {String(lockbox.n)} {copy.overpasses}
          {baseline === undefined ? null : ` (${copy.baseline}: ${baseline.mae.toFixed(1)} °C)`}
          {upstream === null ? null : <>. {copy.upstreamNote(upstream)}</>}
        </p>
      )}
    </section>
  );
}

/**
 * Top-left panel: the way back and the case file. Folded (the default), it shows the reach, the
 * selected pass's turbidity in FNU with its level and the error the locked test measured. Its
 * details add the place, the pass, the 90 % interval (or why it has no value), the gauge's own
 * reading at the overpass, the locked test against the usual value, the water temperature where
 * Landsat measures it and the gauge's page. The toggle's state is remembered.
 *
 * @returns The case file panel.
 */
export function CaseFile({
  reachCase,
  reach,
  row,
  thermal = null,
  headingRef,
  onBack,
}: CaseFileProps) {
  const detailsId = useId();
  const [open, setOpen] = usePanelOpen("file");
  const card = reach.card;
  const overall = card?.levels.find((l) => l.predicted_range === "all");
  const lockbox = card?.metrics.lockbox;
  const estimate = row === null ? null : turbidity(row);
  const value = typeof estimate?.value === "number" ? estimate.value : null;
  const interval = estimate?.interval ?? null;
  const gauge = row === null ? null : gaugeAt(reach, row);
  const unit = estimate?.unit ?? card?.unit ?? "FNU";
  const level = estimate?.level ?? overall?.level ?? "none";
  return (
    <div className="case-panel case-top" data-frame="">
      <button type="button" className="case-btn case-btn--ghost case-top__back" onClick={onBack}>
        <ArrowLeft size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
        {CASE_COPY.back}
      </button>
      <article className="case-file case-glass" aria-labelledby="case-site-title" data-open={open}>
        <header className="case-head">
          <h1
            className="case-head__title case-file__site"
            id="case-site-title"
            ref={headingRef}
            tabIndex={-1}
          >
            {reachCase.title}
          </h1>
          <DisclosureButton
            label={CASE_COPY.caseDetails}
            open={open}
            controls={detailsId}
            onToggle={setOpen}
          />
        </header>

        {row === null ? null : (
          <section className="case-file__summary" aria-label={CASE_COPY.turbidity}>
            <p className="case-file__metric">{CASE_COPY.turbidity}</p>
            <p className="case-file__value">
              {value === null ? (
                <span className="case-file__none">{CASE_COPY.noValue}</span>
              ) : (
                <span>
                  {formatValue(value)}
                  <span className="case-file__unit"> {unit}</span>
                </span>
              )}
              <span className="case-chip case-chip--level" data-level={level}>
                {LEVEL_LABELS[level]}
              </span>
            </p>
            {lockbox === undefined ? null : (
              <p className="case-file__error">
                <strong>{lockbox.mdsa.toFixed(1)} %</strong> {CASE_COPY.validation.error}
              </p>
            )}
          </section>
        )}

        <div className="case-file__details" id={detailsId} hidden={!open}>
          <div className="case-file__section">
            <p className="case-file__place">{reachCase.place}</p>
            <ul className="case-file__chips">
              <li className="case-chip case-chip--quiet">{CASE_COPY.pipelineChip}</li>
            </ul>
          </div>

          {row === null ? null : (
            <section className="case-file__section" aria-label={CASE_COPY.scenePrefix}>
              <p className="case-file__metric">
                {CASE_COPY.scenePrefix} · {formatDate(row.date, true)}
                {platform(row) === "" ? "" : ` · ${platform(row)}`}
              </p>
              {value !== null && interval !== null ? (
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
              ) : (
                <p className="case-file__note">
                  {estimate?.abstainReason ?? CASE_COPY.rangeWithoutLevel}
                </p>
              )}
              <p className="case-file__gauge">
                <span className="case-file__gauge-dot" aria-hidden="true" />
                <span>
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
                </span>
              </p>
            </section>
          )}

          {lockbox === undefined ? null : (
            <dl className="case-file__section case-file__validation">
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

          {thermal === null ? null : <Temperature reach={reach} thermal={thermal} />}

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
        </div>
      </article>
    </div>
  );
}
