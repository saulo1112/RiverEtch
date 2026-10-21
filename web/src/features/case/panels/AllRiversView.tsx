import { CASE_COPY, LEVEL_LABELS } from "../content.ts";
import { gainOver, insideCount } from "../reading.ts";
import { DEMO_GAUGES, medianError, oneDecimal, type RiverResult } from "../rivers.ts";
import { HelpTip } from "./HelpTip.tsx";

const copy = CASE_COPY.rivers;

/** Which test the Accuracy tab shows, by the kind of case. */
export type AccuracyKind = "gauged" | "ungauged" | "outside";

/** Props of {@link AllRiversView}. */
export interface AllRiversViewProps {
  /** Every evaluated river's locked test, lowest error first ({@link riverResults}). */
  readonly rivers: readonly RiverResult[];
  /** The same rivers, each scored by a model that never saw it ({@link transferResults}). */
  readonly transfer?: readonly RiverResult[];
  /** The case's own gauge, e.g. "USGS-06805500". */
  readonly station: string;
  /**
   * A case with a station shows each river's own locked test; a case with none, the test on
   * rivers the model never saw (its expected error); one outside the tested region says that none
   * of those errors applies to it.
   */
  readonly kind?: AccuracyKind;
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

function Row({ r, station }: { readonly r: RiverResult; readonly station: string }) {
  const { columns } = copy;
  const demo = DEMO_GAUGES.includes(r.site);
  const mark = r.site === station ? copy.thisCase : demo ? copy.demo : null;
  return (
    <tr role="row" data-demo={demo || undefined} data-here={r.site === station || undefined}>
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
}

// A group of rows under its own heading row (the heading spans the table).
function Group({
  title,
  note,
  rows,
  station,
}: {
  readonly title: string;
  readonly note?: string;
  readonly rows: readonly RiverResult[];
  readonly station: string;
}) {
  if (rows.length === 0) {
    return null;
  }
  return (
    <tbody role="rowgroup">
      <tr role="row" className="case-rivers__group">
        <th role="columnheader" scope="colgroup" colSpan={5}>
          {title}
          {note === undefined ? null : <span className="case-rivers__muted"> · {note}</span>}
        </th>
      </tr>
      {rows.map((r) => (
        <Row key={r.site} r={r} station={station} />
      ))}
    </tbody>
  );
}

/**
 * The Accuracy tab: where the satellite works and where it does not, from the committed tests. A
 * case with a station shows every station's own locked test; a case with none shows the same
 * stations scored by a model that never saw each river (the error to expect without a station).
 * A summary comes first, then the stations where the satellite passed, then those where it is not
 * recommended (it did not beat guessing the usual value, so no number is shown there), then any
 * with too few test passes to judge. The demo reaches are marked.
 *
 * @returns The tab.
 */
export function AllRiversView({
  rivers,
  transfer = [],
  station,
  kind = "gauged",
}: AllRiversViewProps) {
  const { columns } = copy;
  const never = kind !== "gauged" && transfer.length > 0;
  const shown = never ? transfer : rivers;
  const rated = shown.filter((r) => r.level !== null);
  const works = rated.filter((r) => r.level !== "none");
  const not = rated.filter((r) => r.level === "none");
  const thin = shown.filter((r) => r.level === null);
  return (
    <div className="case-rivers">
      <p className="case-rivers__summary" data-tour="accuracy">
        {never
          ? copy.summaryNever(works.length, rated.length)
          : copy.summary(works.length, rated.length, oneDecimal(medianError(rated)))}
        {kind === "outside" ? ` ${copy.outside}` : ""}
      </p>
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
        <Group title={copy.works(works.length)} rows={works} station={station} />
        <Group
          title={copy.notRecommended(not.length)}
          note={never ? copy.notNoteNever : copy.notNote}
          rows={not}
          station={station}
        />
        <Group title={copy.thin} rows={thin} station={station} />
      </table>
    </div>
  );
}
