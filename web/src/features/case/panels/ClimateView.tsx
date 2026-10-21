import { useState, type PointerEvent } from "react";

import {
  climateMeasures,
  climatePoints,
  extremeKinds,
  extremePoints,
  ordinal,
  recordYear,
  type ClimateMeasure,
  type ClimatePoint,
  type ExtremeKind,
} from "../../reaches/climate.ts";
import type { ClimateRecord } from "../../reaches/types.ts";
import { CASE_COPY, formatCelsius, formatDate, formatReading } from "../content.ts";
import { HelpTip } from "./HelpTip.tsx";
import { useSize } from "./useSize.ts";

/** What the climate tab shows: each year's extreme values, or its count of extreme days. */
export type ClimateTabView = "values" | "days";

/** Props of {@link ClimateView}. */
export interface ClimateViewProps {
  readonly climate: ClimateRecord;
  /** Extreme days where the record has them (default: the yearly values). */
  readonly view?: ClimateTabView;
}

// A chart draws one measure's values, or one kind's count of extreme days.
type ChartMeasure = ClimateMeasure | "days";

// Chart geometry (CSS px), as the other charts'.
const PAD = { left: 40, right: 8, top: 18, bottom: 20 };
const GAP = 2; // surface gap between bars
const DOT = 3.5;

function unitOf(climate: ClimateRecord, measure: ClimateMeasure): string {
  return measure === "warm" ? (climate.temperature?.unit ?? "°C") : climate.discharge.unit;
}

function formatMeasure(measure: ChartMeasure, value: number): string {
  if (measure === "days") {
    return String(value);
  }
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
  note,
}: {
  readonly measure: ChartMeasure;
  readonly points: readonly ClimatePoint[];
  readonly unit: string;
  readonly label: string;
  /** A year's extra line in the tip (extreme days: what the satellite saw). */
  readonly note?: (point: ClimatePoint) => string | null;
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
  const tipNote = tip === undefined || note === undefined ? null : note(tip);
  const tipX = hovered === null ? 0 : x(hovered) + band / 2;
  const tipY = tip?.value == null ? baseY : y(tip.value);
  const record = recordYear(points);
  const recordAt = record === null ? -1 : points.indexOf(record);
  const nowAt = points.findIndex((p) => p.toDate);
  const now = nowAt < 0 ? undefined : points[nowAt];

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
          {/* This year: still running, so not ranked; said over its bar. */}
          {now?.value == null ? null : (
            <text
              className="case-climate__label case-climate__label--now"
              x={Math.min(width - PAD.right - 14, Math.max(PAD.left + 14, x(nowAt) + band / 2))}
              y={y(now.value) - 6}
              textAnchor="middle"
            >
              {CASE_COPY.climate.soFar}
            </text>
          )}
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
          {tipNote === null ? null : <p className="case-series__tip-date">{tipNote}</p>}
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

// The station as the tab names it: its USGS number, and its place when it is a station on the
// same river standing in for a reach with none of its own; a flood model's cell by its name.
function stationLabel(climate: ClimateRecord): string {
  if (climate.station.modelled === true) {
    return climate.station.name;
  }
  const id = climate.station.id.replace(/^USGS-/, "USGS ");
  return climate.station.context === true ? `${climate.station.name} (${id})` : id;
}

/**
 * The climate context of a reach: the gauge's own daily record, year by year (`climate.json`).
 * Each measure's record year sits on the left and selects the measure; the chart shows every year
 * of it, the three most extreme of the ranked years in the gauge's colour and the record labelled.
 * A hidden table gives every year to screen readers. With `view` "days", the record's extreme days
 * instead (see `ExtremeDays`).
 *
 * @param props - The view's props.
 * @param props.climate - The reach's climate context.
 * @param props.view - The yearly values, or the extreme days.
 * @returns The view.
 */
export function ClimateView({ climate, view = "values" }: ClimateViewProps) {
  const copy = CASE_COPY.climate;
  const [measure, setMeasure] = useState<ClimateMeasure>(() => defaultMeasure(climate));
  if (view === "days" && climate.extremes !== undefined) {
    return <ExtremeDays climate={climate} />;
  }
  const measures = climateMeasures(climate);
  const byYear = {
    peak: new Map(climatePoints(climate, "peak").map((p) => [p.year, p])),
    low: new Map(climatePoints(climate, "low").map((p) => [p.year, p])),
    warm: new Map(climatePoints(climate, "warm").map((p) => [p.year, p])),
  };
  const points = climatePoints(climate, measure);
  const unit = unitOf(climate, measure);
  const station = stationLabel(climate);
  const modelled = climate.station.modelled === true;
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
        {climate.discharge.lowsNote === undefined ? null : (
          <p className="case-climate__lows">{climate.discharge.lowsNote}</p>
        )}
      </div>
      <Chart
        measure={measure}
        points={points}
        unit={unit}
        label={(modelled ? copy.chartModel : copy.chart)(copy.measures[measure], station)}
      />
      <table className="case-visually-hidden">
        <caption>{modelled ? copy.tableModel : copy.table}</caption>
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

// A count with a thousands separator ("1,655").
const count = (n: number) => n.toLocaleString("en-US");

// The kind whose record year is the most recent (low flow on a tie).
function defaultKind(climate: ClimateRecord): ExtremeKind {
  let best: ExtremeKind = "low";
  let year = -Infinity;
  for (const k of extremeKinds(climate)) {
    const found = recordYear(extremePoints(climate, k))?.year ?? -Infinity;
    if (found > year) {
      best = k;
      year = found;
    }
  }
  return best;
}

/**
 * The extreme days of the gauge's record (rule v1): each kind's count per year and its record
 * year, ranked like the climate context; how often a usable pass saw such days; and whether the
 * locked test holds enough of them to say how the error changes (it never says it with fewer
 * than the minimum).
 *
 * @param props - The view's props.
 * @param props.climate - The reach's climate context, with its extremes block.
 * @returns The view.
 */
function ExtremeDays({ climate }: { readonly climate: ClimateRecord }) {
  const copy = CASE_COPY.climate;
  const [kind, setKind] = useState<ExtremeKind>(() => defaultKind(climate));
  const e = climate.extremes;
  if (e === undefined) {
    return null;
  }
  const kinds = extremeKinds(climate);
  const points = extremePoints(climate, kind);
  const station = stationLabel(climate);
  const era = e.satelliteEra;
  const seen = era[kind];
  const pairs = e.lockbox[kind];
  const words = copy.kindWords[kind];
  const t = e.thresholds;
  const threshold = kind === "warm" ? t.warm : t[kind];
  const definition = copy.definition[kind](
    threshold === null ? "–" : formatReading(threshold),
    kind === "warm" ? t.warmUnit : t.flowUnit,
    kind === "warm" ? String(t.reference.warmFirstYear) : t.reference.first.slice(0, 4),
  );
  const byYear = new Map(e.years.map((y) => [y.year, y]));
  const note = (p: ClimatePoint) => {
    const k = byYear.get(p.year)?.[`${kind}Seen`];
    return k === null || k === undefined || p.value === null ? null : copy.seenYear(k, p.value);
  };
  return (
    <div className="case-climate">
      <div className="case-climate__facts" role="radiogroup" aria-label={copy.views.days}>
        {kinds.map((k) => {
          const found = recordYear(extremePoints(climate, k));
          return (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={k === kind}
              className="case-climate__fact"
              onClick={() => {
                setKind(k);
              }}
            >
              <span className="case-climate__fact-what">
                {copy.mostIn(
                  copy.kindWords[k],
                  found?.ranked ?? 0,
                  k === "warm" ? "summers" : "years",
                )}
              </span>
              <span className="case-climate__fact-value">
                {copy.kinds[k]}
                {found?.value == null ? null : (
                  <span>
                    {" "}
                    · <strong>{found.year}</strong> · {copy.days(found.value)}
                  </span>
                )}
              </span>
            </button>
          );
        })}
      </div>
      <div className="case-climate__days">
        <Chart
          measure="days"
          points={points}
          unit={copy.dayUnit}
          label={copy.chart(copy.kinds[kind], station)}
          note={note}
        />
        <p className="case-climate__extreme-note">
          {seen === null ? null : (
            <>
              {copy.seen(era.first, era.last, count(seen.seen), count(seen.days), words)}
              {kind === "warm"
                ? ""
                : copy.seenOthers(count(era.normal.seen), count(era.normal.days))}
              .{" "}
            </>
          )}
          {pairs === null
            ? null
            : pairs < e.lockbox.minimum
              ? copy.notEnough(pairs, e.lockbox.pairs, e.lockbox.minimum)
              : copy.enough(pairs, e.lockbox.pairs)}
          <HelpTip label={copy.definitionLabel}>
            {definition} {copy.definitionNote}
          </HelpTip>
        </p>
      </div>
      <table className="case-visually-hidden">
        <caption>{copy.tableDays}</caption>
        <thead>
          <tr>
            <th scope="col">Year</th>
            {kinds.map((k) => (
              <th key={k} scope="col">
                {copy.kinds[k]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {e.years.map((y) => (
            <tr key={y.year}>
              <th scope="row">{y.year}</th>
              {kinds.map((k) => {
                const n = y[k];
                const rank = y[`${k}Rank`];
                const saw = y[`${k}Seen`];
                return (
                  <td key={k}>
                    {n === null ? "" : String(n)}
                    {rank === null ? "" : ` (${ordinal(rank)})`}
                    {n === null || saw === null ? "" : `, ${copy.seenYear(saw, n)}`}
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
