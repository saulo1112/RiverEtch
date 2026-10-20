import { XCircle } from "lucide-react";
import { useState } from "react";

import { CASE_COPY } from "../../../case/content.ts";
import { gainOver } from "../../../case/reading.ts";
import { oneDecimal } from "../../../case/rivers.ts";
import { HOW_IT_WORKS } from "../content.ts";
import type { StationSet } from "./numbers.ts";

const copy = HOW_IT_WORKS.works;
const name = (site: string) => CASE_COPY.rivers.names[site] ?? site;
type View = "never" | "own";

// What a station's two errors say, in the app's words (reading.ts gainOver).
function verdict(satellite: number, guess: number): string {
  const gain = gainOver(satellite, guess);
  return gain.kind === "times"
    ? copy.timesSmaller(gain.text)
    : gain.kind === "none"
      ? copy.noGain
      : copy.worse;
}

/**
 * Each station's typical error (satellite) beside guessing the river's usual value, two thin bars
 * on one scale, lowest error first, for either locked test: a model that never saw the river (the
 * transfer test, first) or one trained on the river's own earlier years (v5). A station that fails
 * says so in words and with a mark, never by colour alone. Hovering, focusing or tapping a row
 * shows its numbers and what they mean; the table under the chart lists them all.
 *
 * @returns The chart, its switch and its table.
 */
export function StationBars({
  never,
  own,
}: {
  readonly never: StationSet;
  readonly own: StationSet;
}) {
  const [view, setView] = useState<View>("never");
  const [on, setOn] = useState<string | null>(null);
  const data = view === "never" ? never : own;
  // One scale for both views, so switching moves the bars, not the axis.
  const top = Math.max(...[...never.rows, ...own.rows].flatMap((r) => [r.mdsa, r.nullMdsa])) * 1.05;
  const pct = (v: number) => `${((v / top) * 100).toFixed(2)}%`;
  const satellite = view === "never" ? copy.satelliteNever : copy.satelliteOwn;
  return (
    <figure className="how-chart how-works__bars">
      <div className="how-seg" role="group" aria-label={copy.viewLabel}>
        {(["never", "own"] as const).map((v) => (
          <button
            key={v}
            type="button"
            className="how-seg__option"
            aria-pressed={view === v}
            onClick={() => {
              setView(v);
              setOn(null);
            }}
          >
            {copy.views[v]}
          </button>
        ))}
      </div>
      <figcaption className="how-chart__title" aria-live="polite">
        {copy.barsTitle(view, data.beat, data.rows.length, data.fail)}
      </figcaption>
      <ul className="how-chart__keys">
        <li>
          <span className="how-key how-key--sat" aria-hidden="true" />
          {satellite}
        </li>
        <li>
          <span className="how-key how-key--guess" aria-hidden="true" />
          {copy.guess}
        </li>
      </ul>
      <ol className="how-bars" aria-label={copy.tableCaption}>
        {data.rows.map((r) => {
          const fails = r.level === "none";
          const words = verdict(r.mdsa, r.nullMdsa);
          return (
            <li
              key={r.site}
              className="how-bars__row"
              data-on={on === r.site}
              data-fails={fails}
              tabIndex={0}
              aria-label={`${name(r.site)}: ${satellite} ${oneDecimal(r.mdsa)} %, ${copy.guess} ${oneDecimal(r.nullMdsa)} %. ${words}. ${copy.passes(r.n)}${fails ? `. ${copy.fails}` : ""}`}
              onPointerEnter={() => {
                setOn(r.site);
              }}
              onPointerLeave={() => {
                setOn(null);
              }}
              onClick={() => {
                setOn(r.site);
              }}
              onFocus={() => {
                setOn(r.site);
              }}
              onBlur={() => {
                setOn(null);
              }}
            >
              <span className="how-bars__name" aria-hidden="true">
                {name(r.site)}
                {fails ? (
                  <span className="how-bars__fails">
                    <XCircle size={12} strokeWidth={2} aria-hidden="true" />
                    {copy.fails}
                  </span>
                ) : null}
              </span>
              <span className="how-bars__track" aria-hidden="true">
                <span className="how-bars__bar how-bars__bar--sat" style={{ width: pct(r.mdsa) }} />
                <span className="how-bars__value">{oneDecimal(r.mdsa)} %</span>
              </span>
              <span className="how-bars__track" aria-hidden="true">
                <span
                  className="how-bars__bar how-bars__bar--guess"
                  style={{ width: pct(r.nullMdsa) }}
                />
                <span className="how-bars__value">{oneDecimal(r.nullMdsa)} %</span>
              </span>
              {on === r.site ? (
                <span className="how-bars__tip" aria-hidden="true">
                  <strong>{name(r.site)}</strong>
                  <span className="how-bars__tip-row">
                    <span className="how-key how-key--sat" />
                    {copy.tipSatellite} <b>{oneDecimal(r.mdsa)} %</b>
                  </span>
                  <span className="how-bars__tip-row">
                    <span className="how-key how-key--guess" />
                    {copy.tipGuess} <b>{oneDecimal(r.nullMdsa)} %</b>
                  </span>
                  <span className="how-bars__tip-verdict" data-fails={fails}>
                    {words}
                  </span>
                  <span>{copy.passes(r.n)}</span>
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
      {data.unscored.length === 0 ? null : (
        <p className="how-small">{copy.unscored(data.unscored.map((r) => name(r.site)))}</p>
      )}
      <p className="how-small how-flow__hint">{copy.barsHint}</p>
      <p className="how-source">{copy.source}</p>
      <details className="how-table">
        <summary>{copy.tableCaption}</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">{copy.station}</th>
              <th scope="col">{satellite}</th>
              <th scope="col">{copy.guess}</th>
              <th scope="col">{copy.passesHead}</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.site}>
                <td>
                  {name(r.site)}
                  {r.level === "none" ? ` (${copy.fails})` : ""}
                </td>
                <td>{oneDecimal(r.mdsa)} %</td>
                <td>{oneDecimal(r.nullMdsa)} %</td>
                <td>{r.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
