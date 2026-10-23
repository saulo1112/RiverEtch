import { useEffect, useState, type PointerEvent } from "react";

import { reachYear } from "../../reaches/archive.ts";
import {
  bandPosition,
  calendarIndex,
  flowDays,
  type BandPosition,
  type FlowDay,
} from "../../reaches/dailyrecord.ts";
import { loadText } from "../../reaches/data.ts";
import type {
  ClimateRecord,
  DailyRecord,
  DailyRecordRow,
  ReachData,
  UsualFlow,
} from "../../reaches/types.ts";
import { CASE_COPY, formatDate, formatReading } from "../content.ts";
import { DailyRecordCheck } from "./DailyRecordCheck.tsx";
import { HelpTip } from "./HelpTip.tsx";
import { useSize } from "./useSize.ts";

/** Props of {@link FlowYear}. */
export interface FlowYearProps {
  /** The reach as the case shows it (its year: sealed, or an earlier one). */
  readonly reach: ReachData;
  readonly climate: ClimateRecord;
}

// Chart geometry (CSS px), as the other charts'.
const PAD = { left: 48, right: 10, top: 14, bottom: 20 };
const PASS = 4; // a satellite pass's dot radius
// Each month's first day in the calendar index (a leap year's: 29 February is 59).
const MONTH_STARTS = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366];

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

// The year's record, read once per file.
function useRecord(reach: ReachData, row: DailyRecordRow | undefined): DailyRecord | null {
  const [found, setFound] = useState<{ file: string; record: DailyRecord } | null>(null);
  useEffect(() => {
    if (row === undefined) {
      return undefined;
    }
    let live = true;
    loadText(reach.base, `daily-record/${row.file}`)
      .then((text) => {
        if (live) {
          setFound({ file: row.file, record: JSON.parse(text) as DailyRecord });
        }
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [reach.base, row]);
  return row !== undefined && found?.file === row.file ? found.record : null;
}

// One run of consecutive days as an SVG path (a gap in the record breaks the line).
function linePath(points: readonly (readonly [number, number, string])[]): string {
  let path = "";
  let previous: string | null = null;
  for (const [x, y, day] of points) {
    const next =
      previous === null
        ? null
        : new Date(Date.parse(`${previous}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10);
    path += `${next === day ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    previous = day;
  }
  return path;
}

function FlowChart({
  days,
  usual,
  passes,
  thresholds,
  label,
}: {
  readonly days: readonly FlowDay[];
  readonly usual: UsualFlow;
  /** The year's satellite passes, by day. */
  readonly passes: ReadonlySet<string>;
  /** Rule v1's low-flow and high-flow lines, m³/s (null: none). */
  readonly thresholds: { readonly low: number; readonly high: number } | null;
  readonly label: string;
}) {
  const copy = CASE_COPY.climate.flow;
  const [plotRef, { width, height }] = useSize<HTMLDivElement>();
  const [hovered, setHovered] = useState<number | null>(null);
  if (days.length === 0) {
    return null;
  }
  const highest = Math.max(
    ...days.map((d) => d.value),
    ...usual.p90.map((v) => v ?? 0),
    thresholds?.low ?? 0,
  );
  const ticks = ticksOf(0, highest, 3);
  const top = Math.max(highest, ticks.at(-1) ?? highest);
  const plotWidth = Math.max(1, width - PAD.left - PAD.right);
  const plotHeight = Math.max(1, height - PAD.top - PAD.bottom);
  const x = (k: number) => PAD.left + ((k + 0.5) / 366) * plotWidth;
  const y = (v: number) => PAD.top + (1 - v / (top || 1)) * plotHeight;
  const byIndex = new Map(days.map((d) => [calendarIndex(d.day), d]));
  // The usual range as one area, and its median as a line, over the calendar days that have them.
  const band: string[] = [];
  const back: string[] = [];
  const median: string[] = [];
  for (let k = 0; k < 366; k += 1) {
    const low = usual.p10[k];
    const high = usual.p90[k];
    const mid = usual.p50[k];
    if (low != null && high != null) {
      band.push(`${x(k).toFixed(1)},${y(high).toFixed(1)}`);
      back.unshift(`${x(k).toFixed(1)},${y(low).toFixed(1)}`);
    }
    if (mid != null) {
      median.push(`${median.length === 0 ? "M" : "L"}${x(k).toFixed(1)},${y(mid).toFixed(1)}`);
    }
  }
  const line = linePath(days.map((d) => [x(calendarIndex(d.day)), y(d.value), d.day] as const));
  const onMove = (event: PointerEvent<HTMLDivElement>) => {
    const left = event.currentTarget.getBoundingClientRect().left;
    const k = Math.round(((event.clientX - left - PAD.left) / plotWidth) * 366 - 0.5);
    let best: number | null = null;
    for (const index of byIndex.keys()) {
      if (best === null || Math.abs(index - k) < Math.abs(best - k)) {
        best = index;
      }
    }
    setHovered(best !== null && Math.abs(best - k) <= 6 ? best : null);
  };
  const tip = hovered === null ? undefined : byIndex.get(hovered);
  const position: BandPosition | null =
    tip === undefined ? null : bandPosition(tip.value, tip.day, usual);
  const tipX = hovered === null ? 0 : x(hovered);
  const reference = (value: number | undefined) =>
    value === undefined || value > top ? null : value;
  const low = reference(thresholds?.low);
  const high = reference(thresholds?.high);
  return (
    <div
      className="case-series case-climate__chart case-flow__chart"
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
            m³/s
          </text>
          {copy.months.map((month, m) => (
            <text
              key={month}
              className="case-series__tick"
              x={x(((MONTH_STARTS[m] ?? 0) + (MONTH_STARTS[m + 1] ?? 366)) / 2)}
              y={height - 5}
              textAnchor="middle"
            >
              {month}
            </text>
          ))}
          {band.length > 1 ? (
            <polygon className="case-flow__band" points={[...band, ...back].join(" ")} />
          ) : null}
          <path className="case-flow__median" d={median.join("")} />
          {(
            [
              [low, copy.lowLine, "low"],
              [high, copy.highLine, "high"],
            ] as const
          ).map(([value, name, kind]) => {
            if (value === null) {
              return null;
            }
            // Two lines close together: the low-flow line's label goes under it.
            const under = kind === "low" && high !== null && y(value) - y(high) < 12;
            return (
              <g key={kind}>
                <line
                  className="case-flow__threshold"
                  x1={PAD.left}
                  x2={width - PAD.right}
                  y1={y(value)}
                  y2={y(value)}
                />
                <text
                  className="case-flow__threshold-label"
                  x={width - PAD.right - 2}
                  y={under ? y(value) + 10 : y(value) - 3}
                  textAnchor="end"
                >
                  {name}
                </text>
              </g>
            );
          })}
          <path className="case-flow__line" d={line} />
          {days.map((d) =>
            passes.has(d.day) ? (
              <circle
                key={d.day}
                className="case-flow__pass"
                data-active={calendarIndex(d.day) === hovered ? "true" : undefined}
                cx={x(calendarIndex(d.day))}
                cy={y(d.value)}
                r={calendarIndex(d.day) === hovered ? PASS + 1.5 : PASS}
              />
            ) : null,
          )}
          {hovered === null ? null : (
            <line
              className="case-flow__cursor"
              x1={tipX}
              x2={tipX}
              y1={PAD.top}
              y2={PAD.top + plotHeight}
            />
          )}
        </svg>
      ) : null}
      {tip === undefined || hovered === null ? null : (
        <div
          className="case-series__tip case-glass"
          data-side={tipX > width - 220 ? "left" : "right"}
          style={{ left: `${String(tipX)}px`, top: `${String(PAD.top + 18)}px` }}
        >
          <p className="case-series__tip-value">
            {formatReading(tip.value)} m³/s
            {tip.status === "Approved" ? "" : ` · ${tip.status.toLowerCase()}`}
          </p>
          <p className="case-series__tip-date">{formatDate(tip.day, true)}</p>
          {usual.p50[hovered] == null ? null : (
            <p className="case-series__tip-gauge">
              {copy.usualTip(
                formatReading(usual.p50[hovered] ?? 0),
                formatReading(usual.p10[hovered] ?? 0),
                formatReading(usual.p90[hovered] ?? 0),
              )}
            </p>
          )}
          {position === null ? null : (
            <p className="case-series__tip-gauge">{copy.position[position]}</p>
          )}
          {passes.has(tip.day) ? <p className="case-series__tip-gauge">{copy.legendPass}</p> : null}
        </div>
      )}
    </div>
  );
}

/**
 * The year's flow, day by day (the year the case shows), against the river's usual flow for each
 * calendar day (the reference years' median and 10th-to-90th percentile range,
 * preregistration-daily-record.md, section 4), with each satellite pass of the year on its day and
 * rule v1's low-flow and high-flow lines where they exist. On the left, the latest day in one
 * sentence (or the year's days below and above the usual range), and the year's sealed daily
 * record: "Check this record" and "Compare with the source now". A hidden table gives the year by
 * month to screen readers.
 *
 * @param props - The view's props.
 * @param props.reach - The reach as the case shows it.
 * @param props.climate - Its climate record (the usual flow, the latest day, the thresholds).
 * @returns The view (a note while the year has no daily record).
 */
export function FlowYear({ reach, climate }: FlowYearProps) {
  const copy = CASE_COPY.climate.flow;
  const year = reachYear(reach);
  const row = reach.dailyRecord?.find((r) => r.year === year);
  const record = useRecord(reach, row);
  const usual = climate.discharge.typical;
  if (usual == null || row === undefined) {
    return <p className="case-timeline__caption">{copy.none}</p>;
  }
  if (record === null) {
    return <p className="case-timeline__caption">{copy.loading}</p>;
  }
  const days = flowDays(record);
  const passes = new Set(reach.series.map((r) => r.date).filter((d) => d.startsWith(String(year))));
  const latest = climate.discharge.latest;
  const latestHere = latest?.day.startsWith(String(year)) === true ? latest : null;
  const positions = days.map((d) => bandPosition(d.value, d.day, usual));
  const below = positions.filter((p) => p === "below").length;
  const above = positions.filter((p) => p === "above").length;
  const thresholds = climate.extremes?.thresholds ?? null;
  const modelled = !record.source.measured;
  const source = copy.source[record.source.kind];
  const station = modelled
    ? record.source.name
    : record.source.stationId.replace(/^USGS-/, "USGS ");
  // The year by month, for screen readers: its mean flow beside the usual median's mean.
  const months = copy.months.map((month, m) => {
    const inMonth = days.filter((d) => Number(d.day.slice(5, 7)) === m + 1);
    const usualMonth = usual.p50
      .slice(MONTH_STARTS[m], MONTH_STARTS[m + 1])
      .flatMap((v) => (v == null ? [] : [v]));
    const mean = (values: readonly number[]) =>
      values.length === 0 ? null : values.reduce((a, b) => a + b, 0) / values.length;
    return { month, mean: mean(inMonth.map((d) => d.value)), usual: mean(usualMonth) };
  });
  return (
    <div className="case-climate case-flow">
      <div className="case-climate__facts">
        <div className="case-climate__fact case-flow__fact">
          {latestHere === null ? (
            <span className="case-climate__fact-value">
              <strong>{copy.yearWhat(year)}</strong> · {copy.yearCounts(below, above)}
            </span>
          ) : (
            <>
              <span className="case-climate__fact-value">
                <strong>
                  {copy.latest(formatDate(latestHere.day, true), formatReading(latestHere.value))}
                </strong>
                {latestHere.provisional ? <span> · {copy.provisional}</span> : null}
                {modelled ? <span> · {copy.modelled}</span> : null}
              </span>
              <span className="case-flow__sentence">
                {copy.higher(usual.first, usual.last, Math.round(latestHere.higherShare * 100))}
                <HelpTip label={copy.usualHelpLabel}>
                  {copy.usualHelp(usual.first, usual.last, usual.years)}
                </HelpTip>
              </span>
            </>
          )}
        </div>
        <div className="case-flow__record">
          <span>{copy.record(source, formatDate(row.fetchedUtc.slice(0, 10), true))}</span>
          <HelpTip label={copy.recordHelpLabel}>{copy.recordHelp}</HelpTip>
          {row.records > 1 ? (
            <span className="case-flow__changed">{copy.recordChanged(row.records)}</span>
          ) : null}
          <DailyRecordCheck reach={reach} row={row} record={record} />
        </div>
      </div>
      <div className="case-flow__plot">
        <p className="case-flow__legend" aria-hidden="true">
          <span className="case-flow__key case-flow__key--line">{year}</span>
          <span className="case-flow__key case-flow__key--band">
            {copy.legendUsual(usual.first, usual.last)}
          </span>
          <span className="case-flow__key case-flow__key--median">{copy.legendMedian}</span>
          <span className="case-flow__key case-flow__key--pass">{copy.legendPass}</span>
        </p>
        <FlowChart
          days={days}
          usual={usual}
          passes={passes}
          thresholds={thresholds}
          label={(modelled ? copy.chartModel : copy.chart)(String(year), station)}
        />
      </div>
      <table className="case-visually-hidden">
        <caption>{copy.table}</caption>
        <thead>
          <tr>
            <th scope="col">{copy.tableMonth}</th>
            <th scope="col">{copy.tableMean}</th>
            <th scope="col">{copy.tableUsual}</th>
          </tr>
        </thead>
        <tbody>
          {months.map((m) => (
            <tr key={m.month}>
              <th scope="row">{m.month}</th>
              <td>{m.mean === null ? "" : formatReading(m.mean)}</td>
              <td>{m.usual === null ? "" : formatReading(m.usual)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
