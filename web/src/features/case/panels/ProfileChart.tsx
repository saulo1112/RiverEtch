import { useState } from "react";

import type { ProfilePoint } from "../../reaches/analysis.ts";
import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY } from "../content.ts";
import { rampRgb } from "../ramp.ts";
import { useSize } from "./useSize.ts";

/** Props of {@link ProfileChart}. */
export interface ProfileChartProps {
  readonly reach: ReachData;
  /** The selected pass's profile (null while it loads). */
  readonly points: readonly ProfilePoint[] | null;
  /** The NDTI ramp's domain. */
  readonly domain: readonly [number, number];
  /** The cursor moved to a place along the river (null: it left). */
  readonly onProbe: (place: number | null) => void;
}

const PAD = { left: 40, right: 10, top: 20, bottom: 22 };

/**
 * The selected pass's NDTI along the river, from the upstream anchor (left) to the downstream one,
 * colored on the ramp; stretches the pass could not see are shaded. Hovering marks the place on
 * the map.
 *
 * @returns The chart.
 */
export function ProfileChart({ reach, points, domain, onProbe }: ProfileChartProps) {
  const [plotRef, { width, height }] = useSize<HTMLDivElement>();
  const [cursor, setCursor] = useState<number | null>(null);
  const features = reach.geometry?.features ?? [];
  const river = features.find((f) => f.properties.kind === "river");
  const lengthM = river?.properties.lengthM ?? 1;
  const plotWidth = Math.max(1, width - PAD.left - PAD.right);
  const plotHeight = Math.max(1, height - PAD.top - PAD.bottom);
  const x = (place: number) => PAD.left + place * plotWidth;
  const y = (ndti: number) =>
    PAD.top + (1 - (ndti - domain[0]) / (domain[1] - domain[0] || 1)) * plotHeight;
  const tone = (ndti: number) => {
    const [r, g, b] = rampRgb((ndti - domain[0]) / (domain[1] - domain[0] || 1));
    return `rgb(${String(r)} ${String(g)} ${String(b)})`;
  };
  const kmTicks: number[] = [];
  const step = lengthM > 15_000 ? 5 : 2;
  for (let km = 0; km <= lengthM / 1000; km += step) {
    kmTicks.push(km);
  }
  const at = cursor === null || points === null ? undefined : points[cursor];

  return (
    <div
      className="case-profile"
      ref={plotRef}
      onPointerMove={(event) => {
        if (points === null || points.length === 0) {
          return;
        }
        const rect = event.currentTarget.getBoundingClientRect();
        const place = (event.clientX - rect.left - PAD.left) / plotWidth;
        if (place < 0 || place > 1) {
          setCursor(null);
          onProbe(null);
          return;
        }
        const index = Math.min(points.length - 1, Math.floor(place * points.length));
        setCursor(index);
        onProbe(points[index]?.place ?? place);
      }}
      onPointerLeave={() => {
        setCursor(null);
        onProbe(null);
      }}
    >
      <p className="case-visually-hidden">{CASE_COPY.profile.title}</p>
      {width > 0 && height > 0 && points !== null ? (
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${String(width)} ${String(height)}`}
          aria-hidden="true"
        >
          {[domain[0], (domain[0] + domain[1]) / 2, domain[1]].map((v) => (
            <g key={v}>
              <line
                className="case-series__grid"
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(v)}
                y2={y(v)}
              />
              <text className="case-series__tick" x={PAD.left - 6} y={y(v) + 3.5} textAnchor="end">
                {v.toFixed(2)}
              </text>
            </g>
          ))}
          <text className="case-series__unit" x={4} y={9}>
            NDTI
          </text>
          {kmTicks.map((km) => (
            <text
              key={km}
              className="case-series__tick"
              x={x((km * 1000) / lengthM)}
              y={height - 6}
              textAnchor="middle"
            >
              {km} km
            </text>
          ))}
          {points.map((p, k) => {
            const w = plotWidth / points.length;
            return p.usable < 0.3 ? (
              <rect
                key={`u${String(k)}`}
                className="case-profile__unusable"
                x={x(p.place) - w / 2}
                y={PAD.top}
                width={w}
                height={plotHeight}
              />
            ) : null;
          })}
          {points.map((p, k) => {
            const next = points[k + 1];
            return p.ndti === null || next?.ndti == null ? null : (
              <line
                key={`l${String(k)}`}
                className="case-profile__line"
                x1={x(p.place)}
                x2={x(next.place)}
                y1={y(p.ndti)}
                y2={y(next.ndti)}
                stroke={tone((p.ndti + next.ndti) / 2)}
              />
            );
          })}
          {at === undefined ? null : (
            <g>
              <line
                className="case-series__cursor"
                x1={x(at.place)}
                x2={x(at.place)}
                y1={PAD.top}
                y2={PAD.top + plotHeight}
              />
              {at.ndti === null ? null : (
                <>
                  <circle
                    className="case-profile__dot"
                    cx={x(at.place)}
                    cy={y(at.ndti)}
                    r={4.5}
                    fill={tone(at.ndti)}
                  />
                  <text
                    className="case-profile__readout"
                    x={x(at.place) + (at.place > 0.8 ? -8 : 8)}
                    y={y(at.ndti) - 8}
                    textAnchor={at.place > 0.8 ? "end" : "start"}
                  >
                    {(at.place * (lengthM / 1000)).toFixed(1)} km · {at.ndti >= 0 ? "+" : "−"}
                    {Math.abs(at.ndti).toFixed(3)}
                  </text>
                </>
              )}
            </g>
          )}
        </svg>
      ) : null}
    </div>
  );
}
