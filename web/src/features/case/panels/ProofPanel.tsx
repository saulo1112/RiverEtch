import { Anchor, Check, Clock, Download, ExternalLink, FileSearch, X } from "lucide-react";
import { useId, useRef, useState } from "react";

import { explorerUrl } from "../../chain/config.ts";
import { useLedgerAnchor, type AnchorOutcome } from "../../chain/useLedgerAnchor.ts";
import { useProofIo } from "../../chain/useProofIo.ts";
import { checkProofFile, type FileReport, type RowIssue } from "../../reaches/proofcheck.ts";
import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY, formatDate } from "../content.ts";
import { HelpTip } from "./HelpTip.tsx";

/** Props of {@link ProofPanel}. */
export interface ProofPanelProps {
  readonly reach: ReachData;
  /** Opens "Export with proof". */
  readonly onExport: () => void;
}

// The owner's action: post the reach's record lists on Ethereum in one transaction.
function AnchorAction({ run }: { readonly run: () => Promise<AnchorOutcome> }) {
  const { record: copy } = CASE_COPY;
  const [state, setState] = useState<
    | { readonly step: "idle" | "running" | "failed" }
    | { readonly step: "finished"; readonly outcome: AnchorOutcome }
  >({ step: "idle" });
  return (
    <div className="case-record__anchor">
      <button
        type="button"
        className="case-btn case-btn--ghost case-record__anchor-button"
        disabled={state.step === "running"}
        onClick={() => {
          setState({ step: "running" });
          run()
            .then((outcome) => {
              setState({ step: "finished", outcome });
            })
            .catch(() => {
              setState({ step: "failed" });
            });
        }}
      >
        <Anchor size={14} strokeWidth={1.9} aria-hidden="true" />
        {state.step === "running" ? copy.anchoring : copy.anchorAction}
      </button>
      <p className="case-record__anchor-note" aria-live="polite">
        {state.step === "failed" ? copy.anchorFailed : null}
        {state.step === "finished" && state.outcome.state === "upToDate" ? copy.upToDate : null}
        {state.step === "finished" && state.outcome.state === "done" ? (
          <a href={explorerUrl("tx", state.outcome.hash)} target="_blank" rel="noopener noreferrer">
            {copy.anchoredTx(state.outcome.ledgers)}
          </a>
        ) : null}
      </p>
    </div>
  );
}

/**
 * The whole file's verdict in one sentence: rows checked, each board counted apart, then what
 * changed, was not found or is missing.
 *
 * @param report - The check.
 * @returns The sentence.
 */
function verdict(report: FileReport): string {
  const copy = CASE_COPY.proof;
  const parts = [
    copy.rows(report.rows),
    ...(report.ethereum === null || report.waiting === null
      ? [copy.offline]
      : [copy.ethereum(report.ethereum)]),
    copy.bitcoin(report.bitcoin),
    ...(report.waiting === null ? [] : [copy.waiting(report.waiting)]),
    copy.changed(report.changed.length),
    copy.notFound(report.notFound.length),
    ...(report.missing.length > 0 ? [copy.missing(report.missing.length)] : []),
  ];
  return parts.join(" · ");
}

const LIST = 6;

// A list of rows with what is wrong with each, the first few.
function Issues({
  title,
  issues,
}: {
  readonly title: string;
  readonly issues: readonly RowIssue[];
}) {
  const copy = CASE_COPY.proof;
  if (issues.length === 0) {
    return null;
  }
  return (
    <div className="case-report__issues">
      <p className="case-report__title">{title}</p>
      <ul className="case-report__list">
        {issues.slice(0, LIST).map((issue) => (
          <li key={`${issue.reach}-${issue.dataset}-${issue.sceneId}-${String(issue.row)}`}>
            {issue.row > 0
              ? copy.row(issue.row, issue.date === "" ? "" : formatDate(issue.date, true))
              : copy.missingRow(formatDate(issue.date, true), issue.reach)}
            {issue.changes.length === 0 ? null : (
              <ul>
                {issue.changes.map((c) => (
                  <li key={c.column}>
                    {c.column.startsWith("(")
                      ? copy.whole
                      : copy.change(c.column, c.sealed, c.given)}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
        {issues.length > LIST ? <li>{copy.more(issues.length - LIST)}</li> : null}
      </ul>
    </div>
  );
}

// The report over a whole file, its verdict first, by mark and words (never colour alone): a
// tick only when nothing is wrong and Ethereum was read.
function Report({ report }: { readonly report: FileReport }) {
  const copy = CASE_COPY.proof;
  const wrong = report.changed.length + report.notFound.length + report.missing.length > 0;
  const offline = report.ethereum === null;
  const state = wrong ? "false" : offline ? "pending" : "true";
  return (
    <div className="case-report">
      <p className="case-report__verdict" data-ok={state}>
        {wrong ? (
          <X size={14} strokeWidth={2.25} aria-hidden="true" />
        ) : offline ? (
          <Clock size={14} strokeWidth={2.25} aria-hidden="true" />
        ) : (
          <Check size={14} strokeWidth={2.25} aria-hidden="true" />
        )}
        <span>{verdict(report)}</span>
      </p>
      {report.signed > 0 ? <p className="case-report__note">{copy.signed(report.signed)}</p> : null}
      <Issues title={copy.changedTitle} issues={report.changed} />
      <Issues title={copy.notFoundTitle} issues={report.notFound} />
      <Issues title={copy.missingTitle} issues={report.missing} />
      {report.notes.map((note) => (
        <p key={note} className="case-report__note" data-warn="true">
          {note}
        </p>
      ))}
      {report.manifestSha256 === null ? null : (
        <p className="case-report__note case-report__hash">
          {copy.manifest(report.manifestSha256)}
        </p>
      )}
      <p className="case-report__note">{CASE_COPY.record.boards}</p>
    </div>
  );
}

/**
 * Right panel: the proof, in two plain actions. "Export with proof" takes the readings out with
 * what proves they have not changed since they were fixed; "Check a file" checks a RiverEtch file
 * someone sent (an export, a table or one record) against the site, in the browser, and reports on
 * the whole file. For the contract's owner only, the action that posts the record lists.
 *
 * @param props - The reach, and the export's opener.
 * @param props.reach - The reach.
 * @param props.onExport - Opens "Export with proof".
 * @returns The panel.
 */
export function ProofPanel({ reach, onExport }: ProofPanelProps) {
  const copy = CASE_COPY.proof;
  const { record } = CASE_COPY;
  const io = useProofIo();
  const anchor = useLedgerAnchor(reach);
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const [state, setState] = useState<
    | { readonly step: "idle" | "running" | "failed" }
    | { readonly step: "done"; readonly report: FileReport | null }
  >({ step: "idle" });
  return (
    <section
      className="case-panel case-record case-glass"
      data-frame=""
      data-tour="proof"
      aria-labelledby="case-proof-title"
    >
      <header className="case-head">
        <div className="case-head__text">
          <div className="case-record__title">
            <h2 className="case-head__title" id="case-proof-title">
              {record.title}
            </h2>
            <HelpTip label={copy.whyLabel}>{copy.why}</HelpTip>
          </div>
        </div>
      </header>
      <div className="case-action">
        <button
          type="button"
          className="case-btn case-btn--solid case-action__btn"
          onClick={onExport}
        >
          <Download size={15} strokeWidth={1.9} aria-hidden="true" />
          {copy.export}
        </button>
        <p className="case-action__purpose">{copy.exportPurpose}</p>
      </div>
      <div className="case-action">
        <button
          type="button"
          className="case-btn case-btn--ghost case-action__btn"
          aria-describedby={hintId}
          disabled={state.step === "running"}
          onClick={() => inputRef.current?.click()}
        >
          <FileSearch size={15} strokeWidth={1.9} aria-hidden="true" />
          {state.step === "running" ? copy.checking : copy.check}
        </button>
        <p className="case-action__purpose" id={hintId}>
          {copy.checkPurpose}
        </p>
        <input
          ref={inputRef}
          className="case-visually-hidden"
          type="file"
          tabIndex={-1}
          aria-hidden="true"
          accept=".zip,.csv,.json,application/zip,application/json,text/csv"
          onChange={(event) => {
            const picked = event.target.files?.[0];
            event.target.value = "";
            if (picked === undefined) {
              return;
            }
            setState({ step: "running" });
            picked
              .arrayBuffer()
              .then((buffer) => checkProofFile(new Uint8Array(buffer), io))
              .then((report) => {
                setState({ step: "done", report });
              })
              .catch(() => {
                setState({ step: "failed" });
              });
          }}
        />
      </div>
      <p className="case-record__hint">{copy.accepts}</p>
      <div className="case-verify" aria-live="polite">
        {state.step === "failed" ? <p className="case-verify__note">{copy.failed}</p> : null}
        {state.step === "done" && state.report === null ? (
          <p className="case-verify__note">{copy.unreadable}</p>
        ) : null}
        {state.step === "done" && state.report !== null ? <Report report={state.report} /> : null}
      </div>
      {anchor.address === null ? null : (
        <p className="case-record__hint">
          {record.anchoredHint}{" "}
          <a
            href={explorerUrl("address", anchor.address)}
            target="_blank"
            rel="noopener noreferrer"
          >
            {record.contract}
            <ExternalLink size={11} strokeWidth={1.75} aria-hidden="true" />
          </a>
        </p>
      )}
      {anchor.isOwner ? <AnchorAction run={anchor.anchorReach} /> : null}
    </section>
  );
}
