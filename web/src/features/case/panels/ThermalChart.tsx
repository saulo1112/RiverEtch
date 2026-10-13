import { useState, type KeyboardEvent } from "react";

import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY, daysBetween, formatCelsius, formatDate, landsatName } from "../content.ts";
import { useSize } from "./useSize.ts";

/** Props of {@link ThermalChart}. */
export interface ThermalChartProps {
  readonly reach: ReachData;
  /** Index of the selected Landsat pass (null: none). */
  readonly selected: number | null;
  /** Date of the selected Sentinel-2 pass, drawn as the cursor (null: none). */
  readonly cursor: string | null;
  /** Selects a Landsat pass. */
  readonly onSelect: (index: number) => void;
}

// Chart geometry (CSS px), as the turbidity chart's.
const PAD = { left: 34, right: 10, top: 20, bottom: 22 };
const DOT = 4.5;

function signed(value: number): string {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1)}`;
}

/**
 * The year's water temperature from Landsat 8 and 9 (preregistration v6), on a linear scale in
 * °C. Each pass is a dot with its 90 % interval; the USGS gauge's own reading at the overpass sits
 * beside it as a ring; the selected Sentinel-2 pass is the dashed cursor. Hovering a pass shows its
 * numbers; clicking it, or the arrow keys, selects it and shows its record.
 *
 * @returns The chart.
 */
export function ThermalChart({ reach, selected, cursor, onSelect }: ThermalChartProps) {
  const [plotRef, { width, height }] = useSize<HTMLDivElement>();
  const [hovered, setHovered] = useState<number | null>(null);
  const series = reach.thermal?.series ?? [];
  const checks = reach.thermal?.checks ?? [];
  const points = series.map((row, index) => {
    const check = checks.find((c) => c.sceneId === row.sceneId);
    return {
      index,
      row,
      value: typeof row.estimate.value === "number" ? row.estimate.value : null,
      low: row.estimate.interval?.low ?? null,
      high: row.estimate.interval?.high ?? null,
      gauge: check?.value ?? null,
      approval: check?.approval ?? "",
    };
  });

  const values = points.flatMap((p) =>
    [p.value, p.low, p.high, p.gauge].filter((v): v is number => v !== null),
  );
  const yMin = Math.floor(Math.min(0, ...values) / 5) * 5;
  const yMax = Math.ceil(Math.max(30, ...values) / 5) * 5;
  const first = series[0]?.date ?? "2026-01-01";
  const start = `${first.slice(0, 4)}-01-01`;
  const last = series.at(-1)?.date ?? first;
  const end = cursor !== null && cursor > last ? cursor : last;
  const span = Math.max(30, daysBetween(start, end) + 6);
  const plotWidth = Math.max(1, width - PAD.left - PAD.right);
  const plotHeight = Math.max(1, height - PAD.top - PAD.bottom);
  const x = (date: string) => PAD.left + (daysBetween(start, date) / span) * plotWidth;
  const y = (v: number) => PAD.top + (1 - (v - yMin) / (yMax - yMin || 1)) * plotHeight;
  const baseY = PAD.top + plotHeight;

  const ticks: number[] = [];
  for (let t = Math.ceil(yMin / 10) * 10; t <= yMax; t += 10) {
    ticks.push(t);
  }
  const months: string[] = [];
  const month = new Date(`${start}T00:00:00Z`);
  while (daysBetween(month.toISOString().slice(0, 10), end) >= 0) {
    months.push(month.toISOString().slice(0, 10));
    month.setUTCMonth(month.getUTCMonth() + 1);
  }

  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step !== 0 && points.length > 0) {
      event.preventDefault();
      onSelect(Math.min(points.length - 1, Math.max(0, (selected ?? points.length - 1) + step)));
    }
  };

  const tip = hovered === null ? undefined : points[hovered];
  return (
    <div
      className="case-series"
      ref={plotRef}
      role="listbox"
      tabIndex={0}
      aria-label={CASE_COPY.thermal.hint}
      aria-activedescendant={selected === null ? undefined : `case-thermal-${String(selected)}`}
      onKeyDown={onKey}
    >
      {width > 0 && height > 0 ? (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${String(width)} ${String(height)}`}
          aria-hidden="true"
        >
          {ticks.map((t) => (
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
            °C
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
          {cursor === null ? null : (
            <line
              className="case-series__cursor"
              x1={x(cursor)}
              x2={x(cursor)}
              y1={PAD.top}
              y2={baseY}
            />
          )}
          {points.map((p) =>
            p.low === null || p.high === null ? null : (
              <line
                key={`i${String(p.index)}`}
                className="case-series__interval case-series__interval--thermal"
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
            p.value === null ? null : (
              <circle
                key={`v${String(p.index)}`}
                className="case-series__dot case-series__dot--thermal"
                data-selected={p.index === selected}
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
              id={`case-thermal-${String(p.index)}`}
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
                {p.value === null ? CASE_COPY.timelineNoValue : `${formatCelsius(p.value)} °C`}
              </span>
            </button>
          ))
        : null}
      {tip?.value == null ? null : (
        <div
          className="case-series__tip case-glass"
          data-side={x(tip.row.date) > width - 220 ? "left" : "right"}
          style={{ left: `${String(x(tip.row.date))}px`, top: `${String(y(tip.value))}px` }}
        >
          <p className="case-series__tip-date">
            {formatDate(tip.row.date, true)} · {landsatName(tip.row.platform)}
          </p>
          <p className="case-series__tip-value">
            {formatCelsius(tip.value)} °C
            {tip.low === null || tip.high === null ? null : (
              <span>
                {" "}
                [{formatCelsius(tip.low)} to {formatCelsius(tip.high)}]
              </span>
            )}
          </p>
          {tip.gauge === null ? null : (
            <p className="case-series__tip-gauge">
              USGS {formatCelsius(tip.gauge)} °C ({tip.approval.toLowerCase()}) ·{" "}
              {signed(tip.value - tip.gauge)} °C
            </p>
          )}
          <p className="case-series__tip-date">
            {String(tip.row.waterPixels)} {CASE_COPY.thermal.pixels}
          </p>
        </div>
      )}
    </div>
  );
}
