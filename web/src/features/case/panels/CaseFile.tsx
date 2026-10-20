import {
  Anchor,
  ArrowLeft,
  Clock,
  Compass,
  ExternalLink,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { useId, type Ref } from "react";

import { useRecordAnchor } from "../../chain/useRecordAnchor.ts";
import type { ReachCase } from "../../reaches/catalog.ts";
import { gaugeAt, isUngauged, thermalValidatedAt, turbidity } from "../../reaches/scene.ts";
import type {
  CardMetrics,
  ExpectedError,
  Level,
  ReachData,
  SeriesRow,
  ThermalRow,
} from "../../reaches/types.ts";
import {
  CASE_COPY,
  formatCelsius,
  formatDate,
  formatValue,
  landsatName,
  LEVEL_LABELS,
} from "../content.ts";
import { gainOver, insideCount, leanOfTurbidity } from "../reading.ts";
import { DisclosureButton } from "./DisclosureButton.tsx";
import { HelpTip } from "./HelpTip.tsx";
import { ReliabilityBars } from "./ReliabilityBars.tsx";
import { usePanelOpen } from "./usePanelOpen.ts";

const { reading, trust, ungauged } = CASE_COPY;

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
  /** Opens the guided tour (no button without it). */
  readonly onTour?: () => void;
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

// The record's trust strip: its level (with what a reader can do with it), its seal, and whether
// its ledger line is anchored on Sepolia, by mark and words, never by colour alone.
function Trust({
  reach,
  row,
  level,
}: {
  readonly reach: ReachData;
  readonly row: SeriesRow;
  readonly level: Level;
}) {
  const anchor = useRecordAnchor(reach, "observations", row.recordSha256);
  const anchorText =
    anchor.state === "anchored"
      ? trust.anchored(
          formatDate(new Date(anchor.anchor.timestamp * 1000).toISOString().slice(0, 10), true),
        )
      : anchor.state === "pending"
        ? trust.pending
        : anchor.state === "mismatch"
          ? trust.mismatch
          : anchor.state === "checking"
            ? trust.checking
            : trust.unavailable;
  const AnchorIcon =
    anchor.state === "anchored" ? Anchor : anchor.state === "mismatch" ? TriangleAlert : Clock;
  return (
    <div className="case-trust" role="group" aria-label={trust.label} data-tour="trust">
      <span className="case-trust__level">
        <span className="case-chip case-chip--level" data-level={level}>
          {LEVEL_LABELS[level]}
        </span>
        <HelpTip label={`${CASE_COPY.levelHelpLabel}: ${LEVEL_LABELS[level]}`}>
          {CASE_COPY.levelHelp[level]}
        </HelpTip>
      </span>
      <span className="case-trust__item">
        <ShieldCheck size={14} strokeWidth={1.9} aria-hidden="true" />
        {trust.sealed}
      </span>
      <span className="case-trust__item" data-state={anchor.state} aria-live="polite">
        <AnchorIcon size={14} strokeWidth={1.9} aria-hidden="true" />
        {anchorText}
      </span>
    </div>
  );
}

// How far off the turbidity tends to be: the satellite's locked-test error beside guessing the
// river's usual value, two bars on one scale, then the same in words.
function Reliability({ lockbox }: { readonly lockbox: CardMetrics }) {
  const gain = gainOver(lockbox.mdsa, lockbox.null_mdsa);
  return (
    <section className="case-file__reliability" aria-label={reading.reliabilityTitle}>
      <p className="case-file__reliability-head">
        <span>
          {reading.reliabilityTitle}{" "}
          <span className="case-file__muted">· {reading.lessIsBetter}</span>
        </span>
        <HelpTip label={reading.reliabilityHelpLabel}>
          {reading.baselineHelp} {reading.unitsHelp}
        </HelpTip>
      </p>
      <ReliabilityBars satellite={lockbox.mdsa} baseline={lockbox.null_mdsa} unit="%" />
      <p className="case-file__note">
        {reading.median(lockbox.n, lockbox.mdsa.toFixed(1))}{" "}
        {gain.kind === "times"
          ? reading.times(gain.text)
          : gain.kind === "worse"
            ? reading.worse
            : reading.noGain}
      </p>
    </section>
  );
}

// An ungauged reach's expected error (preregistration-transfer.md, section 5): the class agreement
// as a count, the pooled median error with what it is a share of, and which way it leans.
function ExpectedErrorNote({ error }: { readonly error: ExpectedError }) {
  const lean = leanOfTurbidity(error.sspb);
  return (
    <section className="case-file__reliability" aria-label={ungauged.errorTitle}>
      <p className="case-file__reliability-head">
        <span>{ungauged.errorTitle}</span>
        <HelpTip label={reading.reliabilityHelpLabel}>
          {ungauged.baselineNote} {reading.unitsHelp}
        </HelpTip>
      </p>
      <p className="case-file__note">
        <strong>{ungauged.agreement(error.classAgreement, error.n)}</strong>{" "}
        {ungauged.median(error.mdsa.toFixed(1), error.sites.length)}
        {lean.kind === "low"
          ? ` It ${reading.leanLow(lean.text)}.`
          : lean.kind === "high"
            ? ` It ${reading.leanHigh(lean.text)}.`
            : ""}
      </p>
      <p className="case-file__note">{ungauged.trainedOn}</p>
    </section>
  );
}

/**
 * Top-left panel: the way back and the case file. Folded (the default), it is the case's card: the
 * selected pass's turbidity in FNU and its expected range, a trust strip (its level, its seal and
 * its anchor on Sepolia) and how far off the estimate tends to be against guessing the river's
 * usual value. Its details add the place, the pass, the interval's bar, the gauge's own reading at
 * the overpass, the water temperature where Landsat measures it and the gauge's page. The
 * toggle's state is remembered.
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
  onTour,
}: CaseFileProps) {
  const detailsId = useId();
  const [open, setOpen] = usePanelOpen("file");
  const card = reach.card;
  const overall = card?.levels.find((l) => l.predicted_range === "all");
  const lockbox = card?.metrics?.lockbox;
  const estimate = row === null ? null : turbidity(row);
  const value = typeof estimate?.value === "number" ? estimate.value : null;
  const interval = estimate?.interval ?? null;
  const gauge = row === null ? null : gaugeAt(reach, row);
  const unit = estimate?.unit ?? card?.unit ?? "FNU";
  const noGauge = isUngauged(reach);
  const fnuClass = estimate?.fnuClass ?? null;
  const level = estimate?.level ?? overall?.level ?? (noGauge ? "unvalidated" : "none");
  return (
    <div className="case-panel case-top" data-frame="">
      <div className="case-bar" role="group" aria-label={CASE_COPY.tour.bar}>
        <button type="button" className="case-bar__btn case-bar__btn--back" onClick={onBack}>
          <ArrowLeft size={16} strokeWidth={1.75} nonScalingStroke aria-hidden="true" />
          {CASE_COPY.back}
        </button>
        {onTour === undefined ? null : (
          <button
            type="button"
            className="case-bar__btn case-bar__btn--tour"
            aria-label={CASE_COPY.tour.openLabel}
            onClick={onTour}
          >
            <Compass size={16} strokeWidth={1.75} aria-hidden="true" />
            {CASE_COPY.tour.open}
          </button>
        )}
      </div>
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
          <section
            className="case-file__summary"
            data-tour="summary"
            aria-label={noGauge ? ungauged.turbidity : CASE_COPY.turbidity}
          >
            <p className="case-file__metric">
              {noGauge ? ungauged.turbidity : CASE_COPY.turbidity} · {formatDate(row.date, true)}
            </p>
            {noGauge ? (
              <>
                <p className="case-file__value">
                  {fnuClass === null ? (
                    <span className="case-file__none">{ungauged.noClass}</span>
                  ) : (
                    ungauged.classes[fnuClass]
                  )}
                </p>
                <p className="case-file__note">
                  {fnuClass === null
                    ? (estimate?.abstainReason ?? ungauged.label)
                    : (card?.label ?? ungauged.label)}
                </p>
              </>
            ) : value === null ? (
              <>
                <p className="case-file__value">
                  <span className="case-file__none">{CASE_COPY.noValue}</span>
                </p>
                <p className="case-file__note">
                  {estimate?.abstainReason ?? CASE_COPY.rangeWithoutLevel}
                </p>
              </>
            ) : (
              <>
                <p className="case-file__value">
                  {formatValue(value)}
                  <span className="case-file__unit"> {unit}</span>
                </p>
                {interval === null ? null : (
                  <p className="case-file__range-line">
                    <span>
                      {reading.expectedRange} {formatValue(interval.low)}–
                      {formatValue(interval.high)} {unit}
                    </span>
                    {lockbox === undefined ? null : (
                      <HelpTip label={reading.rangeHelpLabel}>
                        {reading.rangeHelp(insideCount(lockbox.coverage90, lockbox.n), lockbox.n)}
                      </HelpTip>
                    )}
                  </p>
                )}
              </>
            )}
            <Trust reach={reach} row={row} level={level} />
            {lockbox === undefined ? null : <Reliability lockbox={lockbox} />}
            {card?.expectedError === undefined ? null : (
              <ExpectedErrorNote error={card.expectedError} />
            )}
          </section>
        )}

        <div className="case-file__details" id={detailsId} hidden={!open}>
          <div className="case-file__section">
            <p className="case-file__place">{reachCase.place}</p>
            <ul className="case-file__chips">
              <li className="case-chip case-chip--quiet">{CASE_COPY.pipelineChip}</li>
              {reach.source === undefined ? null : (
                <li className="case-chip case-chip--quiet" data-source={reach.source}>
                  {reach.source === "live" ? CASE_COPY.liveChip : CASE_COPY.snapshotChip}
                </li>
              )}
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
                  {noGauge
                    ? (estimate?.abstainReason ?? ungauged.label)
                    : (estimate?.abstainReason ?? CASE_COPY.rangeWithoutLevel)}
                </p>
              )}
              <p className="case-file__gauge">
                <span className="case-file__gauge-dot" aria-hidden="true" />
                <span>
                  {noGauge ? (
                    ungauged.noGauge
                  ) : gauge === null ? (
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

          {thermal === null ? null : <Temperature reach={reach} thermal={thermal} />}

          {reach.info.station.window === undefined ? null : (
            <section className="case-file__section" aria-label={ungauged.window}>
              <p className="case-file__metric">{ungauged.window}</p>
              <p className="case-file__note">{reach.info.station.window.basis}</p>
            </section>
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
        </div>
      </article>
    </div>
  );
}
