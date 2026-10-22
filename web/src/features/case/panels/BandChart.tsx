import { useState, type KeyboardEvent } from "react";

import { CASE_COPY, daysBetween, formatDate } from "../content.ts";
import type { BandPoint } from "../spot.ts";
import { useSize } from "./useSize.ts";

/** Props of {@link BandChart}. */
export interface BandChartProps {
  readonly points: readonly BandPoint[];
  /** The classes, lowest first: one band each. */
  readonly classes: readonly string[];
  /** The edges between the bands, labelled on the axis. */
  readonly edges: readonly number[];
  /** The edges' unit, e.g. "FNU" or "°C". */
  readonly unit: string;
  /** A class in words, e.g. "Under 30 FNU". */
  readonly label: (cls: string) => string;
  /** Index of the selected pass (null: none). */
  readonly selected: number | null;
  /** A day drawn as the dashed cursor (the map's pass, on another satellite's chart). */
  readonly cursor?: string | null;
  readonly onSelect: (index: number) => void;
  /** What the chart is, for a screen reader. */
  readonly ariaLabel: string;
  /** Prefix of each pass's element id (unique on the page). */
  readonly idPrefix: string;
  /** The dots' tone: Sentinel-2's (turbidity) or Landsat's (water temperature). */
  readonly tone?: "sat" | "thermal";
}

// Chart geometry (CSS px), as the turbidity chart's.
const PAD = { left: 34, right: 10, top: 20, bottom: 22 };
const DOT = 4.5;

/**
 * A stretch of river's passes by class (preregistration-along-temperature.md, section 3): one
 * band per class, each pass a dot in the middle of its band; the height means only the class,
 * never a value. A pass with no reading draws no mark. Hovering a pass names its day and class;
 * clicking it, or the arrow keys, selects it.
 *
 * @param props - The passes, the classes and the selection.
 * @param props.points - Each pass, its day and class.
 * @param props.classes - The classes, lowest first.
 * @param props.edges - The edges between the bands.
 * @param props.unit - The edges' unit.
 * @param props.label - A class in words.
 * @param props.selected - Index of the selected pass.
 * @param props.cursor - A day drawn as the dashed cursor.
 * @param props.onSelect - Selects a pass.
 * @param props.ariaLabel - What the chart is, for a screen reader.
 * @param props.idPrefix - Prefix of each pass's element id.
 * @param props.tone - The dots' tone.
 * @returns The chart.
 */
export function BandChart({
  points,
  classes,
  edges,
  unit,
  label,
  selected,
  cursor = null,
  onSelect,
  ariaLabel,
  idPrefix,
  tone = "sat",
}: BandChartProps) {
  const [plotRef, { width, height }] = useSize<HTMLDivElement>();
  const [hovered, setHovered] = useState<number | null>(null);
  const first = points[0]?.date ?? "2026-01-01";
  const start = `${first.slice(0, 4)}-01-01`;
  const last = points.at(-1)?.date ?? first;
  const end = cursor !== null && cursor > last ? cursor : last;
  const span = Math.max(30, daysBetween(start, end) + 6);
  const plotWidth = Math.max(1, width - PAD.left - PAD.right);
  const plotHeight = Math.max(1, height - PAD.top - PAD.bottom);
  const x = (date: string) => PAD.left + (daysBetween(start, date) / span) * plotWidth;
  const band = plotHeight / Math.max(1, classes.length);
  const baseY = PAD.top + plotHeight;
  const at = (cls: string) => baseY - (classes.indexOf(cls) + 0.5) * band;
  const months: string[] = [];
  const month = new Date(`${start}T00:00:00Z`);
  while (daysBetween(month.toISOString().slice(0, 10), end) >= 0) {
    months.push(month.toISOString().slice(0, 10));
    month.setUTCMonth(month.getUTCMonth() + 1);
  }
  const read = points.filter((p): p is BandPoint & { cls: string } => p.cls !== null);
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step === 0 || read.length === 0) {
      return;
    }
    event.preventDefault();
    // The next pass with a reading, in date order.
    const now = read.findIndex((p) => p.index === selected);
    const next = read[Math.min(read.length - 1, Math.max(0, (now < 0 ? read.length : now) + step))];
    if (next !== undefined) {
      onSelect(next.index);
    }
  };
  const current = points.find((p) => p.index === selected);
  const tip = read.find((p) => p.index === hovered);
  const dot =
    tone === "thermal" ? "case-series__dot case-series__dot--thermal" : "case-series__dot";
  return (
    <div
      className="case-series"
      ref={plotRef}
      role="listbox"
      tabIndex={0}
      aria-label={ariaLabel}
      aria-activedescendant={
        current?.cls == null ? undefined : `${idPrefix}-${String(current.index)}`
      }
      onKeyDown={onKey}
    >
      {width > 0 && height > 0 ? (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${String(width)} ${String(height)}`}
          aria-hidden="true"
        >
          {edges.map((edge, k) => (
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
            {unit}
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
          {(cursor ?? current?.date) == null ? null : (
            <line
              className="case-series__cursor"
              x1={x(cursor ?? current?.date ?? start)}
              x2={x(cursor ?? current?.date ?? start)}
              y1={PAD.top}
              y2={baseY}
            />
          )}
          {read.map((p) => (
            <circle
              key={p.index}
              className={dot}
              data-selected={p.index === selected}
              cx={x(p.date)}
              cy={at(p.cls)}
              r={p.index === selected || p.index === hovered ? DOT + 1.5 : DOT}
            />
          ))}
        </svg>
      ) : null}
      {width > 0
        ? read.map((p) => (
            <button
              key={p.index}
              id={`${idPrefix}-${String(p.index)}`}
              type="button"
              role="option"
              aria-selected={p.index === selected}
              tabIndex={-1}
              className="case-series__hit"
              style={{ left: `${String(x(p.date) - 9)}px`, top: `${String(at(p.cls) - 9)}px` }}
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
                {formatDate(p.date, true)}: {label(p.cls)}
              </span>
            </button>
          ))
        : null}
      {tip === undefined ? null : (
        <div
          className="case-series__tip case-glass"
          data-side={x(tip.date) > width - 220 ? "left" : "right"}
          style={{ left: `${String(x(tip.date))}px`, top: `${String(at(tip.cls))}px` }}
        >
          <p className="case-series__tip-date">{formatDate(tip.date, true)}</p>
          <p className="case-series__tip-value">{label(tip.cls)}</p>
        </div>
      )}
      {read.length === 0 && width > 0 ? (
        <p className="case-along__empty case-series__empty">{CASE_COPY.spot.noReadings}</p>
      ) : null}
    </div>
  );
}
