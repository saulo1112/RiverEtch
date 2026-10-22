import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { useState, type ReactNode } from "react";

import type { PassStats, ProfilePoint } from "../../reaches/analysis.ts";
import { isUngauged, thermalValidatedAt } from "../../reaches/scene.ts";
import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY } from "../content.ts";
import { ALONG_CLASSES, CLASS_COLORS } from "../../reaches/along.ts";
import { chartYears, sealedYear, yearPhases, yearReach } from "../../reaches/history.ts";
import { AlongView } from "./AlongView.tsx";
import { ClimateView, type ClimateTabView } from "./ClimateView.tsx";
import { HelpTip } from "./HelpTip.tsx";
import { PassStatsView } from "./PassStatsView.tsx";
import { ProfileChart } from "./ProfileChart.tsx";
import { ScoreboardView } from "./ScoreboardView.tsx";
import { SeriesChart } from "./SeriesChart.tsx";
import { ThermalChart } from "./ThermalChart.tsx";
import { WaterQualityView } from "./WaterQualityView.tsx";

/** The bottom panel's tabs. */
export type BottomTab =
  "quality" | "series" | "along" | "thermal" | "climate" | "pass" | "scoreboard";

/** What the "This pass" tab shows: its statistics, or its NDTI along the river. */
type PassView = "stats" | "profile";

/** Props of {@link Timeline}. */
export interface TimelineProps {
  readonly reach: ReachData;
  /** Index of the selected pass in the series. */
  readonly selected: number;
  /** The pass compared with it (compare mode). */
  readonly compared: number | null;
  /** Selects a pass. */
  readonly onSelect: (index: number) => void;
  /** Index of the selected Landsat pass (water temperature; null: none). */
  readonly thermalSelected: number | null;
  /** Selects a Landsat pass. */
  readonly onThermalSelect: (index: number) => void;
  readonly tab: BottomTab;
  readonly onTab: (tab: BottomTab) => void;
  /** The time-lapse is running. */
  readonly playing: boolean;
  readonly onPlaying: (playing: boolean) => void;
  /** The selected pass's profile and statistics (null while it loads). */
  readonly profile: readonly ProfilePoint[] | null;
  readonly stats: PassStats | null;
  /** The NDTI ramp's domain. */
  readonly domain: readonly [number, number];
  /** The profile's cursor moved to a place along the river. */
  readonly onProbe: (place: number | null) => void;
}

const TABS: readonly BottomTab[] = [
  "quality",
  "series",
  "along",
  "thermal",
  "climate",
  "pass",
  "scoreboard",
];

function IconButton({
  label,
  onClick,
  children,
  pressed,
}: {
  readonly label: string;
  readonly onClick: () => void;
  readonly children: ReactNode;
  readonly pressed?: boolean;
}) {
  return (
    <button
      type="button"
      className="case-timeline__icon"
      onClick={onClick}
      aria-pressed={pressed}
      title={label}
    >
      {children}
      <span className="case-visually-hidden">{label}</span>
    </button>
  );
}

// A tab's two views, as a segmented switch in its caption.
function Switch<V extends string>({
  label,
  views,
  value,
  onChange,
}: {
  readonly label: string;
  readonly views: readonly { readonly id: V; readonly label: string }[];
  readonly value: V;
  readonly onChange: (view: V) => void;
}) {
  return (
    <div className="case-tools__segmented" role="radiogroup" aria-label={label}>
      {views.map((view) => (
        <button
          key={view.id}
          type="button"
          role="radio"
          aria-checked={value === view.id}
          className="case-tools__segment"
          onClick={() => {
            onChange(view.id);
          }}
        >
          {view.label}
        </button>
      ))}
    </div>
  );
}

// The tab's caption: what its marks mean, or how to read it (on "This pass" and, where the record
// counts extreme days, on "Climate", the switch between the tab's two views). Inside the tab panel,
// under the tab strip, so a caption of any length never moves the strip.
function Caption({
  tab,
  reach,
  passView,
  onPassView,
  climateView,
  onClimateView,
  year,
  onYear,
}: {
  readonly tab: BottomTab;
  readonly reach: ReachData;
  readonly year: number;
  readonly onYear: (year: number) => void;
  readonly passView: PassView;
  readonly onPassView: (view: PassView) => void;
  readonly climateView: ClimateTabView;
  readonly onClimateView: (view: ClimateTabView) => void;
}) {
  const upstream = thermalValidatedAt(reach);
  const years = chartYears(reach);
  const picker =
    tab === "series" && years.length > 1 ? (
      <label className="case-timeline__year">
        <span className="case-visually-hidden">{CASE_COPY.history.yearLabel}</span>
        <select
          className="case-timeline__year-select"
          value={year}
          aria-label={CASE_COPY.history.yearLabel}
          onChange={(event) => {
            onYear(Number(event.target.value));
          }}
        >
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </label>
    ) : null;
  if (tab === "series" && year !== sealedYear(reach)) {
    const { history } = CASE_COPY;
    const phases = yearPhases(reach.history ?? [], year)
      .map((p) => history.phases[p])
      .join(", then ");
    return (
      <p className="case-timeline__caption case-timeline__keys">
        {picker}
        <span>{phases === "" ? history.noPasses : history.line(phases)}</span>
        <HelpTip label={history.helpLabel} float>
          {history.help}
        </HelpTip>
      </p>
    );
  }
  if (tab === "series" && isUngauged(reach)) {
    return (
      <ul className="case-timeline__caption case-timeline__keys">
        {picker === null ? null : <li>{picker}</li>}
        <li>
          <span className="case-timeline__key case-timeline__key--sat" aria-hidden="true" />
          {CASE_COPY.ungauged.chartKey}
        </li>
        <li>
          <span className="case-timeline__key case-timeline__key--none" aria-hidden="true" />
          {CASE_COPY.ungauged.noClass}
        </li>
      </ul>
    );
  }
  if (tab === "series") {
    return (
      <ul className="case-timeline__caption case-timeline__keys">
        {picker === null ? null : <li>{picker}</li>}
        <li>
          <span className="case-timeline__key case-timeline__key--sat" aria-hidden="true" />
          {CASE_COPY.timelineSatellite}
        </li>
        <li>
          <span className="case-timeline__key case-timeline__key--gauge" aria-hidden="true" />
          {CASE_COPY.timelineGauge}
        </li>
        <li>
          <span className="case-timeline__key case-timeline__key--none" aria-hidden="true" />
          {CASE_COPY.timelineNoValue}
        </li>
      </ul>
    );
  }
  if (tab === "thermal") {
    return (
      <ul className="case-timeline__caption case-timeline__keys">
        <li>
          <span className="case-timeline__key case-timeline__key--thermal" aria-hidden="true" />
          {CASE_COPY.thermal.satellite}
        </li>
        <li>
          <span className="case-timeline__key case-timeline__key--gauge" aria-hidden="true" />
          {upstream === null ? CASE_COPY.thermal.gauge : CASE_COPY.thermal.upstreamGauge(upstream)}
        </li>
        <li>
          <span className="case-timeline__key case-timeline__key--picked" aria-hidden="true" />
          {CASE_COPY.thermal.picked}
        </li>
        <li>
          <span className="case-timeline__key case-timeline__key--cursor" aria-hidden="true" />
          {CASE_COPY.thermal.cursor}
        </li>
      </ul>
    );
  }
  if (tab === "climate") {
    const { climate } = CASE_COPY;
    const station = reach.climate?.station;
    const lead = (
      <span>
        {climate.lead} (
        <a href={climate.citeUrl} target="_blank" rel="noreferrer">
          {climate.cite}
        </a>
        ).{" "}
        {station?.modelled === true ? (
          <>
            {climate.model.before}
            <a href={climate.model.url} target="_blank" rel="noreferrer">
              {climate.model.link}
            </a>
            {climate.model.after}
            {/* Why the 7-day low is not ranked, here too: short screens hide it beside the chart. */}
            {station.basis === undefined ? null : (
              <HelpTip label={climate.model.helpLabel}>
                {station.basis} {reach.climate?.discharge.lowsNote}
              </HelpTip>
            )}
          </>
        ) : station?.context === true ? (
          <>
            {climate.noteContext(station.name)}
            {station.basis === undefined ? null : (
              <HelpTip label={climate.contextHelpLabel}>{station.basis}</HelpTip>
            )}
          </>
        ) : (
          climate.note
        )}
      </span>
    );
    if (reach.climate?.extremes === undefined) {
      return <p className="case-timeline__caption">{lead}</p>;
    }
    return (
      <div className="case-timeline__caption case-timeline__switch">
        <Switch
          label={climate.views.label}
          views={[
            { id: "values", label: climate.views.values },
            { id: "days", label: climate.views.days },
          ]}
          value={climateView}
          onChange={onClimateView}
        />
        {lead}
      </div>
    );
  }
  if (tab === "pass") {
    const { pass } = CASE_COPY;
    return (
      <div className="case-timeline__caption case-timeline__switch">
        <Switch
          label={pass.views}
          views={[
            { id: "stats", label: pass.stats },
            { id: "profile", label: pass.profile },
          ]}
          value={passView}
          onChange={onPassView}
        />
        {passView === "profile" ? <span>{CASE_COPY.profile.hint}</span> : null}
      </div>
    );
  }
  if (tab === "scoreboard") {
    return <p className="case-timeline__caption">{CASE_COPY.scoreboard.caption}</p>;
  }
  if (tab === "along") {
    const { along, ungauged } = CASE_COPY;
    return (
      <ul className="case-timeline__caption case-timeline__keys" data-tour="along">
        {ALONG_CLASSES.map((c) => (
          <li key={c}>
            <span
              className="case-timeline__key case-timeline__key--class"
              style={{ background: CLASS_COLORS[c] }}
              aria-hidden="true"
            />
            {along.short[c] ?? ungauged.classes[c]}
          </li>
        ))}
        <li>
          <span className="case-timeline__key case-timeline__key--class-none" aria-hidden="true" />
          <span>
            {along.noReading}
            <span className="case-timeline__keys-more">{along.noReadingWhy}</span>
          </span>
        </li>
        <li className="case-timeline__keys-note">{along.hint}</li>
      </ul>
    );
  }
  return null;
}

/**
 * Bottom panel: the year's passes (turbidity in FNU beside the gauge), the water temperature from
 * Landsat where the reach has it, the gauge's whole record as climate context, the selected pass
 * (its statistics, or its NDTI along the river), the scoreboard and every evaluated river, on tabs;
 * the time-lapse plays the year pass by pass. The head is a fixed grid (transport, tabs centred,
 * an empty column) and the tab panel has a fixed height, so the tab strip never moves when the tab
 * or the time-lapse changes.
 *
 * @param props - The reach, the selection, the tab, the time-lapse and the pass's analysis.
 * @returns The panel.
 */
export function Timeline(props: TimelineProps) {
  const { reach, selected, tab, playing } = props;
  const { play, tabs } = CASE_COPY;
  const [passView, setPassView] = useState<PassView>("stats");
  const [climateView, setClimateView] = useState<ClimateTabView>("values");
  const [year, setYear] = useState(() => sealedYear(reach));
  const [earlier, setEarlier] = useState(0);
  const pastYear = year !== sealedYear(reach) ? yearReach(reach, year) : null;
  const last = reach.series.length - 1;
  const row = reach.series[selected] ?? null;
  // A reach with no gauge is never scored: no scoreboard.
  const shown = TABS.filter(
    (t) =>
      (t !== "thermal" || reach.thermal !== null) &&
      (t !== "climate" || reach.climate !== null) &&
      (t !== "scoreboard" || !isUngauged(reach)),
  );
  return (
    <section className="case-panel case-timeline case-glass" data-frame="" aria-label={tabs[tab]}>
      <header className="case-timeline__head">
        <div className="case-timeline__transport">
          <IconButton
            label={play.previous}
            onClick={() => {
              props.onSelect(Math.max(0, selected - 1));
            }}
          >
            <SkipBack size={15} strokeWidth={1.9} aria-hidden="true" />
          </IconButton>
          <button
            type="button"
            className="case-timeline__play"
            aria-pressed={playing}
            onClick={() => {
              props.onPlaying(!playing);
            }}
          >
            {/* Both labels share one cell, so the button keeps the longer one's width. */}
            <span className="case-timeline__play-face" data-shown={!playing}>
              <Play size={15} strokeWidth={2} aria-hidden="true" />
              {play.play}
            </span>
            <span className="case-timeline__play-face" data-shown={playing}>
              <Pause size={15} strokeWidth={2} aria-hidden="true" />
              {play.pause}
            </span>
          </button>
          <IconButton
            label={play.next}
            onClick={() => {
              props.onSelect(Math.min(last, selected + 1));
            }}
          >
            <SkipForward size={15} strokeWidth={1.9} aria-hidden="true" />
          </IconButton>
        </div>
        <div className="case-timeline__tabs" role="tablist" data-tour="tabs">
          {shown.map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              className="case-timeline__tab"
              onClick={() => {
                props.onTab(t);
              }}
            >
              {tabs[t]}
            </button>
          ))}
        </div>
      </header>
      <div className="case-timeline__body" role="tabpanel">
        <Caption
          tab={tab}
          reach={reach}
          passView={passView}
          onPassView={(view) => {
            setPassView(view);
            props.onProbe(null);
          }}
          climateView={climateView}
          onClimateView={setClimateView}
          year={year}
          onYear={(y) => {
            setYear(y);
            setEarlier(0);
          }}
        />
        <div className="case-timeline__view">
          {tab === "quality" ? (
            <WaterQualityView reach={reach} selected={selected} />
          ) : tab === "series" && pastYear !== null ? (
            <SeriesChart
              reach={pastYear}
              selected={Math.min(earlier, Math.max(0, pastYear.series.length - 1))}
              compared={null}
              onSelect={setEarlier}
            />
          ) : tab === "series" ? (
            <SeriesChart
              reach={reach}
              selected={selected}
              compared={props.compared}
              onSelect={props.onSelect}
            />
          ) : tab === "thermal" ? (
            <ThermalChart
              reach={reach}
              selected={props.thermalSelected}
              cursor={row?.date ?? null}
              onSelect={props.onThermalSelect}
            />
          ) : tab === "climate" && reach.climate !== null ? (
            <ClimateView climate={reach.climate} view={climateView} />
          ) : tab === "scoreboard" ? (
            <ScoreboardView reach={reach} t0={__PROSPECTIVE_T0__} />
          ) : tab === "along" ? (
            <AlongView
              reach={reach}
              selected={selected}
              onSelect={props.onSelect}
              onProbe={props.onProbe}
            />
          ) : passView === "profile" ? (
            <ProfileChart
              reach={reach}
              points={props.profile}
              domain={props.domain}
              onProbe={props.onProbe}
            />
          ) : (
            <PassStatsView stats={props.stats} />
          )}
        </div>
      </div>
    </section>
  );
}
