import { Check, Clock, Link2, Unlink, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { explorerUrl } from "../../chain/config.ts";
import type { ChainCheck } from "../../chain/useLedgerAnchor.ts";
import type { Verification } from "../../reaches/verify.ts";
import { CASE_COPY, formatDate } from "../content.ts";

/** Props of {@link VerifyDialog}. */
export interface VerifyDialogProps {
  /** The check to show (null: closed). */
  readonly result: Verification | null;
  /** The record's anchor on Sepolia (null: no anchor contract configured). */
  readonly chain?: ChainCheck | null;
  /** The dialog closed. */
  readonly onClose: () => void;
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
  const at = text.indexOf(`"${key}":${result.altered.to}`);
  if (at < 0) {
    return { before: text.slice(0, 260), mark: "", after: "…" };
  }
  const start = Math.max(0, at - 120);
  const markStart = at + key.length + 3;
  return {
    before: `${start > 0 ? "…" : ""}${text.slice(start, markStart)}`,
    mark: result.altered.to,
    after: `${text.slice(markStart + result.altered.to.length, markStart + 140)}…`,
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
  if (chain.state === "anchored") {
    const day = new Date(chain.anchor.timestamp * 1000).toISOString().slice(0, 10);
    return (
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
    );
  }
  if (chain.state === "mismatch") {
    return (
      <p className="case-proof__line" data-ok="false">
        <X size={14} strokeWidth={2.25} aria-hidden="true" />
        {copy.chainMismatch}
      </p>
    );
  }
  return (
    <p className="case-proof__line" data-ok="pending">
      <Clock size={14} strokeWidth={2.25} aria-hidden="true" />
      {chain.state === "pending" ? copy.chainPending : copy.chainUnavailable}
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
export function VerifyDialog({ result, chain = null, onClose }: VerifyDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [shown, setShown] = useState(0);
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
    if (result === null) {
      return undefined;
    }
    // The steps appear one after the other.
    let step = 0;
    const timer = window.setInterval(() => {
      step += 1;
      setShown(step);
      if (step >= 6) {
        window.clearInterval(timer);
      }
    }, 650);
    return () => {
      window.clearInterval(timer);
      setShown(0);
    };
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
              {verify.title}
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
          <ol className="case-proof__steps">
            <li className="case-proof__step" data-shown={shown >= 1}>
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
            <li className="case-proof__step" data-shown={shown >= 2}>
              <p className="case-proof__step-title">
                <span>2</span> {verify.step2}
              </p>
              <HashLine label={verify.stated} hash={result.stated} />
              <HashLine label={verify.computed} hash={result.computed} against={result.stated} />
            </li>
            <li className="case-proof__step" data-shown={shown >= 3}>
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
                      <span className="case-proof__block-date">{formatDate(link.date, true)}</span>
                      <code>{link.lineSha256.slice(0, 10)}…</code>
                    </li>
                  );
                })}
              </ol>
            </li>
            <li className="case-proof__step" data-shown={shown >= 4}>
              <p className="case-proof__step-title">
                <span>4</span> {verify.step4}
              </p>
              <p className="case-proof__line" data-ok={result.cardMatches !== false}>
                {result.cardMatches !== false ? (
                  <Check size={14} strokeWidth={2.25} aria-hidden="true" />
                ) : (
                  <X size={14} strokeWidth={2.25} aria-hidden="true" />
                )}
                {result.cardMatches !== false ? CASE_COPY.record.cardOk : CASE_COPY.record.cardBad}
              </p>
            </li>
            {chain === null ? null : (
              <li className="case-proof__step" data-shown={shown >= 5}>
                <p className="case-proof__step-title">
                  <span>5</span> {verify.step5}
                </p>
                <p className="case-proof__note">{verify.step5Note}</p>
                <ChainLine chain={chain} />
              </li>
            )}
          </ol>
          <p
            className="case-proof__verdict"
            data-shown={shown >= (chain === null ? 5 : 6)}
            data-ok={result.sealed}
          >
            {result.sealed ? verify.verified : verify.tampered}
          </p>
        </div>
      )}
    </dialog>
  );
}
