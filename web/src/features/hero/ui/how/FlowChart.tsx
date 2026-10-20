import { useState } from "react";

import { useSize } from "../../../case/panels/useSize.ts";
import { HOW_IT_WORKS } from "../content.ts";
import type { FlowDay, FlowYear } from "./flow.ts";

const copy = HOW_IT_WORKS.problem;
const PAD = { left: 40, right: 12, top: 26, bottom: 24 };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const flowText = (v: number) =>
  v >= 1000 ? `${(v / 1000).toFixed(v >= 10_000 ? 0 : 1)}K` : v.toFixed(0);
const whole = (v: number) => Math.round(v).toLocaleString("en-US");
const dayText = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });

/**
 * A station's daily flow through one year (a 2 px line), its low-flow line with the low zone
 * washed under it, and a dot on each day the satellite had a clear view: filled on a low-flow day,
 * a ring on any other day, so the two read apart without colour. Hovering or focusing a dot shows
 * its day and flow; the table under the chart lists every one.
 *
 * @returns The chart and its table.
 */
export function FlowChart({ data }: { readonly data: FlowYear }) {
  const [ref, { width }] = useSize<HTMLDivElement>();
  const [tip, setTip] = useState<FlowDay | null>(null);
  const height = 200;
  const plotW = Math.max(1, width - PAD.left - PAD.right);
  const plotH = height - PAD.top - PAD.bottom;
  const top = Math.max(...data.days.map((d) => d.flow)) * 1.08;
  const step = top > 20_000 ? 10_000 : top > 6_000 ? 2_000 : 500;
  const ticks = Array.from({ length: Math.floor(top / step) + 1 }, (_, k) => k * step);
  const start = Date.UTC(data.year, 0, 1);
  const span = Date.UTC(data.year + 1, 0, 1) - start;
  const x = (iso: string) => PAD.left + ((Date.parse(`${iso}T00:00:00Z`) - start) / span) * plotW;
  const y = (v: number) => PAD.top + (1 - v / top) * plotH;
  // A day the station has no value for breaks the line: it is not drawn across.
  const DAY = 86_400_000;
  const line = data.days
    .map((d, k) => {
      const prev = data.days[k - 1];
      const joined = prev !== undefined && Date.parse(d.day) - Date.parse(prev.day) === DAY;
      return `${joined ? "L" : "M"}${x(d.day).toFixed(1)},${y(d.flow).toFixed(1)}`;
    })
    .join("");
  const missing = Math.round(span / DAY) - data.days.length;
  const seen = data.days.filter((d) => d.seen);
  return (
    <figure className="how-chart">
      <figcaption className="how-chart__title">
        {copy.chartTitle(data.lowDays, data.lowSeen, data.year)}
      </figcaption>
      <ul className="how-chart__keys" aria-label={copy.chartNote}>
        <li>
          <span className="how-key how-key--low" aria-hidden="true" />
          {copy.seenLow}
        </li>
        <li>
          <span className="how-key how-key--seen" aria-hidden="true" />
          {copy.seenOther}
        </li>
        <li>
          <span className="how-key how-key--line" aria-hidden="true" />
          {copy.lowLine}
        </li>
      </ul>
      <div className="how-chart__plot" ref={ref}>
        {width > 0 ? (
          <svg
            width={width}
            height={height}
            role="img"
            aria-label={copy.chartTitle(data.lowDays, data.lowSeen, data.year)}
          >
            <text className="how-chart__tick how-chart__unit" x={0} y={12}>
              {copy.flowAxis}
            </text>
            {ticks.map((t) => (
              <g key={t}>
                <line
                  className="how-chart__grid"
                  x1={PAD.left}
                  x2={width - PAD.right}
                  y1={y(t)}
                  y2={y(t)}
                />
                <text className="how-chart__tick" x={PAD.left - 6} y={y(t) + 4} textAnchor="end">
                  {flowText(t)}
                </text>
              </g>
            ))}
            {MONTHS.map((m, k) =>
              // A narrow chart names every third month, so the labels never touch.
              plotW < 480 && k % 3 !== 0 ? null : (
                <text
                  key={m}
                  className="how-chart__tick"
                  x={x(`${String(data.year)}-${String(k + 1).padStart(2, "0")}-01`) + 2}
                  y={height - 6}
                >
                  {m}
                </text>
              ),
            )}
            <rect
              className="how-chart__low-zone"
              x={PAD.left}
              y={y(data.lowLine)}
              width={plotW}
              height={PAD.top + plotH - y(data.lowLine)}
            />
            <line
              className="how-chart__low-line"
              x1={PAD.left}
              x2={width - PAD.right}
              y1={y(data.lowLine)}
              y2={y(data.lowLine)}
            />
            <path className="how-chart__line" d={line} />
            {seen.map((d) => (
              <circle
                key={d.day}
                className="how-chart__dot"
                data-low={d.low}
                data-on={tip?.day === d.day}
                cx={x(d.day)}
                cy={y(d.flow)}
                r={tip?.day === d.day ? 5.5 : 4.5}
              />
            ))}
            {/* Hit areas bigger than the dots. */}
            {seen.map((d) => (
              <circle
                key={`hit-${d.day}`}
                className="how-chart__hit"
                cx={x(d.day)}
                cy={y(d.flow)}
                r={12}
                onPointerEnter={() => {
                  setTip(d);
                }}
                onPointerLeave={() => {
                  setTip(null);
                }}
              />
            ))}
          </svg>
        ) : null}
        {tip === null ? null : (
          <p
            className="how-chart__tip"
            style={{ left: `${String(x(tip.day))}px`, top: `${String(y(tip.flow))}px` }}
            data-side={x(tip.day) > width - 160 ? "left" : "right"}
          >
            <strong>{whole(tip.flow)} m³/s</strong>
            <span>
              {dayText(tip.day)}
              {tip.low ? ` · ${copy.lowDay.toLowerCase()}` : ""}
            </span>
          </p>
        )}
      </div>
      <p className="how-source">{copy.source(data.station.name, data.source, missing)}</p>
      <details className="how-table">
        <summary>{copy.tableCaption}</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">{copy.day}</th>
              <th scope="col">{copy.flow}</th>
              <th scope="col">{copy.lowDay}</th>
            </tr>
          </thead>
          <tbody>
            {seen.map((d) => (
              <tr key={d.day}>
                <td>{dayText(d.day)}</td>
                <td>{whole(d.flow)}</td>
                <td>{d.low ? copy.yes : copy.no}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
