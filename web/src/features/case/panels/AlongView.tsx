import { useState, type KeyboardEvent, type PointerEvent } from "react";

import { CLASS_COLORS, alongPasses, placeOf, readCount, riverLength } from "../../reaches/along.ts";
import type { FnuClass, ReachData } from "../../reaches/types.ts";
import { CASE_COPY, daysBetween, formatDate } from "../content.ts";
import { useSize } from "./useSize.ts";

/** Props of {@link AlongView}. */
export interface AlongViewProps {
  readonly reach: ReachData;
  /** Index of the selected pass in the series. */
  readonly selected: number;
  /** Selects a pass (its index in the series). */
  readonly onSelect: (index: number) => void;
  /** Marks a place on the map's river (a fraction from upstream; null: none). */
  readonly onProbe: (place: number | null) => void;
}

// Chart geometry (CSS px), as the other charts': the distance axis left, the months below, the
// station's row named on the right. A small chart (a phone's panel) keeps its height for the rows:
// the unit moves beside the months and the station's row keeps only its mark.
function frame(width: number, height: number) {
  const compact = height < 100 || width < 520;
  return { compact, left: 40, right: compact ? 14 : 88, top: compact ? 4 : 18, bottom: 20 };
}
const NONE = "rgb(240 246 255 / 0.07)"; // a stretch the pass could not read

const copy = CASE_COPY.along;

// The months from the first pass's January to the last pass, and the x scale over them (the same
// axis as the turbidity chart's, so a column sits under its pass).
function timeAxis(dates: readonly string[], width: number, pad: ReturnType<typeof frame>) {
  const first = dates[0] ?? "2026-01-01";
  const start = `${first.slice(0, 4)}-01-01`;
  const end = dates.at(-1) ?? first;
  const span = Math.max(30, daysBetween(start, end) + 6);
  const plotWidth = Math.max(1, width - pad.left - pad.right);
  const months: string[] = [];
  const cursor = new Date(`${start}T00:00:00Z`);
  while (daysBetween(cursor.toISOString().slice(0, 10), end) >= 0) {
    months.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  return {
    months,
    x: (date: string) => pad.left + (daysBetween(start, date) / span) * plotWidth,
    dayPx: plotWidth / span,
  };
}

// The window nearest the reach's station or reading spot (its point in the geometry).
function spotWindow(reach: ReachData): number | null {
  const point = reach.geometry?.features.find((f) => f.properties.kind === "station");
  const windows = reach.along?.plan.windows ?? [];
  if (point?.geometry.type !== "Point" || windows.length === 0) {
    return null;
  }
  const [lon, lat] = point.geometry.coordinates as [number, number];
  const scale = Math.cos((lat * Math.PI) / 180);
  let best = 0;
  let distance = Infinity;
  windows.forEach((w, k) => {
    const d = Math.hypot((w.lon - lon) * scale, w.lat - lat);
    if (d < distance) {
      best = k;
      distance = d;
    }
  });
  return best;
}

/**
 * The year's passes along the whole river: each column a pass (on the turbidity chart's time
 * axis), each row a stretch of river from upstream (top) to downstream, coloured by its turbidity
 * class, a stretch the pass could not read left faint. Hovering a cell names its day, its stretch
 * and its class and marks the stretch on the map; clicking a column selects that pass. The arrow
 * keys step through passes (left, right) and stretches (up, down).
 *
 * @param props - The view's props.
 * @param props.reach - The reach, with its classes along the river.
 * @param props.selected - Index of the selected pass in the series.
 * @param props.onSelect - Selects a pass.
 * @param props.onProbe - Marks a place on the map's river.
 * @returns The view.
 */
export function AlongView({ reach, selected, onSelect, onProbe }: AlongViewProps) {
  const [plotRef, { width, height }] = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<{ column: number; row: number } | null>(null);
  const [focusRow, setFocusRow] = useState(0);
  const along = reach.along;
  const passes = alongPasses(reach);
  if (along === undefined || along === null || passes.length === 0) {
    return <p className="case-along__empty">{copy.empty}</p>;
  }
  const windows = along.plan.windows;
  const length = riverLength(reach);
  const PAD = frame(width, height);
  const { months, x, dayPx } = timeAxis(
    passes.map((p) => p.pass.date),
    width,
    PAD,
  );
  const plotHeight = Math.max(1, height - PAD.top - PAD.bottom);
  const rowH = plotHeight / Math.max(1, windows.length);
  const cellW = Math.max(3, Math.min(10, dayPx * 3));
  const gap = rowH > 5 ? 1 : 0;
  const y = (row: number) => PAD.top + row * rowH;
  const column = passes.findIndex((p) => p.index === selected);
  const spot = spotWindow(reach);
  const kmTicks: number[] = [];
  const stepKm = length > 40_000 ? 10 : length > 12_000 ? 5 : 2;
  for (let km = 0; km * 1000 <= length; km += stepKm) {
    kmTicks.push(km);
  }
  const rowOfKm = (km: number) => PAD.top + (length > 0 ? ((km * 1000) / length) * plotHeight : 0);

  const pick = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    if (
      px < PAD.left - 4 ||
      px > width - PAD.right + 4 ||
      py < PAD.top ||
      py > PAD.top + plotHeight
    ) {
      return null;
    }
    let best = 0;
    let distance = Infinity;
    passes.forEach((p, k) => {
      const d = Math.abs(x(p.pass.date) - px);
      if (d < distance) {
        best = k;
        distance = d;
      }
    });
    const row = Math.min(windows.length - 1, Math.max(0, Math.floor((py - PAD.top) / rowH)));
    return { column: best, row };
  };
  const show = (cell: { column: number; row: number } | null) => {
    setHover(cell);
    const w = cell === null ? undefined : windows[cell.row];
    onProbe(w === undefined ? null : placeOf(w.chainageM, length));
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const dx = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    const dy = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if (dx === 0 && dy === 0) {
      return;
    }
    event.preventDefault();
    const at = column < 0 ? 0 : column;
    if (dx !== 0) {
      const next = passes[Math.min(passes.length - 1, Math.max(0, at + dx))];
      if (next !== undefined) {
        onSelect(next.index);
      }
    }
    const row = Math.min(windows.length - 1, Math.max(0, focusRow + dy));
    setFocusRow(row);
    const w = windows[row];
    onProbe(w === undefined ? null : placeOf(w.chainageM, length));
  };

  const tip = hover === null ? undefined : passes[hover.column];
  const tipWindow = hover === null ? undefined : windows[hover.row];
  const tipClass =
    tip === undefined || hover === null ? null : (tip.pass.classes[hover.row] ?? null);
  const current = column < 0 ? undefined : passes[column];
  const focused = windows[focusRow];
  const km = (m: number) => (m / 1000).toFixed(1);
  const stretch = (row: number) => {
    const w = windows[row];
    if (w === undefined) {
      return "";
    }
    const half = along.plan.spacingM / 2;
    return copy.stretch(km(Math.max(0, w.chainageM - half)), km(w.chainageM + half));
  };
  const words = (cls: FnuClass | null, reason: string | null | undefined) =>
    cls === null ? (reason ?? CASE_COPY.ungauged.noClass) : CASE_COPY.ungauged.classes[cls];

  return (
    <div
      className="case-along"
      ref={plotRef}
      role="group"
      tabIndex={0}
      aria-label={copy.chartLabel}
      data-own-keys=""
      onKeyDown={onKey}
      onPointerMove={(event) => {
        show(pick(event));
      }}
      onPointerLeave={() => {
        show(null);
      }}
      onClick={(event) => {
        const cell = pick(event as unknown as PointerEvent<HTMLDivElement>);
        const pass = cell === null ? undefined : passes[cell.column];
        if (pass !== undefined) {
          onSelect(pass.index);
        }
      }}
    >
      {width > 0 && height > 0 ? (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${String(width)} ${String(height)}`}
          aria-hidden="true"
        >
          {passes.map((p, c) =>
            windows.map((w, r) => {
              const cls = p.pass.classes[r] ?? null;
              return (
                <rect
                  key={`${p.pass.sceneId}-${w.id}`}
                  x={x(p.pass.date) - cellW / 2}
                  y={y(r)}
                  width={cellW}
                  height={Math.max(1, rowH - gap)}
                  rx={cellW > 5 && rowH > 5 ? 1.5 : 0}
                  fill={cls === null ? NONE : (CLASS_COLORS[cls] ?? NONE)}
                  data-hover={hover?.column === c && hover.row === r ? "true" : undefined}
                  className="case-along__cell"
                />
              );
            }),
          )}
          {current === undefined ? null : (
            <rect
              className="case-along__selected"
              x={x(current.pass.date) - cellW / 2 - 1.5}
              y={PAD.top - 1.5}
              width={cellW + 3}
              height={plotHeight + 3}
              rx={2}
            />
          )}
          {kmTicks.map((k) => (
            <text
              key={k}
              className="case-series__tick"
              x={PAD.left - 6}
              y={rowOfKm(k) + 3.5}
              textAnchor="end"
            >
              {k}
            </text>
          ))}
          <text className="case-series__unit" x={4} y={PAD.compact ? height - 6 : 10}>
            {PAD.compact ? copy.unitShort : copy.unit}
          </text>
          {spot === null ? null : (
            <g className="case-along__spot">
              <line
                x1={width - PAD.right + 4}
                x2={width - PAD.right + 10}
                y1={y(spot) + rowH / 2}
                y2={y(spot) + rowH / 2}
              />
              {PAD.compact ? null : (
                <text x={width - PAD.right + 13} y={y(spot) + rowH / 2 + 3.5}>
                  {reach.info.station.window === undefined ? copy.station : copy.spot}
                </text>
              )}
            </g>
          )}
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
        </svg>
      ) : null}
      {tip === undefined || tipWindow === undefined || hover === null ? null : (
        <div
          className="case-series__tip case-glass"
          data-side={x(tip.pass.date) > width - 240 ? "left" : "right"}
          style={{
            left: `${String(x(tip.pass.date))}px`,
            top: `${String(y(hover.row) + rowH / 2)}px`,
          }}
        >
          <p className="case-series__tip-date">
            {formatDate(tip.pass.date, true)} · {stretch(hover.row)}
          </p>
          {tipClass === null ? (
            <p className="case-series__tip-none">{words(null, tip.pass.reasons[hover.row])}</p>
          ) : (
            <p className="case-series__tip-value">{words(tipClass, null)}</p>
          )}
          <p className="case-series__tip-gauge">{copy.read(readCount(tip.pass), windows.length)}</p>
        </div>
      )}
      <p className="case-visually-hidden" aria-live="polite">
        {current === undefined || focused === undefined
          ? ""
          : `${formatDate(current.pass.date, true)}, ${stretch(focusRow)}: ${words(
              current.pass.classes[focusRow] ?? null,
              current.pass.reasons[focusRow],
            )}`}
      </p>
    </div>
  );
}
