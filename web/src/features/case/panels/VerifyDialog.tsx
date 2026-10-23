import { Check, Clock, Download, Link2, Unlink, X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";

import { explorerUrl } from "../../chain/config.ts";
import type { ChainCheck } from "../../chain/useLedgerAnchor.ts";
import type { BitcoinWitness, SignatureWitness } from "../../chain/witness.ts";
import type { Verification } from "../../reaches/verify.ts";
import { CASE_COPY, formatDate } from "../content.ts";

/** Props of {@link VerifyDialog}. */
export interface VerifyDialogProps {
  /** The check to show (null: closed). */
  readonly result: Verification | null;
  /** The record's anchor on Sepolia (null: no anchor contract configured). */
  readonly chain?: ChainCheck | null;
  /** A Bitcoin timestamp of a head covering it (null: not checked). */
  readonly bitcoin?: BitcoinWitness | null;
  /** The ML-DSA-65 signature of a head covering it (null: not checked). */
  readonly signature?: SignatureWitness | null;
  /** The day the reading was fixed (its line of the record list; null: unknown). */
  readonly fixedOn?: string | null;
  /** The record's details, under the steps. */
  readonly details?: readonly RecordDetail[];
  /** The record file, to download (null: none). */
  readonly download?: string | null;
  /** The dialog's title (default: checking the reading). */
  readonly title?: string;
  /** The dialog closed. */
  readonly onClose: () => void;
}

/** One line of a record's details: what, and its value. */
export interface RecordDetail {
  readonly label: string;
  readonly value: ReactNode;
}

// The verdict's mark: changed, unchanged and posted on Ethereum, or unchanged but not (yet, or
// not read) on Ethereum, which never shows as a pass.
function verdictState(
  result: Verification,
  chain: ChainCheck | null,
): "true" | "false" | "pending" {
  if (!result.sealed || !result.inLedger || !result.chainIntact || chain?.state === "mismatch") {
    return "false";
  }
  return chain?.state === "anchored" ? "true" : "pending";
}

// The verdict in one sentence: unchanged since when, and on which boards.
function verdictOf(
  result: Verification,
  chain: ChainCheck | null,
  bitcoin: BitcoinWitness | null,
  fixedOn: string | null,
): string {
  const { verify } = CASE_COPY;
  if (!result.sealed || !result.inLedger || !result.chainIntact) {
    return verify.changed;
  }
  const same = fixedOn === null ? verify.verified : verify.same(formatDate(fixedOn, true));
  const boards =
    chain === null || chain.state === "unavailable"
      ? verify.boardsOffline
      : chain.state === "mismatch"
        ? verify.boardsMismatch
        : chain.state === "pending"
          ? verify.boardsPending
          : bitcoin?.state === "confirmed"
            ? verify.boardsBoth
            : verify.boardsEthereum;
  return `${same} ${boards}`;
}

// The canonical text around the altered value (or its start), with the value marked.
function excerpt(result: Verification): { before: string; mark: string; after: string } {
  const text = result.canonical;
  if (result.altered === null) {
    return { before: text.slice(0, 260), mark: "", after: text.length > 260 ? "…" : "" };
  }
  const key =
    result.altered.path
      .split(".")
      .at(-1)
      ?.replace(/\[\d+\]/, "") ?? "";
  // A class is a JSON string: its quotes are part of what changed.
  const to =
    result.altered.kind === "class" ? JSON.stringify(result.altered.to) : result.altered.to;
  const at = text.indexOf(`"${key}":${to}`);
  if (at < 0) {
    return { before: text.slice(0, 260), mark: "", after: "…" };
  }
  const start = Math.max(0, at - 120);
  const markStart = at + key.length + 3;
  return {
    before: `${start > 0 ? "…" : ""}${text.slice(start, markStart)}`,
    mark: to,
    after: `${text.slice(markStart + to.length, markStart + 140)}…`,
  };
}

function HashLine({ label, hash, against }: { label: string; hash: string; against?: string }) {
  return (
    <p className="case-proof__hash">
      <span className="case-proof__hash-label">{label}</span>
      <code>
        {Array.from(hash, (c, k) => (
          <span key={k} data-diff={against !== undefined && against[k] !== c}>
            {c}
          </span>
        ))}
      </code>
    </p>
  );
}

// The anchor's line: anchored (with its block), pending, changed since, or unreadable.
function ChainLine({ chain }: { readonly chain: ChainCheck }) {
  const copy = CASE_COPY.record;
  const via =
    chain.state === "unavailable" ? null : (
      <p className="case-proof__note">{chain.via === "wallet" ? copy.viaWallet : copy.viaPublic}</p>
    );
  if (chain.state === "anchored") {
    const day = new Date(chain.anchor.timestamp * 1000).toISOString().slice(0, 10);
    return (
      <>
        <p className="case-proof__line" data-ok="true">
          <Check size={14} strokeWidth={2.25} aria-hidden="true" />
          <a
            href={explorerUrl("block", chain.anchor.blockNumber)}
            target="_blank"
            rel="noopener noreferrer"
          >
            {copy.chainAnchored(formatDate(day, true), chain.anchor.blockNumber)}
          </a>
        </p>
        {via}
      </>
    );
  }
  if (chain.state === "mismatch") {
    return (
      <>
        <p className="case-proof__line" data-ok="false">
          <X size={14} strokeWidth={2.25} aria-hidden="true" />
          {copy.chainMismatch}
        </p>
        {via}
      </>
    );
  }
  return (
    <p className="case-proof__line" data-ok="pending">
      <Clock size={14} strokeWidth={2.25} aria-hidden="true" />
      {chain.state === "pending" ? copy.chainPending : copy.chainUnavailable}
    </p>
  );
}

// The Bitcoin witness's line: confirmed (with its block), pending, none yet, or a failure.
function BitcoinLine({ witness }: { readonly witness: BitcoinWitness }) {
  const { verify } = CASE_COPY;
  if (witness.state === "confirmed") {
    const day = new Date(witness.time * 1000).toISOString().slice(0, 10);
    return (
      <p className="case-proof__line" data-ok="true">
        <Check size={14} strokeWidth={2.25} aria-hidden="true" />
        <a
          href={`https://mempool.space/block/${String(witness.height)}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          {verify.bitcoinConfirmed(formatDate(day, true), witness.height, witness.lines)}
        </a>
      </p>
    );
  }
  if (witness.state === "mismatch") {
    return (
      <p className="case-proof__line" data-ok="false">
        <X size={14} strokeWidth={2.25} aria-hidden="true" />
        {verify.bitcoinMismatch}
      </p>
    );
  }
  return (
    <p className="case-proof__line" data-ok="pending">
      <Clock size={14} strokeWidth={2.25} aria-hidden="true" />
      {witness.state === "pending"
        ? verify.bitcoinPending(witness.lines)
        : witness.state === "none"
          ? verify.bitcoinNone
          : verify.bitcoinUnavailable}
    </p>
  );
}

// The signature's line: verified (with its date), none yet, invalid, or unreadable.
function SignatureLine({ witness }: { readonly witness: SignatureWitness }) {
  const { verify } = CASE_COPY;
  if (witness.state === "verified") {
    return (
      <p className="case-proof__line" data-ok="true">
        <Check size={14} strokeWidth={2.25} aria-hidden="true" />
        {verify.signatureVerified(formatDate(witness.signedAt.slice(0, 10), true), witness.lines)}
      </p>
    );
  }
  if (witness.state === "invalid") {
    return (
      <p className="case-proof__line" data-ok="false">
        <X size={14} strokeWidth={2.25} aria-hidden="true" />
        {verify.signatureInvalid}
      </p>
    );
  }
  return (
    <p className="case-proof__line" data-ok="pending">
      <Clock size={14} strokeWidth={2.25} aria-hidden="true" />
      {witness.state === "none" ? verify.signatureNone : verify.signatureUnavailable}
    </p>
  );
}

/**
 * "Verifying the record", step by step: the record's canonical content (an altered value marked),
 * the SHA-256 recomputed beside the sealed one, the record's place in the hash-chained ledger and
 * its model card. Each step appears in turn; a native modal dialog.
 *
 * @returns The dialog element (closed while `result` is null).
 */
export function VerifyDialog({
  result,
  chain = null,
  bitcoin = null,
  signature = null,
  fixedOn = null,
  details = [],
  download = null,
  title,
  onClose,
}: VerifyDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const { verify } = CASE_COPY;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) {
      return undefined;
    }
    if (result !== null && !dialog.open) {
      dialog.showModal();
    } else if (result === null && dialog.open) {
      dialog.close();
    }
    return undefined;
  }, [result]);

  const parts = result === null ? null : excerpt(result);
  const around =
    result === null || result.position < 0
      ? []
      : result.ledger.slice(Math.max(0, result.position - 2), result.position + 3);
  const first = result === null ? 0 : Math.max(0, result.position - 2);
  return (
    <dialog
      ref={dialogRef}
      className="case-proof"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          event.currentTarget.close();
        }
      }}
    >
      {result === null || parts === null ? null : (
        <div className="case-proof__body" data-sealed={result.sealed}>
          <div className="case-proof__head">
            <h2 className="case-proof__title" id={titleId}>
              {title ?? verify.title}
            </h2>
            <button
              type="button"
              className="case-proof__close"
              aria-label={verify.close}
              onClick={() => dialogRef.current?.close()}
            >
              <X size={18} strokeWidth={1.75} aria-hidden="true" />
            </button>
          </div>
          <p
            className="case-proof__verdict case-proof__verdict--first"
            data-ok={verdictState(result, chain)}
            role="status"
          >
            {verdictOf(result, chain, bitcoin, fixedOn)}
          </p>
          <p className="case-proof__note">{CASE_COPY.record.boards}</p>
          <details className="case-proof__more">
            <summary>{verify.showSteps}</summary>
            <ol className="case-proof__steps">
              <li className="case-proof__step" data-shown="true">
                <p className="case-proof__step-title">
                  <span>1</span> {verify.step1}
                </p>
                <p className="case-proof__note">{verify.step1Note}</p>
                <pre className="case-proof__json">
                  {parts.before}
                  {parts.mark === "" ? null : <mark>{parts.mark}</mark>}
                  {parts.after}
                </pre>
              </li>
              <li className="case-proof__step" data-shown="true">
                <p className="case-proof__step-title">
                  <span>2</span> {verify.step2}
                </p>
                <HashLine label={verify.stated} hash={result.stated} />
                <HashLine label={verify.computed} hash={result.computed} against={result.stated} />
              </li>
              <li className="case-proof__step" data-shown="true">
                <p className="case-proof__step-title">
                  <span>3</span> {verify.step3}
                </p>
                <p className="case-proof__note">{verify.step3Note}</p>
                <ol className="case-proof__chain">
                  {around.map((link, k) => {
                    const index = first + k;
                    const mine = index === result.position;
                    return (
                      <li
                        key={link.lineSha256}
                        className="case-proof__block"
                        data-mine={mine}
                        data-broken={mine && !result.sealed}
                      >
                        {k === 0 ? null : (
                          <span className="case-proof__link" aria-hidden="true">
                            {result.chainIntact ? (
                              <Link2 size={14} strokeWidth={1.9} />
                            ) : (
                              <Unlink size={14} strokeWidth={1.9} />
                            )}
                          </span>
                        )}
                        <span className="case-proof__block-index">#{String(index + 1)}</span>
                        <span className="case-proof__block-date">
                          {formatDate(link.date, true)}
                        </span>
                        <code>{link.lineSha256.slice(0, 10)}…</code>
                      </li>
                    );
                  })}
                </ol>
              </li>
              <li className="case-proof__step" data-shown="true">
                <p className="case-proof__step-title">
                  <span>4</span> {verify.step4}
                </p>
                <p className="case-proof__line" data-ok={result.cardMatches !== false}>
                  {result.cardMatches !== false ? (
                    <Check size={14} strokeWidth={2.25} aria-hidden="true" />
                  ) : (
                    <X size={14} strokeWidth={2.25} aria-hidden="true" />
                  )}
                  {result.cardMatches !== false
                    ? CASE_COPY.record.cardOk
                    : CASE_COPY.record.cardBad}
                </p>
              </li>
              {chain === null ? null : (
                <li className="case-proof__step" data-shown="true">
                  <p className="case-proof__step-title">
                    <span>5</span> {verify.step5}
                  </p>
                  <p className="case-proof__note">{verify.step5Note}</p>
                  <ChainLine chain={chain} />
                </li>
              )}
              {bitcoin === null ? null : (
                <li className="case-proof__step" data-shown="true">
                  <p className="case-proof__step-title">
                    <span>{chain === null ? 5 : 6}</span> {verify.step6}
                  </p>
                  <p className="case-proof__note">{verify.step6Note}</p>
                  <BitcoinLine witness={bitcoin} />
                </li>
              )}
              {signature === null ? null : (
                <li className="case-proof__step" data-shown="true">
                  <p className="case-proof__step-title">
                    <span>{4 + [chain, bitcoin, signature].filter((w) => w !== null).length}</span>{" "}
                    {verify.step7}
                  </p>
                  <p className="case-proof__note">{verify.step7Note}</p>
                  <SignatureLine witness={signature} />
                </li>
              )}
            </ol>
            {details.length === 0 ? null : (
              <dl className="case-record__rows">
                {details.map((r) => (
                  <div className="case-record__row" key={r.label}>
                    <dt>{r.label}</dt>
                    <dd>{r.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {download === null ? null : (
              <a className="case-record__download" href={download} download>
                <Download size={13} strokeWidth={1.75} aria-hidden="true" />
                {CASE_COPY.record.download}
              </a>
            )}
          </details>
        </div>
      )}
    </dialog>
  );
}
