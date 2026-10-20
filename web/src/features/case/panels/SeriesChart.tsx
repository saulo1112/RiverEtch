import { useState, type KeyboardEvent } from "react";

import { FNU_CLASSES, gaugeAt, isOutside, isUngauged, turbidity } from "../../reaches/scene.ts";
import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY, daysBetween, formatDate, formatValue } from "../content.ts";
import { useSize } from "./useSize.ts";

/** Props of {@link SeriesChart}. */
export interface SeriesChartProps {
  readonly reach: ReachData;
  /** Index of the selected pass in the series. */
  readonly selected: number;
  /** The pass compared with it (compare mode). */
  readonly compared: number | null;
  /** Selects a pass. */
  readonly onSelect: (index: number) => void;
}

// Chart geometry (CSS px): room for the value axis on the left and the month axis below.
const PAD = { left: 34, right: 10, top: 20, bottom: 22 };
const DOT = 4.5;
const TICKS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];

/**
 * The year's passes: turbidity values on a log scale, or, on a reach with no gauge, its classes.
 *
 * @param props - The reach, the selection and its handler.
 * @returns The chart.
 */
export function SeriesChart(props: SeriesChartProps) {
  return isUngauged(props.reach) ? <ClassChart {...props} /> : <ValueChart {...props} />;
}

// The months from the first pass's January to the last pass, and the x scale over them.
function timeAxis(reach: ReachData, width: number) {
  const first = reach.series[0]?.date ?? "2026-01-01";
  const start = `${first.slice(0, 4)}-01-01`;
  const end = reach.series.at(-1)?.date ?? first;
  const span = Math.max(30, daysBetween(start, end) + 6);
  const plotWidth = Math.max(1, width - PAD.left - PAD.right);
  const months: string[] = [];
  const cursor = new Date(`${start}T00:00:00Z`);
  while (daysBetween(cursor.toISOString().slice(0, 10), end) >= 0) {
    months.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  return {
    months,
    x: (date: string) => PAD.left + (daysBetween(start, date) / span) * plotWidth,
  };
}

/**
 * An ungauged reach's passes by class (preregistration-transfer.md, section 5): three bands,
 * under 30, 30 to 100 and 100 FNU and over, with each pass a dot in its band. Height means only
 * the class, never a value; a pass without a class is a mark on the axis.
 *
 * @returns The chart.
 */
function ClassChart({ reach, selected, compared, onSelect }: SeriesChartProps) {
  const [plotRef, { width, height }] = useSize<HTMLDivElement>();
  const [hovered, setHovered] = useState<number | null>(null);
  const { ungauged } = CASE_COPY;
  const { series } = reach;
  const points = series.map((row, index) => {
    const estimate = turbidity(row);
    return { index, row, cls: estimate?.fnuClass ?? null, reason: estimate?.abstainReason ?? null };
  });
  const { months, x } = timeAxis(reach, width);
  const plotHeight = Math.max(1, height - PAD.top - PAD.bottom);
  const band = plotHeight / FNU_CLASSES.length;
  const baseY = PAD.top + plotHeight;
  // A dot sits in the middle of its class's band; the lowest class is at the bottom.
  const at = (p: (typeof points)[number]) =>
    p.cls === null ? baseY : baseY - (FNU_CLASSES.indexOf(p.cls) + 0.5) * band;
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step !== 0) {
      event.preventDefault();
      onSelect(Math.min(series.length - 1, Math.max(0, selected + step)));
    }
  };
  const current = points[selected];
  const other = compared === null ? undefined : points[compared];
  const tip = hovered === null ? undefined : points[hovered];
  return (
    <div
      className="case-series"
      ref={plotRef}
      role="listbox"
      tabIndex={0}
      aria-label={CASE_COPY.timelineHint}
      aria-activedescendant={current === undefined ? undefined : `case-pass-${String(selected)}`}
      onKeyDown={onKey}
    >
      {width > 0 && height > 0 ? (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${String(width)} ${String(height)}`}
          aria-hidden="true"
        >
          {[30, 100].map((edge, k) => (
            <g key={edge}>
              <line
                className="case-series__grid"
                x1={PAD.left}
                x2={width - PAD.right}
                y1={baseY - (k + 1) * band}
                y2={baseY - (k + 1) * band}
              />
              <text
                className="case-series__tick"
                x={PAD.left - 6}
                y={baseY - (k + 1) * band + 3.5}
                textAnchor="end"
              >
                {edge}
              </text>
            </g>
          ))}
          <text className="case-series__unit" x={4} y={9}>
            FNU
          </text>
          {months.map((m) => (
            <text
              key={m}
              className="case-series__tick"
              x={x(m) + 2}
              y={height - 6}
              textAnchor="start"
            >
              {formatDate(m).split(" ")[1]}
            </text>
          ))}
          {other === undefined ? null : (
            <line
              className="case-series__compare"
              x1={x(other.row.date)}
              x2={x(other.row.date)}
              y1={PAD.top}
              y2={baseY}
            />
          )}
          {current === undefined ? null : (
            <line
              className="case-series__cursor"
              x1={x(current.row.date)}
              x2={x(current.row.date)}
              y1={PAD.top}
              y2={baseY}
            />
          )}
          {points.map((p) =>
            p.cls === null ? (
              <path
                key={`n${String(p.index)}`}
                className="case-series__none"
                d={`M${String(x(p.row.date) - 3)},${String(baseY - 3)}l6,6m0,-6l-6,6`}
              />
            ) : (
              <circle
                key={`v${String(p.index)}`}
                className="case-series__dot"
                data-selected={p.index === selected}
                data-compared={p.index === compared}
                cx={x(p.row.date)}
                cy={at(p)}
                r={p.index === selected || p.index === hovered ? DOT + 1.5 : DOT}
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
              className="case-series__hit"
              style={{ left: `${String(x(p.row.date) - 9)}px`, top: `${String(at(p) - 9)}px` }}
              onClick={() => {
                onSelect(p.index);
              }}
              onPointerEnter={() => {
                setHovered(p.index);
              }}
              onPointerLeave={() => {
                setHovered(null);
              }}
            >
              <span className="case-visually-hidden">
                {formatDate(p.row.date, true)}:{" "}
                {p.cls === null ? ungauged.noClass : ungauged.classes[p.cls]}
              </span>
            </button>
          ))
        : null}
      {tip === undefined ? null : (
        <div
          className="case-series__tip case-glass"
          data-side={x(tip.row.date) > width - 220 ? "left" : "right"}
          style={{ left: `${String(x(tip.row.date))}px`, top: `${String(at(tip))}px` }}
        >
          <p className="case-series__tip-date">{formatDate(tip.row.date, true)}</p>
          {tip.cls === null ? (
            <p className="case-series__tip-none">{tip.reason ?? ungauged.noClass}</p>
          ) : (
            <p className="case-series__tip-value">{ungauged.classes[tip.cls]}</p>
          )}
          <p className="case-series__tip-gauge">
            {isOutside(reach) ? ungauged.outsideLabel : ungauged.label}
          </p>
        </div>
      )}
    </div>
  );
}

// The year's passes as a turbidity chart on a log scale. Each pass with a value is a dot with its
// 90 % interval; the USGS gauge's own reading at the overpass sits beside it as a ring; a pass
// without a value is a small mark on the axis. Hovering a pass shows its numbers; clicking it, or
// the arrow keys, selects it.
function ValueChart({ reach, selected, compared, onSelect }: SeriesChartProps) {
  const [plotRef, { width, height }] = useSize<HTMLDivElement>();
  const [hovered, setHovered] = useState<number | null>(null);
  const { series } = reach;
  const points = series.map((row, index) => {
    const estimate = turbidity(row);
    const value = typeof estimate?.value === "number" ? estimate.value : null;
    const gauge = gaugeAt(reach, row);
    return {
      index,
      row,
      value,
      level: estimate?.level ?? "none",
      reason: estimate?.abstainReason ?? null,
      low: estimate?.interval?.low ?? null,
      high: estimate?.interval?.high ?? null,
      gauge: gauge?.value ?? null,
      approval: gauge?.approval ?? "",
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
  const other = compared === null ? undefined : points[compared];
  const tip = hovered === null ? undefined : points[hovered];
  return (
    <div
      className="case-series"
      ref={plotRef}
      role="listbox"
      tabIndex={0}
      aria-label={CASE_COPY.timelineHint}
      aria-activedescendant={current === undefined ? undefined : `case-pass-${String(selected)}`}
      onKeyDown={onKey}
    >
      {width > 0 && height > 0 ? (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${String(width)} ${String(height)}`}
          aria-hidden="true"
        >
          {yTicks.map((t) => (
            <g key={t}>
              <line
                className="case-series__grid"
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(t)}
                y2={y(t)}
              />
              <text className="case-series__tick" x={PAD.left - 6} y={y(t) + 3.5} textAnchor="end">
                {t}
              </text>
            </g>
          ))}
          <text className="case-series__unit" x={4} y={9}>
            FNU
          </text>
          {months.map((m) => (
            <text
              key={m}
              className="case-series__tick"
              x={x(m) + 2}
              y={height - 6}
              textAnchor="start"
            >
              {formatDate(m).split(" ")[1]}
            </text>
          ))}
          {other === undefined ? null : (
            <line
              className="case-series__compare"
              x1={x(other.row.date)}
              x2={x(other.row.date)}
              y1={PAD.top}
              y2={baseY}
            />
          )}
          {current === undefined ? null : (
            <line
              className="case-series__cursor"
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
                className="case-series__interval"
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
                className="case-series__gauge"
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
                className="case-series__none"
                d={`M${String(x(p.row.date) - 3)},${String(baseY - 3)}l6,6m0,-6l-6,6`}
              />
            ) : (
              <circle
                key={`v${String(p.index)}`}
                className="case-series__dot"
                data-selected={p.index === selected}
                data-compared={p.index === compared}
                cx={x(p.row.date)}
                cy={y(p.value)}
                r={p.index === selected || p.index === hovered ? DOT + 1.5 : DOT}
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
              className="case-series__hit"
              style={{
                left: `${String(x(p.row.date) - 9)}px`,
                top: `${String((p.value === null ? baseY : y(p.value)) - 9)}px`,
              }}
              onClick={() => {
                onSelect(p.index);
              }}
              onPointerEnter={() => {
                setHovered(p.index);
              }}
              onPointerLeave={() => {
                setHovered(null);
              }}
            >
              <span className="case-visually-hidden">
                {formatDate(p.row.date, true)}:{" "}
                {p.value === null ? CASE_COPY.timelineNoValue : `${formatValue(p.value)} FNU`}
              </span>
            </button>
          ))
        : null}
      {tip === undefined ? null : (
        <div
          className="case-series__tip case-glass"
          data-side={x(tip.row.date) > width - 220 ? "left" : "right"}
          style={{
            left: `${String(x(tip.row.date))}px`,
            top: `${String(tip.value === null ? baseY : y(tip.value))}px`,
          }}
        >
          <p className="case-series__tip-date">{formatDate(tip.row.date, true)}</p>
          {tip.value === null ? (
            <p className="case-series__tip-none">{tip.reason ?? CASE_COPY.rangeWithoutLevel}</p>
          ) : (
            <p className="case-series__tip-value">
              {formatValue(tip.value)} FNU
              {tip.low === null || tip.high === null ? null : (
                <span>
                  {" "}
                  [{formatValue(tip.low)}–{formatValue(tip.high)}]
                </span>
              )}
            </p>
          )}
          {tip.gauge === null ? null : (
            <p className="case-series__tip-gauge">
              USGS {formatValue(tip.gauge)} FNU ({tip.approval.toLowerCase()})
              {tip.value === null
                ? ""
                : ` · ${tip.value >= tip.gauge ? "+" : "−"}${Math.abs((tip.value / tip.gauge - 1) * 100).toFixed(0)} %`}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
