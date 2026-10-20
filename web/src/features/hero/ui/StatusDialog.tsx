import { ArrowUpRight, Check, Clock, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";

import { explorerUrl } from "../../chain/config.ts";
import type { RunStatus } from "../../reaches/data.ts";
import { RUN_STATUS as copy } from "./content.ts";

/** Props of {@link StatusDialog}. */
export interface StatusDialogProps {
  /** Open or closed. */
  readonly open: boolean;
  /** The daily run's status (null: it could not be read). */
  readonly status: RunStatus | null;
  /** The dialog closed. */
  readonly onClose: () => void;
}

// "20 Oct 2026, 13:05 UTC" from an ISO time.
function utc(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  const day = new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
  return `${day}, ${date.toISOString().slice(11, 16)} UTC`;
}

function External({ href, children }: { readonly href: string; readonly children: string }) {
  return (
    <a className="hero-status__link" href={href} target="_blank" rel="noopener noreferrer">
      {children}
      <ArrowUpRight size={12} strokeWidth={1.75} aria-hidden="true" />
      <span className="hero-ui__visually-hidden"> {copy.externalHint}</span>
    </a>
  );
}

/**
 * The daily run's status, as it publishes it (`status.json` on the data branch): its last run and
 * last success, the newest sealed record, the last anchor on Sepolia, the Bitcoin timestamps and
 * the recent failures with their reasons. Each state has a mark and words, never colour alone; a
 * native modal dialog.
 *
 * @returns The dialog element.
 */
export function StatusDialog({ open, status, onClose }: StatusDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) {
      return;
    }
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);
  const Mark = status === null ? Clock : status.run.ok ? Check : X;
  return (
    <dialog
      ref={ref}
      className="hero-status"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          event.currentTarget.close();
        }
      }}
    >
      <div className="hero-status__body">
        <div className="hero-status__head">
          <h2 className="hero-status__title" id={titleId}>
            {copy.title}
          </h2>
          <button
            type="button"
            className="hero-status__close"
            aria-label={copy.close}
            onClick={() => ref.current?.close()}
          >
            <X size={18} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>
        <p className="hero-status__note">{copy.lead}</p>
        {status === null ? (
          <p className="hero-status__line" data-ok="pending">
            <Clock size={14} strokeWidth={2.25} aria-hidden="true" />
            {copy.unavailable}
          </p>
        ) : (
          <dl className="hero-status__list">
            <dt>{copy.lastRun}</dt>
            <dd>
              <span className="hero-status__line" data-ok={status.run.ok ? "true" : "false"}>
                <Mark size={14} strokeWidth={2.25} aria-hidden="true" />
                {status.run.ok ? copy.ok : copy.failed} · {utc(status.updatedUtc)}
              </span>{" "}
              {status.run.url === "" ? null : <External href={status.run.url}>{copy.log}</External>}
            </dd>
            <dt>{copy.lastSuccess}</dt>
            <dd>{status.lastSuccessUtc === null ? copy.none : utc(status.lastSuccessUtc)}</dd>
            <dt>{copy.lastSealed}</dt>
            <dd>
              {status.lastSealed === null
                ? copy.none
                : copy.sealed(status.lastSealed.reach, status.lastSealed.date)}
            </dd>
            <dt>{copy.lastAnchor}</dt>
            <dd>
              {status.lastAnchor === null ? (
                copy.none
              ) : (
                <>
                  {copy.anchor(
                    status.lastAnchor.label,
                    status.lastAnchor.lines,
                    utc(status.lastAnchor.timestampUtc),
                  )}{" "}
                  <External href={explorerUrl("tx", status.lastAnchor.tx)}>
                    {copy.block(status.lastAnchor.block)}
                  </External>
                </>
              )}
            </dd>
            <dt>{copy.bitcoin}</dt>
            <dd>
              {status.lastBitcoin === null ? (
                copy.noBitcoin
              ) : (
                <External href={`https://mempool.space/block/${String(status.lastBitcoin.height)}`}>
                  {copy.bitcoinBlock(
                    status.lastBitcoin.height,
                    status.lastBitcoin.blockTime === null
                      ? null
                      : utc(status.lastBitcoin.blockTime),
                  )}
                </External>
              )}{" "}
              · {copy.pending(status.pendingBitcoin)}
            </dd>
            <dt>{copy.failures}</dt>
            <dd>
              {status.failures.length === 0 ? (
                copy.none
              ) : (
                <ul className="hero-status__failures">
                  {status.failures
                    .slice(-5)
                    .reverse()
                    .map((f) => (
                      <li key={`${f.utc}|${f.step}`}>
                        <strong>{utc(f.utc)}</strong> · <code>{f.step}</code> · {f.reason}
                      </li>
                    ))}
                </ul>
              )}
            </dd>
          </dl>
        )}
      </div>
    </dialog>
  );
}
