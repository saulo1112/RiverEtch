import { useEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";

import { gaugeAt, turbidity } from "../../reaches/scene.ts";
import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY, daysBetween, formatDate, formatValue } from "../content.ts";

/** Props of {@link Timeline}. */
export interface TimelineProps {
  /** The reach. */
  readonly reach: ReachData;
  /** Index of the selected pass in the series. */
  readonly selected: number;
  /** Selects a pass. */
  readonly onSelect: (index: number) => void;
}

// Chart geometry (CSS px): the plot keeps room for the value axis on the left and the month axis
// below; the height comes from case.css.
const PAD = { left: 34, right: 10, top: 10, bottom: 22 };
const DOT = 4.5;
const TICKS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];

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

/**
 * Bottom panel: the year's passes as a turbidity chart on a log scale. Each pass with a value is
 * a dot with its 90 % interval; the USGS gauge's own reading at the overpass sits beside it as a
 * ring; a pass without a value is a small mark on the axis. Clicking a pass, or the arrow keys,
 * selects it.
 *
 * @returns The timeline panel.
 */
export function Timeline({ reach, selected, onSelect }: TimelineProps) {
  const plotRef = useRef<HTMLDivElement>(null);
  const { width, height } = useSize(plotRef);
  const { series } = reach;
  const points = series.map((row, index) => {
    const estimate = turbidity(row);
    const value = typeof estimate?.value === "number" ? estimate.value : null;
    return {
      index,
      row,
      value,
      low: estimate?.interval?.low ?? null,
      high: estimate?.interval?.high ?? null,
      gauge: gaugeAt(reach, row)?.value ?? null,
    };
  });

  const values = points.flatMap((p) =>
    [p.value, p.low, p.high, p.gauge].filter((v): v is number => v !== null && v > 0),
  );
  const yMin = Math.max(0.5, Math.min(...values, 10) * 0.8);
  const yMax = Math.max(...values, 20) * 1.15;
  const first = series[0]?.date ?? "2026-01-01";
  const start = `${first.slice(0, 4)}-01-01`;
  const end = series.at(-1)?.date ?? first;
  const span = Math.max(30, daysBetween(start, end) + 6);
  const plotWidth = Math.max(1, width - PAD.left - PAD.right);
  const plotHeight = Math.max(1, height - PAD.top - PAD.bottom);
  const x = (date: string) => PAD.left + (daysBetween(start, date) / span) * plotWidth;
  const y = (v: number) => PAD.top + (1 - Math.log(v / yMin) / Math.log(yMax / yMin)) * plotHeight;
  const baseY = PAD.top + plotHeight;

  const months: string[] = [];
  const cursor = new Date(`${start}T00:00:00Z`);
  while (daysBetween(cursor.toISOString().slice(0, 10), end) >= 0) {
    months.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  const yTicks = TICKS.filter((t) => t >= yMin && t <= yMax);

  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step !== 0) {
      event.preventDefault();
      onSelect(Math.min(series.length - 1, Math.max(0, selected + step)));
    }
  };

  const current = points[selected];
  return (
    <section className="case-panel case-timeline case-glass" aria-labelledby="case-timeline-title">
      <header className="case-timeline__head">
        <h2 className="case-timeline__title" id="case-timeline-title">
          {CASE_COPY.timelineTitle}
        </h2>
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
      </header>
      <div
        className="case-timeline__plot"
        ref={plotRef}
        role="listbox"
        tabIndex={0}
        aria-label={CASE_COPY.timelineHint}
        aria-activedescendant={current === undefined ? undefined : `case-pass-${String(selected)}`}
        onKeyDown={onKey}
      >
        {width > 0 && height > 0 ? (
          <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
            {yTicks.map((t) => (
              <g key={t}>
                <line
                  className="case-timeline__grid"
                  x1={PAD.left}
                  x2={width - PAD.right}
                  y1={y(t)}
                  y2={y(t)}
                />
                <text
                  className="case-timeline__tick"
                  x={PAD.left - 6}
                  y={y(t) + 3.5}
                  textAnchor="end"
                >
                  {t}
                </text>
              </g>
            ))}
            <text className="case-timeline__unit" x={PAD.left - 6} y={PAD.top - 1} textAnchor="end">
              FNU
            </text>
            {months.map((m) => (
              <text
                key={m}
                className="case-timeline__tick"
                x={x(m) + 2}
                y={height - 6}
                textAnchor="start"
              >
                {formatDate(m).split(" ")[1]}
              </text>
            ))}
            {current === undefined ? null : (
              <line
                className="case-timeline__cursor"
                x1={x(current.row.date)}
                x2={x(current.row.date)}
                y1={PAD.top}
                y2={baseY}
              />
            )}
            {points.map((p) =>
              p.value === null || p.low === null || p.high === null ? null : (
                <line
                  key={`i${String(p.index)}`}
                  className="case-timeline__interval"
                  x1={x(p.row.date)}
                  x2={x(p.row.date)}
                  y1={y(p.high)}
                  y2={y(p.low)}
                />
              ),
            )}
            {points.map((p) =>
              p.gauge === null ? null : (
                <circle
                  key={`g${String(p.index)}`}
                  className="case-timeline__gauge"
                  cx={x(p.row.date) + 5}
                  cy={y(p.gauge)}
                  r={3.4}
                />
              ),
            )}
            {points.map((p) =>
              p.value === null ? (
                <path
                  key={`n${String(p.index)}`}
                  className="case-timeline__none"
                  d={`M${String(x(p.row.date) - 3)},${String(baseY - 3)}l6,6m0,-6l-6,6`}
                />
              ) : (
                <circle
                  key={`v${String(p.index)}`}
                  className="case-timeline__dot"
                  data-selected={p.index === selected}
                  cx={x(p.row.date)}
                  cy={y(p.value)}
                  r={p.index === selected ? DOT + 1.5 : DOT}
                />
              ),
            )}
          </svg>
        ) : null}
        {width > 0
          ? points.map((p) => (
              <button
                key={p.row.sceneId}
                id={`case-pass-${String(p.index)}`}
                type="button"
                role="option"
                aria-selected={p.index === selected}
                tabIndex={-1}
                className="case-timeline__hit"
                style={{
                  left: `${String(x(p.row.date) - 9)}px`,
                  top: `${String((p.value === null ? baseY : y(p.value)) - 9)}px`,
                }}
                onClick={() => {
                  onSelect(p.index);
                }}
              >
                <span className="case-visually-hidden">
                  {formatDate(p.row.date, true)}:{" "}
                  {p.value === null ? CASE_COPY.timelineNoValue : `${formatValue(p.value)} FNU`}
                </span>
              </button>
            ))
          : null}
      </div>
    </section>
  );
}
