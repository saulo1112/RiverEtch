import { XCircle } from "lucide-react";
import { useState } from "react";

import { CASE_COPY } from "../../../case/content.ts";
import { oneDecimal } from "../../../case/rivers.ts";
import { HOW_IT_WORKS } from "../content.ts";
import type { NeverSaw } from "./numbers.ts";

const copy = HOW_IT_WORKS.works;
const name = (site: string) => CASE_COPY.rivers.names[site] ?? site;

/**
 * The test on rivers the model never saw: each station's typical error (satellite) beside
 * guessing the river's usual value, two thin bars on one scale, lowest error first. A station
 * that fails says so in words and with a mark, never by colour alone. Hovering or focusing a row
 * shows both values; the table under the chart lists them.
 *
 * @returns The chart and its table.
 */
export function StationBars({ data }: { readonly data: NeverSaw }) {
  const [on, setOn] = useState<string | null>(null);
  const top = Math.max(...data.rows.flatMap((r) => [r.mdsa, r.nullMdsa])) * 1.05;
  const pct = (v: number) => `${((v / top) * 100).toFixed(2)}%`;
  return (
    <figure className="how-chart">
      <figcaption className="how-chart__title">
        {copy.barsTitle(data.beat, data.rows.length, data.fail)}
      </figcaption>
      <ul className="how-chart__keys">
        <li>
          <span className="how-key how-key--sat" aria-hidden="true" />
          {copy.satellite}
        </li>
        <li>
          <span className="how-key how-key--guess" aria-hidden="true" />
          {copy.guess}
        </li>
      </ul>
      <ol className="how-bars" aria-label={copy.tableCaption}>
        {data.rows.map((r) => {
          const fails = r.level === "none";
          return (
            <li
              key={r.site}
              className="how-bars__row"
              data-on={on === r.site}
              data-fails={fails}
              tabIndex={0}
              aria-label={`${name(r.site)}: ${copy.satellite} ${oneDecimal(r.mdsa)} %, ${copy.guess} ${oneDecimal(r.nullMdsa)} %${fails ? `, ${copy.fails}` : ""}`}
              onPointerEnter={() => {
                setOn(r.site);
              }}
              onPointerLeave={() => {
                setOn(null);
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
            </li>
          );
        })}
      </ol>
      <p className="how-source">{copy.source}</p>
      <details className="how-table">
        <summary>{copy.tableCaption}</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">{copy.station}</th>
              <th scope="col">{copy.satellite}</th>
              <th scope="col">{copy.guess}</th>
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
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
