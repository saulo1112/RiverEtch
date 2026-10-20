import { ArrowUpRight, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";

import { explorerUrl } from "../../chain/config.ts";
import { REACH_CASES } from "../../reaches/catalog.ts";
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

// A reach's title as the cases name it ("Mississippi · Belle Chasse"), else its id.
const placeOf = (reach: string) => REACH_CASES.find((c) => c.id === reach)?.title ?? reach;

/**
 * The live record, from the daily run's `status.json` (data branch): when it last updated, its
 * newest sealed reading, and the latest proofs on Ethereum and Bitcoin, each a link. When the
 * status cannot be read, it says the page shows the readings bundled with this build. A native
 * modal dialog.
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
          <p className="hero-status__note">{copy.snapshot}</p>
        ) : (
          <dl className="hero-status__list">
            <dt>{copy.lastUpdate}</dt>
            <dd>{status.lastSuccessUtc === null ? copy.notYet : utc(status.lastSuccessUtc)}</dd>
            <dt>{copy.newest}</dt>
            <dd>
              {status.lastSealed === null
                ? copy.notYet
                : copy.newestValue(placeOf(status.lastSealed.reach), status.lastSealed.date)}
            </dd>
            <dt>{copy.ethereum}</dt>
            <dd>
              {status.lastAnchor === null ? (
                copy.notYet
              ) : (
                <>
                  {utc(status.lastAnchor.timestampUtc)}{" "}
                  <External href={explorerUrl("tx", status.lastAnchor.tx)}>
                    {copy.block(status.lastAnchor.block)}
                  </External>
                </>
              )}
            </dd>
            <dt>{copy.bitcoin}</dt>
            <dd>
              {status.lastBitcoin === null ? (
                copy.notYet
              ) : (
                <External href={`https://mempool.space/block/${String(status.lastBitcoin.height)}`}>
                  {copy.bitcoinBlock(
                    status.lastBitcoin.height,
                    status.lastBitcoin.blockTime === null
                      ? null
                      : utc(status.lastBitcoin.blockTime),
                  )}
                </External>
              )}
            </dd>
          </dl>
        )}
      </div>
    </dialog>
  );
}
