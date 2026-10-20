import { useId, useState, type KeyboardEvent, type PointerEvent } from "react";

import { CASE_COPY } from "../../../case/content.ts";
import { useSize } from "../../../case/panels/useSize.ts";
import { HOW_IT_WORKS } from "../content.ts";
import type { FlowDay, FlowStation } from "./flow.ts";

const copy = HOW_IT_WORKS.problem;
const PAD = { left: 40, right: 12, top: 10, bottom: 24 };
const HEIGHT = 204;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** The year the chapter opens on: Belle Chasse's most low-flow days among the satellite years. */
const FIRST_YEAR = 2023;

const flowText = (v: number) =>
  v >= 1000 ? `${(v / 1000).toFixed(v >= 10_000 || v % 1000 === 0 ? 0 : 1)}K` : v.toFixed(0);
const whole = (v: number) => Math.round(v).toLocaleString("en-US");
const dayText = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
// Grid values on a log scale: 1, 2 and 5 times each power of ten over about one decade, 1 and 3
// over a wider range, so there are three to six lines.
function logTicks(lo: number, hi: number): number[] {
  const steps = Math.log10(hi) - Math.log10(lo) > 1.6 ? [1, 3] : [1, 2, 5];
  const out: number[] = [];
  for (let p = Math.floor(Math.log10(lo)); p <= Math.ceil(Math.log10(hi)); p++) {
    for (const m of steps) {
      const t = m * 10 ** p;
      if (t >= lo && t <= hi) {
        out.push(t);
      }
    }
  }
  return out;
}
const name = (s: FlowStation) => CASE_COPY.rivers.names[s.id] ?? s.name;

// What a day says, in words: its flow, its date, its kind and whether the satellite saw it.
function dayWords(d: FlowDay): string {
  return [
    d.flow === null ? copy.noValue : `${whole(d.flow)} m³/s`,
    dayText(d.day),
    d.kind === "low" ? copy.lowDay : d.kind === "high" ? copy.highDay : null,
    d.seen ? copy.seen : copy.notSeen,
  ]
    .filter((w) => w !== null)
    .join(", ");
}

/**
 * A station's daily flow through one satellite year (a 2 px line, on a log scale so a river's low
 * days stay as visible as its floods), its low-flow and high-flow lines with the zones beyond them
 * washed, and a dot on each day the satellite had a clear view:
 * filled on a low-flow or high-flow day, a ring on any other day, so the two read apart without
 * colour. The reader picks the station and the year; moving over the chart (or focusing it and
 * pressing the arrow keys, which step through the clear-view days) reads out any day. The table
 * under the chart lists every clear-view day.
 *
 * @returns The chart, its controls and its table.
 */
export function FlowChart({ stations }: { readonly stations: readonly FlowStation[] }) {
  const ids = useId();
  const [ref, { width }] = useSize<HTMLDivElement>();
  const [stationAt, setStationAt] = useState(0);
  const station = stations[stationAt] ?? stations[0];
  const [yearPicked, setYearPicked] = useState(FIRST_YEAR);
  const data = station?.years.find((y) => y.year === yearPicked) ?? station?.years.at(-1);
  const [at, setAt] = useState<number | null>(null);
  const [byKeys, setByKeys] = useState(false);
  if (station === undefined || data === undefined) {
    return null;
  }
  const days = data.days;
  const plotW = Math.max(1, width - PAD.left - PAD.right);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const flows = days.flatMap((d) => (d.flow === null ? [] : [d.flow]));
  const lo = Math.min(station.lowLine, ...flows) / 1.25;
  const hi = Math.max(station.highLine, ...flows) * 1.12;
  const [l0, l1] = [Math.log10(lo), Math.log10(hi)];
  const ticks = logTicks(lo, hi);
  const x = (k: number) => PAD.left + ((k + 0.5) / days.length) * plotW;
  const y = (v: number) => PAD.top + (1 - (Math.log10(Math.max(v, lo)) - l0) / (l1 - l0)) * plotH;
  // Each line's label at the chart's left end, beyond the line (inside the plot when there is no
  // room), haloed so the flow line never hides it.
  const labelY = (v: number, beyond: "below" | "above") => {
    const below = y(v) + 15;
    const above = y(v) - 6;
    return beyond === "below"
      ? below > PAD.top + plotH - 2
        ? above
        : below
      : above < PAD.top + 10
        ? below
        : above;
  };
  // A day the station has no value for breaks the line: it is not drawn across.
  const line = days
    .map((d, k) => {
      if (d.flow === null) {
        return "";
      }
      const joined = days[k - 1]?.flow != null;
      return `${joined ? "L" : "M"}${x(k).toFixed(1)},${y(d.flow).toFixed(1)}`;
    })
    .join("");
  const missing = days.length - flows.length;
  const seenAt = days.flatMap((d, k) => (d.seen && d.flow !== null ? [k] : []));
  const on = at === null ? undefined : days[at];
  const monthEvery = plotW < 480 ? 3 : 1;
  const firstOf = (m: number) =>
    Math.round((Date.UTC(data.year, m, 1) - Date.UTC(data.year, 0, 1)) / 86_400_000);

  const pick = (k: number | null, keys: boolean) => {
    setAt(k === null ? null : Math.min(Math.max(0, k), days.length - 1));
    setByKeys(keys);
  };
  const onPointer = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const k = Math.floor(((event.clientX - box.left - PAD.left) / plotW) * days.length);
    pick(k < 0 || k >= days.length ? null : k, false);
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = seenAt.find((k) => k > (at ?? -1));
    const prev = [...seenAt].reverse().find((k) => k < (at ?? days.length));
    const to =
      event.key === "ArrowRight"
        ? next
        : event.key === "ArrowLeft"
          ? prev
          : event.key === "Home"
            ? seenAt[0]
            : event.key === "End"
              ? seenAt.at(-1)
              : null;
    if (to !== null) {
      event.preventDefault();
      if (to !== undefined) {
        pick(to, true);
      }
    }
  };
  const tipX = at === null ? 0 : x(at);
  const tipY = on?.flow == null ? PAD.top + plotH / 2 : y(on.flow);

  return (
    <figure className="how-chart how-flow">
      <div className="how-flow__controls">
        <div className="how-seg" role="group" aria-label={copy.stationLabel}>
          {stations.map((s, k) => (
            <button
              key={s.id}
              type="button"
              className="how-seg__option"
              aria-pressed={k === stationAt}
              onClick={() => {
                setStationAt(k);
                pick(null, false);
              }}
            >
              {name(s)}
            </button>
          ))}
        </div>
        <div className="how-seg how-seg--years" role="group" aria-label={copy.yearLabel}>
          {station.years.map((yr) => (
            <button
              key={yr.year}
              type="button"
              className="how-seg__option"
              aria-pressed={yr.year === data.year}
              onClick={() => {
                setYearPicked(yr.year);
                pick(null, false);
              }}
            >
              {yr.year}
            </button>
          ))}
        </div>
      </div>
      <figcaption className="how-chart__title" aria-live="polite">
        {copy.chartTitle(data)}
      </figcaption>
      <ul className="how-chart__keys">
        <li>
          <span className="how-key how-key--low" aria-hidden="true" />
          {copy.seenExtreme}
        </li>
        <li>
          <span className="how-key how-key--seen" aria-hidden="true" />
          {copy.seenOther}
        </li>
      </ul>
      <p className="how-chart__axis" aria-hidden="true">
        {copy.flowAxis}
      </p>
      <div
        className="how-chart__plot how-flow__plot"
        ref={ref}
        tabIndex={0}
        data-own-keys
        role="group"
        aria-label={copy.plotLabel(name(station), data.year)}
        aria-describedby={`${ids}-hint`}
        onPointerMove={onPointer}
        onPointerDown={onPointer}
        onPointerLeave={(event) => {
          if (event.pointerType === "mouse") {
            pick(null, false);
          }
        }}
        onKeyDown={onKey}
        onBlur={() => {
          if (byKeys) {
            pick(null, false);
          }
        }}
      >
        {width > 0 ? (
          <svg width={width} height={HEIGHT} aria-hidden="true">
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
              k % monthEvery !== 0 ? null : (
                <text
                  key={m}
                  className="how-chart__tick"
                  x={PAD.left + (firstOf(k) / days.length) * plotW + 2}
                  y={HEIGHT - 6}
                >
                  {m}
                </text>
              ),
            )}
            <rect
              className="how-chart__zone"
              x={PAD.left}
              y={y(station.lowLine)}
              width={plotW}
              height={Math.max(0, PAD.top + plotH - y(station.lowLine))}
            />
            <rect
              className="how-chart__zone"
              x={PAD.left}
              y={PAD.top}
              width={plotW}
              height={Math.max(0, y(station.highLine) - PAD.top)}
            />
            {[station.lowLine, station.highLine].map((v) => (
              <line
                key={v}
                className="how-chart__limit"
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(v)}
                y2={y(v)}
              />
            ))}
            <path className="how-chart__line" d={line} />
            <text
              className="how-chart__limit-label"
              x={PAD.left + 6}
              y={labelY(station.lowLine, "below")}
            >
              {copy.lowLine}
            </text>
            <text
              className="how-chart__limit-label"
              x={PAD.left + 6}
              y={labelY(station.highLine, "above")}
            >
              {copy.highLine}
            </text>
            {on === undefined || at === null ? null : (
              <line
                className="how-chart__cross"
                x1={tipX}
                x2={tipX}
                y1={PAD.top}
                y2={PAD.top + plotH}
              />
            )}
            {seenAt.map((k) => {
              const d = days[k];
              return d?.flow == null ? null : (
                <circle
                  key={d.day}
                  className="how-chart__dot"
                  data-extreme={d.kind !== "normal"}
                  data-on={at === k}
                  cx={x(k)}
                  cy={y(d.flow)}
                  r={at === k ? 6 : 4.5}
                />
              );
            })}
            {on?.flow == null || on.seen ? null : (
              <circle className="how-chart__marker" cx={tipX} cy={y(on.flow)} r={3.5} />
            )}
          </svg>
        ) : null}
        {on === undefined ? null : (
          <p
            className="how-chart__tip"
            style={{ left: `${String(tipX)}px`, top: `${String(tipY)}px` }}
            data-side={tipX > width - 190 ? "left" : "right"}
            aria-hidden="true"
          >
            <strong>{on.flow === null ? copy.noValue : `${whole(on.flow)} m³/s`}</strong>
            <span>{dayText(on.day)}</span>
            {on.kind === "normal" ? null : (
              <span className="how-chart__tip-kind">
                {on.kind === "low" ? copy.lowDay : copy.highDay}
              </span>
            )}
            <span className="how-chart__tip-seen" data-seen={on.seen}>
              {on.seen ? copy.seen : copy.notSeen}
            </span>
          </p>
        )}
      </div>
      <p className="how-small how-flow__hint" id={`${ids}-hint`}>
        {copy.hint}
      </p>
      <p className="hero-ui__visually-hidden" aria-live="polite">
        {byKeys && on !== undefined ? dayWords(on) : ""}
      </p>
      <p className="how-source">{copy.source(station.name, station.source, missing)}</p>
      <details className="how-table">
        <summary>{copy.tableCaption(data.year)}</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">{copy.day}</th>
              <th scope="col">{copy.flow}</th>
              <th scope="col">{copy.kind}</th>
            </tr>
          </thead>
          <tbody>
            {seenAt.map((k) => {
              const d = days[k];
              return d === undefined ? null : (
                <tr key={d.day}>
                  <td>{dayText(d.day)}</td>
                  <td>{d.flow === null ? "" : whole(d.flow)}</td>
                  <td>
                    {d.kind === "low"
                      ? copy.lowDay
                      : d.kind === "high"
                        ? copy.highDay
                        : copy.normal}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
