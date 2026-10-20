import { useState } from "react";

import { CASE_COPY, LEVEL_LABELS } from "../content.ts";
import { gainOver, insideCount } from "../reading.ts";
import { DEMO_GAUGES, oneDecimal, type RiverResult } from "../rivers.ts";
import { HelpTip } from "./HelpTip.tsx";

const copy = CASE_COPY.rivers;

/** Props of {@link AllRiversView}. */
export interface AllRiversViewProps {
  /** Every evaluated river, lowest error first ({@link riverResults}). */
  readonly rivers: readonly RiverResult[];
  /** The same rivers, each scored by a model that never saw it ({@link transferResults}). */
  readonly transfer?: readonly RiverResult[];
  /** The case's own gauge, e.g. "USGS-06805500". */
  readonly station: string;
}

// The gain over guessing the usual value, in a few words.
function gainText(r: RiverResult): string {
  if (r.mdsa === null || r.nullMdsa === null) {
    return "";
  }
  const gain = gainOver(r.mdsa, r.nullMdsa);
  return gain.kind === "times"
    ? copy.gain(gain.text)
    : gain.kind === "worse"
      ? copy.worse
      : copy.noGain;
}

/**
 * Every river the validation evaluated, lowest locked-test error first: its level, the satellite's
 * error beside guessing the river's usual value, and its test passes, the rivers that do not beat
 * the guess included. The demo reaches are marked; the summary over all of them is the tab's
 * caption. A switch shows the same rivers scored by a model that never saw each one.
 *
 * @returns The table.
 */
export function AllRiversView({ rivers, transfer = [], station }: AllRiversViewProps) {
  const { columns } = copy;
  const [view, setView] = useState<"own" | "never">("own");
  const shown = view === "never" && transfer.length > 0 ? transfer : rivers;
  return (
    <div className="case-rivers">
      {transfer.length === 0 ? null : (
        <div className="case-rivers__views" role="group" aria-label={copy.viewsLabel}>
          {(["own", "never"] as const).map((v) => (
            <button
              key={v}
              type="button"
              className="case-btn case-btn--ghost case-rivers__view"
              aria-pressed={view === v}
              onClick={() => {
                setView(v);
              }}
            >
              {copy.views[v]}
            </button>
          ))}
        </div>
      )}
      {view === "never" ? <p className="case-rivers__note">{copy.neverNote}</p> : null}
      <table className="case-rivers__table" role="table">
        <caption className="case-visually-hidden">{copy.tableCaption}</caption>
        <thead role="rowgroup">
          <tr role="row">
            <th scope="col" role="columnheader">
              {columns.river}
            </th>
            <th scope="col" role="columnheader">
              {columns.level}
            </th>
            <th scope="col" role="columnheader">
              <span className="case-rivers__head">
                {columns.satellite}
                <HelpTip label={copy.errorHelpLabel}>{copy.errorHelp}</HelpTip>
              </span>
            </th>
            <th scope="col" role="columnheader">
              {columns.baseline}
            </th>
            <th scope="col" role="columnheader">
              {columns.passes}
            </th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          {shown.map((r) => {
            const demo = DEMO_GAUGES.includes(r.site);
            const mark = r.site === station ? copy.thisCase : demo ? copy.demo : null;
            return (
              <tr
                key={r.site}
                role="row"
                data-demo={demo || undefined}
                data-here={r.site === station || undefined}
              >
                <th scope="row" role="rowheader">
                  {copy.names[r.site] ?? r.site}{" "}
                  <span className="case-rivers__muted">({r.site.replace("USGS-", "")})</span>
                  {mark === null ? null : <span className="case-rivers__mark"> · {mark}</span>}
                </th>
                <td role="cell">
                  {r.level === null ? (
                    <span className="case-chip case-chip--quiet">{copy.insufficient}</span>
                  ) : (
                    <span className="case-chip case-chip--level" data-level={r.level}>
                      {LEVEL_LABELS[r.level]}
                    </span>
                  )}
                </td>
                <td role="cell" data-label={columns.satellite}>
                  {r.mdsa === null ? (
                    "–"
                  ) : (
                    <>
                      <span className="case-rivers__value">{oneDecimal(r.mdsa)} %</span>{" "}
                      <span className="case-rivers__muted">{gainText(r)}</span>
                    </>
                  )}
                </td>
                <td role="cell" data-label={columns.baseline}>
                  {r.nullMdsa === null ? "–" : `${oneDecimal(r.nullMdsa)} %`}
                  {r.noLocalMdsa == null ? null : (
                    <span className="case-rivers__muted">
                      {" "}
                      · {copy.otherMedian(oneDecimal(r.noLocalMdsa))}
                    </span>
                  )}
                </td>
                <td role="cell" data-label={columns.passes}>
                  {r.n}
                  {r.coverage90 === null ? null : (
                    <span className="case-rivers__muted">
                      {" "}
                      · {copy.inside(insideCount(r.coverage90, r.n))}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
