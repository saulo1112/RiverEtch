import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import type { ReactNode } from "react";

import type { PassStats, ProfilePoint } from "../../reaches/analysis.ts";
import { thermalValidatedAt } from "../../reaches/scene.ts";
import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY } from "../content.ts";
import { ClimateView } from "./ClimateView.tsx";
import { PassStatsView } from "./PassStatsView.tsx";
import { ProfileChart } from "./ProfileChart.tsx";
import { SeriesChart } from "./SeriesChart.tsx";
import { ThermalChart } from "./ThermalChart.tsx";
import { WaterQualityView } from "./WaterQualityView.tsx";

/** The bottom panel's tabs. */
export type BottomTab = "quality" | "series" | "thermal" | "climate" | "profile" | "pass";

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

const TABS: readonly BottomTab[] = ["quality", "series", "thermal", "climate", "profile", "pass"];

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

// The tab's caption: what its marks mean, or how to read it. Inside the tab panel, under the tab
// strip, so a caption of any length never moves the strip.
function Caption({ tab, reach }: { readonly tab: BottomTab; readonly reach: ReachData }) {
  const upstream = thermalValidatedAt(reach);
  if (tab === "series") {
    return (
      <ul className="case-timeline__caption case-timeline__keys">
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
          <span className="case-timeline__key case-timeline__key--cursor" aria-hidden="true" />
          {CASE_COPY.thermal.cursor}
        </li>
      </ul>
    );
  }
  if (tab === "climate") {
    return (
      <p className="case-timeline__caption">
        {CASE_COPY.climate.lead} (
        <a href={CASE_COPY.climate.citeUrl} target="_blank" rel="noreferrer">
          {CASE_COPY.climate.cite}
        </a>
        ). {CASE_COPY.climate.note}
      </p>
    );
  }
  if (tab === "profile") {
    return <p className="case-timeline__caption">{CASE_COPY.profile.hint}</p>;
  }
  return null;
}

/**
 * Bottom panel: the year's passes (turbidity in FNU beside the gauge), the water temperature from
 * Landsat where the reach has it, the gauge's whole record as climate context, the selected pass
 * along the river, and its statistics and the gauge's readings, on tabs; the time-lapse plays the
 * year pass by pass. The head is a fixed grid (transport, tabs centred, an empty column) and the
 * tab panel has a fixed height, so the tab strip never moves when the tab or the time-lapse
 * changes.
 *
 * @param props - The reach, the selection, the tab, the time-lapse and the pass's analysis.
 * @returns The panel.
 */
export function Timeline(props: TimelineProps) {
  const { reach, selected, tab, playing } = props;
  const { play, tabs } = CASE_COPY;
  const last = reach.series.length - 1;
  const row = reach.series[selected] ?? null;
  const shown = TABS.filter(
    (t) =>
      (t !== "thermal" || reach.thermal !== null) && (t !== "climate" || reach.climate !== null),
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
        <div className="case-timeline__tabs" role="tablist">
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
        <Caption tab={tab} reach={reach} />
        <div className="case-timeline__view">
          {tab === "quality" ? (
            <WaterQualityView reach={reach} selected={selected} />
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
            <ClimateView climate={reach.climate} />
          ) : tab === "profile" ? (
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
