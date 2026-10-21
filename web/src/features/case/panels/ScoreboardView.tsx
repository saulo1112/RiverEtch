import { Anchor, CircleCheck, CircleDashed, CircleSlash, CircleX, History } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY, formatCelsius, formatDate, formatValue } from "../content.ts";
import {
  claimRows,
  lockboxHits,
  prospectiveHits,
  retrospectiveHits,
  type ClaimResult,
  type ClaimRow,
  type Hits,
} from "../scoreboard.ts";
import { HelpTip } from "./HelpTip.tsx";

const copy = CASE_COPY.scoreboard;

/** Props of {@link ScoreboardView}. */
export interface ScoreboardViewProps {
  readonly reach: ReachData;
  /** The prospective cut-off (ISO, UTC; null: the rule is not anchored yet). */
  readonly t0: string | null;
}

// Each result has its own shape and words; the colour only repeats them.
const RESULTS: Record<ClaimResult, { icon: LucideIcon; text: string }> = {
  inside: { icon: CircleCheck, text: copy.results.inside },
  outside: { icon: CircleX, text: copy.results.outside },
  pending: { icon: CircleDashed, text: copy.results.pending },
  none: { icon: CircleDashed, text: copy.results.none },
  abstained: { icon: CircleSlash, text: copy.results.abstained },
  noRange: { icon: CircleSlash, text: copy.results.noRange },
};

const TARGETS = [
  { id: "turbidity", name: copy.turbidity },
  { id: "water_temperature", name: copy.temperature },
] as const;

const format = (value: number, unit: string) =>
  unit === "°C" ? `${formatCelsius(value)} °C` : `${formatValue(value)} ${unit}`;

// "13 of 18 inside", or "none yet" before the first pass.
function Count({ hits }: { readonly hits: Hits }) {
  if (hits.n === 0) {
    return <span className="case-score__count case-score__muted">{copy.noneYet}</span>;
  }
  return (
    <span className="case-score__count">
      <strong>{copy.count(hits.inside, hits.n)}</strong> {copy.inside}
    </span>
  );
}

// A tile of counts, one row per target the reach has.
function Counts({
  title,
  note,
  rows,
}: {
  readonly title: string;
  readonly note: string;
  readonly rows: readonly { name: string; hits: Hits | null }[];
}) {
  return (
    <li className="case-score__tile">
      <p className="case-score__title">
        {title} <span className="case-score__muted">· {note}</span>
      </p>
      <dl className="case-score__rows">
        {rows.map((r) =>
          r.hits === null ? null : (
            <div key={r.name}>
              <dt>{r.name}</dt>
              <dd>
                <Count hits={r.hits} />
              </dd>
            </div>
          ),
        )}
      </dl>
    </li>
  );
}

// The prospective claims, latest first: the pass, the sealed estimate and range, the gauge's
// value with its approval, and the result in a shape and words.
function ClaimTable({ rows }: { readonly rows: readonly ClaimRow[] }) {
  const { columns } = copy;
  return (
    <table className="case-score__table">
      <caption className="case-visually-hidden">{copy.prospective}</caption>
      <thead>
        <tr>
          <th scope="col">{columns.pass}</th>
          <th scope="col">{columns.estimate}</th>
          <th scope="col">{columns.gauge}</th>
          <th scope="col">{columns.result}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const { icon: Icon, text } = RESULTS[r.result];
          const name = TARGETS.find((t) => t.id === r.target)?.name ?? r.target;
          const later = r.approved?.gauge ?? null;
          return (
            <tr key={r.claim}>
              <th scope="row">
                {formatDate(r.overpassUtc.slice(0, 10))}
                <span className="case-score__muted"> · {name}</span>
              </th>
              <td>
                <span className="case-score__nowrap">
                  {r.estimate === null ? "–" : format(r.estimate, r.unit)}
                </span>
                {r.interval === null ? null : (
                  <>
                    {" "}
                    <span className="case-score__muted case-score__nowrap">
                      ({formatValue(r.interval.low)}–{formatValue(r.interval.high)})
                    </span>
                  </>
                )}
              </td>
              <td>
                {r.gauge === null ? (
                  "–"
                ) : (
                  <>
                    <span className="case-score__nowrap">
                      {format(r.gauge.value, r.gauge.unit)}
                    </span>{" "}
                    <span
                      className="case-score__muted"
                      title={
                        r.gauge.approval === "Approved"
                          ? CASE_COPY.kinds.approvedHelp
                          : CASE_COPY.kinds.provisionalHelp
                      }
                    >
                      · {r.gauge.approval === "Approved" ? copy.approvedWord : copy.provisionalWord}
                    </span>
                  </>
                )}
                {later === null ? null : (
                  <span className="case-score__muted">
                    {" "}
                    {copy.approvedLater(format(later.value, later.unit))}
                  </span>
                )}
              </td>
              <td>
                <span className="case-score__result" data-result={r.result}>
                  <Icon size={14} strokeWidth={2} aria-hidden="true" />
                  {text}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/**
 * The track record: how many station values fell inside the sealed expected range, in counts.
 * First what was checked after the station's value was public (this year's passes and the locked
 * test), then the passes sealed and anchored before the station was read (after T0), with what
 * that wait means while there are none. Each group says which it is, in words and a mark.
 *
 * @returns The view.
 */
export function ScoreboardView({ reach, t0 }: ScoreboardViewProps) {
  const rows = claimRows(reach.outcomes);
  const retro = retrospectiveHits(reach, t0);
  const lock = lockboxHits(reach);
  const targets = TARGETS.filter((t) => t.id === "turbidity" || reach.thermal !== null);
  return (
    <div className="case-score">
      <section
        className="case-score__group"
        data-kind="retrospective"
        aria-label={copy.retrospective}
      >
        <p className="case-score__label">
          <History size={13} strokeWidth={1.9} aria-hidden="true" />
          <span>{copy.retrospective}</span>
          <HelpTip label={copy.retrospectiveHelpLabel}>{copy.retrospectiveHelp}</HelpTip>
        </p>
        <ul className="case-score__tiles">
          <Counts
            title={copy.passes2026}
            note={copy.passes2026Note}
            rows={[
              { name: copy.turbidity, hits: retro.turbidity },
              { name: copy.temperature, hits: retro.temperature },
            ]}
          />
          <Counts
            title={copy.lockbox}
            note={copy.lockboxNote}
            rows={[
              { name: copy.turbidity, hits: lock.turbidity },
              { name: copy.temperature, hits: lock.temperature },
            ]}
          />
        </ul>
      </section>
      <section className="case-score__group" data-kind="prospective" aria-label={copy.prospective}>
        <p className="case-score__label">
          <Anchor size={13} strokeWidth={1.9} aria-hidden="true" />
          <span>
            {copy.prospective}
            {t0 === null ? null : ` · ${copy.since(formatDate(t0.slice(0, 10), true))}`}
          </span>
          <HelpTip label={copy.prospectiveHelpLabel}>{copy.prospectiveHelp}</HelpTip>
        </p>
        {t0 === null || rows.length === 0 ? (
          <p className="case-score__empty" aria-live="polite">
            {t0 === null ? copy.notStarted : copy.empty(formatDate(t0.slice(0, 10), true))}
          </p>
        ) : (
          <div className="case-score__prospective">
            <dl className="case-score__rows case-score__rows--inline">
              {targets.map((t) => (
                <div key={t.id}>
                  <dt>{t.name}</dt>
                  <dd>
                    <Count hits={prospectiveHits(rows, t.id)} />
                  </dd>
                </div>
              ))}
            </dl>
            <ClaimTable rows={rows} />
          </div>
        )}
      </section>
    </div>
  );
}
