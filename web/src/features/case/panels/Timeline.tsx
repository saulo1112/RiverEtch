import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { useState, type ReactNode } from "react";

import type { PassStats, ProfilePoint } from "../../reaches/analysis.ts";
import { isUngauged, thermalValidatedAt, turbidity } from "../../reaches/scene.ts";
import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY } from "../content.ts";
import {
  ALONG_CLASSES,
  CLASS_COLORS,
  TEMPERATURE_CLASSES,
  TEMPERATURE_COLORS,
  TEMPERATURE_EDGES,
} from "../../reaches/along.ts";
import { yearPhases } from "../../reaches/archive.ts";
import { temperaturePoints, turbidityPoints, type Spot } from "../spot.ts";
import { AlongView, type AlongVariable } from "./AlongView.tsx";
import {
  primaryText,
  secondaryText,
  stretchReach,
  stretchShown,
  stretchValued,
} from "../turbidity.ts";
import { BandChart } from "./BandChart.tsx";
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
  /** The reading spot, away from the start (null: at the start). */
  readonly spot: Spot | null;
  /** Moves the reading spot to a window. */
  readonly onSpot: (index: number) => void;
}

// The turbidity classes' edges along the river (four classes) and their words.
const ALONG_EDGES = [30, 50, 100];
const turbidityWords = (cls: string) =>
  CASE_COPY.ungauged.classes[cls as keyof typeof CASE_COPY.ungauged.classes];
const temperatureWords = (cls: string) => CASE_COPY.temperatureClasses[cls] ?? cls;

// Whether the reach has water temperature along the river.
const hasAlongTemperature = (reach: ReachData) =>
  reach.thermal !== null && (reach.alongTemperature?.length ?? 0) > 0;

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
  spot,
  variable,
  onVariable,
}: {
  readonly tab: BottomTab;
  readonly reach: ReachData;
  readonly spot: Spot | null;
  readonly variable: AlongVariable;
  readonly onVariable: (variable: AlongVariable) => void;
  readonly passView: PassView;
  readonly onPassView: (view: PassView) => void;
  readonly climateView: ClimateTabView;
  readonly onClimateView: (view: ClimateTabView) => void;
}) {
  const upstream = thermalValidatedAt(reach);
  // An earlier year (preregistration-archive.md): recomputed, not sealed, and what its passes
  // were to the model, said first on its charts.
  const { archive } = CASE_COPY;
  const phases = yearPhases(reach)
    .map((p) => archive.phases[p])
    .join(", then ");
  const recomputed =
    reach.archive == null || (tab !== "series" && tab !== "thermal" && tab !== "quality") ? null : (
      <li className="case-timeline__archive">
        <span className="case-chip case-chip--archive">{archive.label}</span>
        <span>{phases}</span>
        <HelpTip label={archive.helpLabel} float>
          {archive.help}
        </HelpTip>
      </li>
    );
  // Away from the start: the stretch's classes, the height meaning the class only.
  if (spot !== null && (tab === "series" || tab === "thermal")) {
    return (
      <ul className="case-timeline__caption case-timeline__keys">
        {recomputed}
        <li>
          <span
            className={`case-timeline__key case-timeline__key--${tab === "series" ? "sat" : "thermal"}`}
            aria-hidden="true"
          />
          {tab === "series"
            ? stretchValued(reach)
              ? CASE_COPY.spot.chartKeyValue(spot.stretch)
              : CASE_COPY.spot.chartKey(spot.stretch)
            : CASE_COPY.spot.temperatureKey(spot.stretch)}
        </li>
        {tab === "thermal" ? (
          <li>
            <span className="case-timeline__key case-timeline__key--cursor" aria-hidden="true" />
            {CASE_COPY.thermal.cursor}
          </li>
        ) : null}
      </ul>
    );
  }
  if (tab === "quality" && recomputed !== null) {
    return <ul className="case-timeline__caption case-timeline__keys">{recomputed}</ul>;
  }
  if (tab === "series" && isUngauged(reach)) {
    return (
      <ul className="case-timeline__caption case-timeline__keys">
        {recomputed}
        <li>
          <span className="case-timeline__key case-timeline__key--sat" aria-hidden="true" />
          {reach.series.some((r) => typeof turbidity(r)?.value === "number")
            ? CASE_COPY.ungauged.chartKeyValue
            : CASE_COPY.ungauged.chartKey}
        </li>
      </ul>
    );
  }
  if (tab === "series") {
    return (
      <ul className="case-timeline__caption case-timeline__keys">
        {recomputed}
        <li>
          <span className="case-timeline__key case-timeline__key--sat" aria-hidden="true" />
          {CASE_COPY.timelineSatellite}
        </li>
        {reach.archive == null ? (
          <li>
            <span className="case-timeline__key case-timeline__key--gauge" aria-hidden="true" />
            {CASE_COPY.timelineGauge}
          </li>
        ) : null}
      </ul>
    );
  }
  if (tab === "thermal") {
    return (
      <ul className="case-timeline__caption case-timeline__keys">
        {recomputed}
        <li>
          <span className="case-timeline__key case-timeline__key--thermal" aria-hidden="true" />
          {CASE_COPY.thermal.satellite}
        </li>
        <li hidden={reach.archive != null}>
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
    // The year's flow first, where the usual flow is written (preregistration-daily-record.md).
    const flow = reach.climate?.discharge.typical != null;
    const views: { id: ClimateTabView; label: string }[] = [
      ...(flow ? [{ id: "flow" as const, label: climate.views.flow }] : []),
      { id: "values", label: climate.views.values },
      ...(reach.climate?.extremes === undefined
        ? []
        : [{ id: "days" as const, label: climate.views.days }]),
    ];
    if (views.length < 2) {
      return <p className="case-timeline__caption">{lead}</p>;
    }
    return (
      <div className="case-timeline__caption case-timeline__switch">
        <Switch
          label={climate.views.label}
          views={views}
          value={views.some((v) => v.id === climateView) ? climateView : "values"}
          onChange={onClimateView}
        />
        {climateView === "flow" && flow ? <span>{climate.flow.lead}</span> : lead}
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
    const { along } = CASE_COPY;
    const temperature = variable === "temperature" && hasAlongTemperature(reach);
    const classes: readonly string[] = temperature ? TEMPERATURE_CLASSES : ALONG_CLASSES;
    const colors: Readonly<Record<string, string>> = temperature
      ? TEMPERATURE_COLORS
      : CLASS_COLORS;
    const short = temperature ? along.shortTemperature : along.short;
    return (
      <div className="case-timeline__caption case-timeline__switch" data-tour="along">
        {hasAlongTemperature(reach) ? (
          <Switch
            label={along.variable.label}
            views={[
              { id: "turbidity", label: along.variable.turbidity },
              { id: "temperature", label: along.variable.temperature },
            ]}
            value={temperature ? "temperature" : "turbidity"}
            onChange={onVariable}
          />
        ) : null}
        <ul className="case-timeline__keys">
          {classes.map((c, k) => (
            // On a phone only the first and last classes keep their words: a ramp, ends named.
            <li key={c} data-middle={k > 0 && k < classes.length - 1}>
              <span
                className="case-timeline__key case-timeline__key--class"
                style={{ background: colors[c] }}
                aria-hidden="true"
              />
              <span className="case-timeline__key-text">{short[c] ?? c}</span>
            </li>
          ))}
          <li>
            <span
              className="case-timeline__key case-timeline__key--class-none"
              aria-hidden="true"
            />
            {along.noReading}
          </li>
          <li className="case-timeline__keys-note">{along.hint}</li>
        </ul>
      </div>
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
  // The year's flow first where the reach has its usual flow, else the yearly values.
  const [climateView, setClimateView] = useState<ClimateTabView>(() =>
    reach.climate?.discharge.typical != null ? "flow" : "values",
  );
  const [variable, setVariable] = useState<AlongVariable>("turbidity");
  const { spot } = props;
  const alongTemperature = variable === "temperature" && hasAlongTemperature(reach);
  const last = reach.series.length - 1;
  const row = reach.series[selected] ?? null;
  // A reach with no gauge is never scored: no scoreboard. An earlier year keeps no image of its
  // passes and no track record: no image details, no scoreboard.
  const archived = reach.archive != null;
  const shown = TABS.filter(
    (t) =>
      (t !== "thermal" || reach.thermal !== null) &&
      (t !== "climate" || reach.climate !== null) &&
      (t !== "scoreboard" || (!isUngauged(reach) && !archived)) &&
      (t !== "pass" || !archived),
  );
  const year = (row?.date ?? reach.series.at(-1)?.date ?? "2026").slice(0, 4);
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
              {play.play(year)}
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
          spot={spot}
          variable={variable}
          onVariable={setVariable}
        />
        <div className="case-timeline__view">
          {tab === "quality" ? (
            <WaterQualityView reach={reach} selected={selected} spot={spot} />
          ) : tab === "series" && spot !== null && stretchValued(reach) ? (
            // The stretch's values, as the station's are drawn (preregistration-values.md).
            <SeriesChart
              reach={stretchReach(reach, spot.index)}
              selected={selected}
              compared={props.compared}
              onSelect={props.onSelect}
            />
          ) : tab === "series" && spot !== null ? (
            <BandChart
              points={turbidityPoints(reach, spot.index).map((p) => {
                // The stretch's value beside its class, where its record carries one.
                const shown = stretchShown(
                  reach,
                  reach.series[p.index]?.sceneId,
                  spot.index,
                  __TRANSFER_POOLED__.mdsa,
                );
                return shown?.value == null
                  ? p
                  : { ...p, text: primaryText(shown), detail: secondaryText(shown) };
              })}
              classes={ALONG_CLASSES}
              edges={ALONG_EDGES}
              unit="FNU"
              label={turbidityWords}
              selected={selected}
              onSelect={props.onSelect}
              ariaLabel={CASE_COPY.timelineHint}
              idPrefix="case-stretch"
            />
          ) : tab === "thermal" && spot !== null ? (
            <BandChart
              points={temperaturePoints(reach, spot.index)}
              classes={TEMPERATURE_CLASSES}
              edges={TEMPERATURE_EDGES}
              unit="°C"
              label={temperatureWords}
              selected={props.thermalSelected}
              cursor={row?.date ?? null}
              onSelect={props.onThermalSelect}
              ariaLabel={CASE_COPY.thermal.hint}
              idPrefix="case-stretch-thermal"
              tone="thermal"
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
            <ClimateView climate={reach.climate} view={climateView} reach={reach} />
          ) : tab === "scoreboard" ? (
            <ScoreboardView reach={reach} t0={__PROSPECTIVE_T0__} />
          ) : tab === "along" ? (
            <AlongView
              reach={reach}
              variable={alongTemperature ? "temperature" : "turbidity"}
              selected={alongTemperature ? props.thermalSelected : selected}
              onSelect={alongTemperature ? props.onThermalSelect : props.onSelect}
              spot={spot?.index ?? null}
              onSpot={props.onSpot}
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
