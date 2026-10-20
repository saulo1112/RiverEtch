import { ArrowUpRight } from "lucide-react";
import { useEffect, useState } from "react";

import { explorerUrl, LEDGER_ANCHOR_ADDRESS } from "../../chain/config.ts";
import { REACH_CASES } from "../../reaches/catalog.ts";
import { loadStatus, type RunStatus } from "../../reaches/data.ts";
import { ATTRIBUTION, EVIDENCE, RUN_STATUS, STATUS } from "./content.ts";
import { evidenceOf } from "./evidence.ts";
import { StatusDialog } from "./StatusDialog.tsx";

// Counted once: the build's facts over the catalog's cases.
const EVIDENCE_FIGURES = evidenceOf(
  REACH_CASES.map((c) => c.id),
  __REACH_FACTS__,
);

/**
 * The hero's bottom row: the evidence strip (the demo's sealed readings and, once the anchor
 * contract is deployed, a link to their fingerprints on it) on the text column, the status chip on
 * the right and the data attribution under the strip. The chip reads the daily run's status and
 * opens it.
 *
 * @returns The bottom row.
 */
export function Footer() {
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let live = true;
    loadStatus()
      .then((found) => {
        if (live) {
          setStatus(found);
        }
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  const state = status === null ? "unknown" : status.run.ok ? "ok" : "failed";
  return (
    <div className="hero-foot">
      <div className="hero-foot__row">
        {EVIDENCE_FIGURES === null ? null : (
          <ul className="hero-evidence" aria-label={EVIDENCE.label}>
            <li className="hero-evidence__item">
              <strong>{String(EVIDENCE_FIGURES.sealedPasses)}</strong>{" "}
              {EVIDENCE.sealed(EVIDENCE_FIGURES.sealedPasses)}
            </li>
            {LEDGER_ANCHOR_ADDRESS === null ? null : (
              <li className="hero-evidence__item">
                <a
                  className="hero-evidence__link"
                  href={explorerUrl("address", LEDGER_ANCHOR_ADDRESS)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {EVIDENCE.anchored}
                  <ArrowUpRight size={13} strokeWidth={1.75} aria-hidden="true" />
                  <span className="hero-ui__visually-hidden"> {EVIDENCE.anchorHint}</span>
                </a>
              </li>
            )}
          </ul>
        )}
        <button
          type="button"
          className="hero-chip hero-ui__glass"
          data-state={state}
          aria-haspopup="dialog"
          title={RUN_STATUS.open}
          onClick={() => {
            setOpen(true);
          }}
        >
          <span className="hero-chip__dot" aria-hidden="true" />
          <span className="hero-chip__text">
            {state === "ok"
              ? RUN_STATUS.chipOk
              : state === "failed"
                ? RUN_STATUS.chipFailed
                : STATUS}
          </span>
          <span className="hero-ui__visually-hidden"> · {RUN_STATUS.open}</span>
        </button>
      </div>
      <p className="hero-attribution">{ATTRIBUTION}</p>
      <StatusDialog
        open={open}
        status={status}
        onClose={() => {
          setOpen(false);
        }}
      />
    </div>
  );
}
