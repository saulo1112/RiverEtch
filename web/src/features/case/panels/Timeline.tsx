import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import type { ReactNode } from "react";

import type { PassStats, ProfilePoint } from "../../reaches/analysis.ts";
import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY } from "../content.ts";
import { PassStatsView } from "./PassStatsView.tsx";
import { ProfileChart } from "./ProfileChart.tsx";
import { SeriesChart } from "./SeriesChart.tsx";

/** The bottom panel's tabs. */
export type BottomTab = "series" | "profile" | "pass";

/** Props of {@link Timeline}. */
export interface TimelineProps {
  readonly reach: ReachData;
  /** Index of the selected pass in the series. */
  readonly selected: number;
  /** The pass compared with it (compare mode). */
  readonly compared: number | null;
  /** Selects a pass. */
  readonly onSelect: (index: number) => void;
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

const TABS: readonly BottomTab[] = ["series", "profile", "pass"];

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

/**
 * Bottom panel: the year's passes (turbidity in FNU beside the gauge), the selected pass along
 * the river, and its statistics, on three tabs; the time-lapse plays the year pass by pass.
 *
 * @param props - The reach, the selection, the tab, the time-lapse and the pass's analysis.
 * @returns The panel.
 */
export function Timeline(props: TimelineProps) {
  const { reach, selected, tab, playing } = props;
  const { play, tabs } = CASE_COPY;
  const last = reach.series.length - 1;
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
            {playing ? (
              <Pause size={15} strokeWidth={2} aria-hidden="true" />
            ) : (
              <Play size={15} strokeWidth={2} aria-hidden="true" />
            )}
            {playing ? play.pause : play.play}
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
          {TABS.map((t) => (
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
        {tab === "series" ? (
          <ul className="case-timeline__keys">
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
        ) : tab === "profile" ? (
          <p className="case-timeline__note">{CASE_COPY.profile.hint}</p>
        ) : null}
      </header>
      <div className="case-timeline__body" role="tabpanel">
        {tab === "series" ? (
          <SeriesChart
            reach={reach}
            selected={selected}
            compared={props.compared}
            onSelect={props.onSelect}
          />
        ) : tab === "profile" ? (
          <ProfileChart
            reach={reach}
            points={props.profile}
            domain={props.domain}
            onProbe={props.onProbe}
          />
        ) : (
          <PassStatsView stats={props.stats} row={reach.series[selected] ?? null} />
        )}
      </div>
    </section>
  );
}
