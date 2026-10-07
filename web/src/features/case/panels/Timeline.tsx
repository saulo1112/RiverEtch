import { useEffect, useId, useRef, useState, type RefObject } from "react";

import { CASE_COPY, daysBetween, formatDate } from "../content.ts";
import { ndtiColor, ndtiPosition } from "../ramp.ts";
import { windowMean } from "../stats.ts";
import type { CaseData } from "../types.ts";

/** Props of {@link Timeline}. */
export interface TimelineProps {
  /** The case. */
  readonly data: CaseData;
}

// Chart geometry (CSS px). Two lanes share one time axis: scenes above, rainfall below; the lanes
// share whatever height the plot gets from case.css (150 px, less on short screens).
const PAD_X = 8;
const LANE_TOP = 22;
const LABEL_SPACE = 28;
const AXIS_SPACE = 24;
const DOT_RADIUS = 4.5;

function useSize(ref: RefObject<HTMLElement | null>): { width: number; height: number } {
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const element = ref.current;
    if (element === null) {
      return undefined;
    }
    const observer = new ResizeObserver(([entry]) => {
      if (entry !== undefined) {
        setSize({
          width: Math.round(entry.contentRect.width),
          height: Math.round(entry.contentRect.height),
        });
      }
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, [ref]);
  return size;
}

// A column with a 2 px rounded top and a square base.
function columnPath(x: number, width: number, base: number, height: number): string {
  const top = base - height;
  const r = Math.min(2, width / 2, height);
  return [
    `M${x},${base}`,
    `V${top + r}`,
    `Q${x},${top} ${x + r},${top}`,
    `H${x + width - r}`,
    `Q${x + width},${top} ${x + width},${top + r}`,
    `V${base}`,
    "Z",
  ].join("");
}

/**
 * Bottom panel: the sparse Sentinel-2 scenes (downstream NDTI, about every 5 days, hatched when
 * cloudy) over the daily upstream rainfall, with the anomaly onset marked. Static for now, with a
 * table for screen readers.
 *
 * @returns The timeline panel.
 */
export function Timeline({ data }: TimelineProps) {
  const plotRef = useRef<HTMLDivElement>(null);
  const { width, height } = useSize(plotRef);
  const hatchId = useId();
  const laneHeight = Math.max(12, (height - LANE_TOP - LABEL_SPACE - AXIS_SPACE) / 2);
  const scenesLane = { top: LANE_TOP, height: laneHeight };
  const rainLane = { top: LANE_TOP + laneHeight + LABEL_SPACE, height: laneHeight };
  const axisY = height - 4;

  const start = data.rainfall[0]?.date ?? data.anomaly.sceneDate;
  const end = data.rainfall.at(-1)?.date ?? data.anomaly.sceneDate;
  const span = Math.max(1, daysBetween(start, end));
  const plotWidth = Math.max(1, width - 2 * PAD_X);
  const x = (date: string) => PAD_X + (daysBetween(start, date) / span) * plotWidth;

  const scenes = data.samples.map((scene) => ({
    date: scene.date,
    ndti: windowMean(scene, data.sampleProgress, data.stats.splitProgress, "downstream"),
  }));
  const sceneY = (ndti: number) => scenesLane.top + (1 - ndtiPosition(ndti)) * scenesLane.height;
  // The line between consecutive clear scenes; a cloudy scene breaks it.
  let trend = "";
  let drawing = false;
  for (const scene of scenes) {
    if (scene.ndti === null) {
      drawing = false;
      continue;
    }
    trend += `${drawing ? "L" : "M"}${x(scene.date).toFixed(1)},${sceneY(scene.ndti).toFixed(1)}`;
    drawing = true;
  }

  const maxRain = Math.max(1, ...data.rainfall.map((day) => day.mm));
  const slot = plotWidth / data.rainfall.length;
  const barWidth = Math.min(24, Math.max(1.5, slot * 0.6));
  const lastRain = data.rainfall.at(-1);
  const rainBase = rainLane.top + rainLane.height;

  // Month starts inside the window, between the two end labels.
  const ticks: string[] = [];
  const cursor = new Date(`${start}T00:00:00Z`);
  cursor.setUTCDate(1);
  cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  while (daysBetween(cursor.toISOString().slice(0, 10), end) > 6) {
    ticks.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }

  const onsetX = x(data.anomaly.onsetDate);
  const onsetLabelEnd = onsetX > width - 120;

  return (
    <section className="case-panel case-timeline case-glass" aria-labelledby="case-timeline-title">
      <header className="case-timeline__head">
        <h2 className="case-timeline__title" id="case-timeline-title">
          {CASE_COPY.timelineTitle}
        </h2>
        {data.illustrative ? <p className="case-chip">{CASE_COPY.illustrativeLabel}</p> : null}
      </header>
      <div className="case-timeline__plot" ref={plotRef}>
        {width > 0 && height > 0 ? (
          <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
            <defs>
              <pattern
                id={hatchId}
                width="4"
                height="4"
                patternUnits="userSpaceOnUse"
                patternTransform="rotate(45)"
              >
                <line x1="0" y1="0" x2="0" y2="4" className="case-timeline__hatch" />
              </pattern>
            </defs>

            <text className="case-timeline__lane" x={PAD_X} y={scenesLane.top - 10}>
              {CASE_COPY.laneScenes}
            </text>
            <text className="case-timeline__lane" x={PAD_X} y={rainLane.top - 10}>
              {CASE_COPY.laneRain}
            </text>

            <line
              className="case-timeline__onset"
              x1={onsetX}
              x2={onsetX}
              y1={scenesLane.top - 6}
              y2={rainBase}
            />
            <text
              className="case-timeline__onset-label"
              x={onsetX + (onsetLabelEnd ? -6 : 6)}
              y={scenesLane.top - 10}
              textAnchor={onsetLabelEnd ? "end" : "start"}
            >
              {CASE_COPY.onset}
            </text>

            <line
              className="case-timeline__baseline"
              x1={PAD_X}
              x2={width - PAD_X}
              y1={rainBase + 0.5}
              y2={rainBase + 0.5}
            />
            {data.rainfall.map((day) => {
              const height = (day.mm / maxRain) * rainLane.height;
              if (height < 0.5) {
                return null;
              }
              return (
                <path
                  key={day.date}
                  className={
                    day === lastRain
                      ? "case-timeline__rain case-timeline__rain--last"
                      : "case-timeline__rain"
                  }
                  d={columnPath(x(day.date) - barWidth / 2, barWidth, rainBase, height)}
                />
              );
            })}
            {lastRain === undefined ? null : (
              <text
                className="case-timeline__value"
                x={x(lastRain.date) - barWidth / 2 - 4}
                y={rainBase - (lastRain.mm / maxRain) * rainLane.height - 2}
                textAnchor="end"
              >
                {lastRain.mm.toFixed(1)}
              </text>
            )}

            <path className="case-timeline__trend" d={trend} />
            {scenes.map((scene) =>
              scene.ndti === null ? (
                <circle
                  key={scene.date}
                  className="case-timeline__cloud"
                  cx={x(scene.date)}
                  cy={scenesLane.top + scenesLane.height / 2}
                  r={DOT_RADIUS}
                  fill={`url(#${hatchId})`}
                />
              ) : (
                <circle
                  key={scene.date}
                  className="case-timeline__scene"
                  cx={x(scene.date)}
                  cy={sceneY(scene.ndti)}
                  r={scene.date === data.anomaly.sceneDate ? DOT_RADIUS + 1.5 : DOT_RADIUS}
                  fill={ndtiColor(scene.ndti)}
                />
              ),
            )}

            <text className="case-timeline__tick" x={PAD_X} y={axisY}>
              {formatDate(start)}
            </text>
            {ticks.map((tick) => (
              <text
                key={tick}
                className="case-timeline__tick"
                x={x(tick)}
                y={axisY}
                textAnchor="middle"
              >
                {formatDate(tick)}
              </text>
            ))}
            <text className="case-timeline__tick" x={width - PAD_X} y={axisY} textAnchor="end">
              {formatDate(end)}
            </text>
          </svg>
        ) : null}
      </div>
      <table className="case-visually-hidden">
        <caption>
          {CASE_COPY.timelineTitle} ({CASE_COPY.illustrativeLabel})
        </caption>
        <thead>
          <tr>
            <th scope="col">Scene</th>
            <th scope="col">{CASE_COPY.laneScenes}</th>
            <th scope="col">Rainfall that day (mm)</th>
          </tr>
        </thead>
        <tbody>
          {scenes.map((scene) => (
            <tr key={scene.date}>
              <th scope="row">
                {formatDate(scene.date, true)}
                {scene.date === data.anomaly.onsetDate ? ` (${CASE_COPY.onset})` : ""}
              </th>
              <td>{scene.ndti === null ? CASE_COPY.cloudy : scene.ndti.toFixed(3)}</td>
              <td>{data.rainfall.find((day) => day.date === scene.date)?.mm.toFixed(1) ?? "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
