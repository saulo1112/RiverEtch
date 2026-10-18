import { useState, type PointerEvent } from "react";

import {
  climateMeasures,
  climatePoints,
  ordinal,
  recordYear,
  type ClimateMeasure,
  type ClimatePoint,
} from "../../reaches/climate.ts";
import type { ClimateRecord } from "../../reaches/types.ts";
import { CASE_COPY, formatCelsius, formatDate, formatReading } from "../content.ts";
import { useSize } from "./useSize.ts";

/** Props of {@link ClimateView}. */
export interface ClimateViewProps {
  readonly climate: ClimateRecord;
}

// Chart geometry (CSS px), as the other charts'.
const PAD = { left: 40, right: 8, top: 18, bottom: 20 };
const GAP = 2; // surface gap between bars
const DOT = 3.5;

function unitOf(climate: ClimateRecord, measure: ClimateMeasure): string {
  return measure === "warm" ? (climate.temperature?.unit ?? "°C") : climate.discharge.unit;
}

function formatMeasure(measure: ClimateMeasure, value: number): string {
  return measure === "warm" ? formatCelsius(value) : formatReading(value);
}

// Round steps of 1, 2 or 5 × 10^k: at most `count` ticks from `low` to `high`.
function ticksOf(low: number, high: number, count: number): number[] {
  const raw = (high - low) / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(raw || 1));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let t = Math.ceil(low / step) * step; t <= high + 1e-9; t += step) {
    out.push(Number(t.toFixed(6)));
  }
  return out;
}

// The default measure: the one whose record year is the most recent (the peak on a tie).
function defaultMeasure(climate: ClimateRecord): ClimateMeasure {
  let best: ClimateMeasure = "peak";
  let year = -Infinity;
  for (const m of climateMeasures(climate)) {
    const found = recordYear(climatePoints(climate, m))?.year ?? -Infinity;
    if (found > year) {
      best = m;
      year = found;
    }
  }
  return best;
}

function Chart({
  measure,
  points,
  unit,
  label,
}: {
  readonly measure: ClimateMeasure;
  readonly points: readonly ClimatePoint[];
  readonly unit: string;
  readonly label: string;
}) {
  const [plotRef, { width, height }] = useSize<HTMLDivElement>();
  const [hovered, setHovered] = useState<number | null>(null);
  const values = points.flatMap((p) => (p.value === null ? [] : [p.value]));
  if (values.length === 0) {
    return null;
  }
  const dots = measure === "warm";
  const lowest = dots ? Math.floor(Math.min(...values) - 1) : 0;
  const highest = Math.max(...values, lowest + 1);
  const ticks = ticksOf(lowest, highest, 3);
  const top = Math.max(highest, ticks.at(-1) ?? highest);
  const plotWidth = Math.max(1, width - PAD.left - PAD.right);
  const plotHeight = Math.max(1, height - PAD.top - PAD.bottom);
  const band = plotWidth / Math.max(1, points.length);
  const x = (k: number) => PAD.left + k * band;
  const y = (v: number) => PAD.top + (1 - (v - lowest) / (top - lowest || 1)) * plotHeight;
  const baseY = PAD.top + plotHeight;
  const every = [1, 2, 5, 10, 20].find((s) => s * band >= 34) ?? 20;

  const onMove = (event: PointerEvent<HTMLDivElement>) => {
    const left = event.currentTarget.getBoundingClientRect().left;
    const k = Math.floor((event.clientX - left - PAD.left) / band);
    setHovered(k >= 0 && k < points.length ? k : null);
  };
  const tip = hovered === null ? undefined : points[hovered];
  const tipX = hovered === null ? 0 : x(hovered) + band / 2;
  const tipY = tip?.value == null ? baseY : y(tip.value);
  const record = recordYear(points);
  const recordAt = record === null ? -1 : points.indexOf(record);

  return (
    <div
      className="case-series case-climate__chart"
      ref={plotRef}
      role="img"
      aria-label={label}
      onPointerMove={onMove}
      onPointerLeave={() => {
        setHovered(null);
      }}
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
                {t.toLocaleString("en-US", { maximumFractionDigits: 1 })}
              </text>
            </g>
          ))}
          <text className="case-series__unit" x={4} y={9}>
            {unit}
          </text>
          {points.map((p, k) =>
            p.year % every === 0 ? (
              <text
                key={`y${String(p.year)}`}
                className="case-series__tick"
                x={x(k) + band / 2}
                y={height - 5}
                textAnchor="middle"
              >
                {p.year}
              </text>
            ) : null,
          )}
          {points.map((p, k) => {
            if (p.value === null) {
              return null;
            }
            const tone =
              p.rank !== null && p.rank <= 3 ? "top" : p.toDate ? "now" : p.complete ? "" : "gap";
            const active = k === hovered ? "true" : undefined;
            if (dots) {
              return (
                <circle
                  key={p.year}
                  className="case-climate__dot"
                  data-tone={tone}
                  data-active={active}
                  cx={x(k) + band / 2}
                  cy={y(p.value)}
                  r={k === hovered ? DOT + 1.5 : DOT}
                />
              );
            }
            const barWidth = Math.max(1, band - GAP);
            const barTop = Math.min(y(p.value), baseY - 1);
            return (
              <rect
                key={p.year}
                className="case-climate__bar"
                data-tone={tone}
                data-active={active}
                x={x(k) + (band - barWidth) / 2}
                y={barTop}
                width={barWidth}
                height={baseY - barTop}
                rx={Math.min(2, barWidth / 2)}
              />
            );
          })}
          {record?.value == null ? null : (
            <text
              className="case-climate__label"
              x={Math.min(width - PAD.right - 14, Math.max(PAD.left + 14, x(recordAt) + band / 2))}
              y={y(record.value) - 6}
              textAnchor="middle"
            >
              {record.year}
            </text>
          )}
        </svg>
      ) : null}
      {tip?.value == null ? null : (
        <div
          className="case-series__tip case-glass"
          data-side={tipX > width - 220 ? "left" : "right"}
          style={{ left: `${String(tipX)}px`, top: `${String(Math.max(PAD.top + 24, tipY))}px` }}
        >
          <p className="case-series__tip-value">
            {tip.year} · {formatMeasure(measure, tip.value)} {unit}
          </p>
          {tip.day === null ? null : (
            <p className="case-series__tip-date">
              {measure === "low" ? `${CASE_COPY.climate.weekTo} ` : ""}
              {formatDate(tip.day, true)}
            </p>
          )}
          <p className="case-series__tip-gauge">
            {tip.rank !== null
              ? `${ordinal(tip.rank)} of ${String(tip.ranked)}`
              : tip.toDate
                ? CASE_COPY.climate.toDate
                : CASE_COPY.climate.incomplete}
            {tip.provisional ? ` · ${CASE_COPY.climate.provisional}` : ""}
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * The climate context of a reach: the gauge's own daily record, year by year (`climate.json`).
 * Each measure's record year sits on the left and selects the measure; the chart shows every year
 * of it, the three most extreme of the ranked years in the gauge's colour and the record labelled.
 * A hidden table gives every year to screen readers.
 *
 * @param props - The view's props.
 * @param props.climate - The reach's climate context.
 * @returns The view.
 */
export function ClimateView({ climate }: ClimateViewProps) {
  const copy = CASE_COPY.climate;
  const [measure, setMeasure] = useState<ClimateMeasure>(() => defaultMeasure(climate));
  const measures = climateMeasures(climate);
  const byYear = {
    peak: new Map(climatePoints(climate, "peak").map((p) => [p.year, p])),
    low: new Map(climatePoints(climate, "low").map((p) => [p.year, p])),
    warm: new Map(climatePoints(climate, "warm").map((p) => [p.year, p])),
  };
  const points = climatePoints(climate, measure);
  const unit = unitOf(climate, measure);
  const station = climate.station.id.replace(/^USGS-/, "USGS ");
  return (
    <div className="case-climate">
      <div className="case-climate__facts" role="radiogroup" aria-label={copy.note}>
        {measures.map((m) => {
          const found = recordYear(climatePoints(climate, m));
          const ranked = found?.ranked ?? 0;
          return (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={m === measure}
              className="case-climate__fact"
              onClick={() => {
                setMeasure(m);
              }}
            >
              <span className="case-climate__fact-what">
                {copy.facts[m]} {copy.span(ranked, m === "warm" ? "summers" : "years")}
              </span>
              {found?.value == null ? null : (
                <span className="case-climate__fact-value">
                  <strong>{found.year}</strong> · {formatMeasure(m, found.value)}{" "}
                  {unitOf(climate, m)}
                  {found.day === null ? null : (
                    <span>
                      {" "}
                      · {m === "low" ? `${copy.weekTo} ` : ""}
                      {formatDate(found.day)}
                    </span>
                  )}
                </span>
              )}
            </button>
          );
        })}
        <p className="case-climate__since">
          {copy.since(climate.discharge.first.slice(0, 4), station)}
        </p>
      </div>
      <Chart
        measure={measure}
        points={points}
        unit={unit}
        label={copy.chart(copy.measures[measure], station)}
      />
      <table className="case-visually-hidden">
        <caption>{copy.table}</caption>
        <thead>
          <tr>
            <th scope="col">Year</th>
            {measures.map((m) => (
              <th key={m} scope="col">
                {copy.measures[m]} ({unitOf(climate, m)})
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {climatePoints(climate, "peak").map((p) => (
            <tr key={p.year}>
              <th scope="row">{p.year}</th>
              {measures.map((m) => {
                const row = byYear[m].get(p.year);
                return (
                  <td key={m}>
                    {row?.value == null ? "" : formatMeasure(m, row.value)}
                    {row?.rank == null ? "" : ` (${ordinal(row.rank)})`}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
