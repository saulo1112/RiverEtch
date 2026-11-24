import { ArrowUpRight } from "lucide-react";
import { useEffect, useState } from "react";

import { explorerUrl, LEDGER_ANCHOR_ADDRESS } from "../../chain/config.ts";
import { REACH_CASES } from "../../reaches/catalog.ts";
import { loadLiveLedgers, loadStatus, type RunStatus } from "../../reaches/data.ts";
import { ATTRIBUTION, EVIDENCE, RUN_STATUS, STATUS } from "./content.ts";
import { evidenceOf, passesOf } from "./evidence.ts";
import { StatusDialog } from "./StatusDialog.tsx";

// "20 Oct" from an ISO time (UTC).
const dayMonth = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(
    new Date(iso),
  );

// Counted once: the build's facts over the catalog's cases.
const CASE_IDS = REACH_CASES.map((c) => c.id);
const EVIDENCE_FIGURES = evidenceOf(CASE_IDS, __REACH_FACTS__);
// The live count waits until the page is up: the globe and the text come first.
const LIVE_COUNT_DELAY_MS = 1500;

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
  const [livePasses, setLivePasses] = useState<number | null>(null);
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
    // The sealed passes as the daily run has published them since the build; the build's count
    // stays when they cannot be read.
    const timer = window.setTimeout(() => {
      loadLiveLedgers(CASE_IDS)
        .then((ledgers) => {
          if (live && ledgers !== null) {
            setLivePasses(
              ledgers.reduce((sum, l) => sum + passesOf(l.sentinel) + passesOf(l.landsat), 0),
            );
          }
        })
        .catch(() => undefined);
    }, LIVE_COUNT_DELAY_MS);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, []);
  // A sealed pass is never taken out of a ledger, so the live count can only add to the build's.
  const sealedPasses =
    EVIDENCE_FIGURES === null ? null : Math.max(EVIDENCE_FIGURES.sealedPasses, livePasses ?? 0);
  // Live once the record has updated at least once; until the status can be read, the bundled
  // snapshot ("Demo workspace").
  const updated = status?.lastSuccessUtc ?? null;
  const state = updated === null ? "unknown" : "live";
  return (
    <div className="hero-foot">
      <div className="hero-foot__row">
        {sealedPasses === null ? null : (
          <ul className="hero-evidence" aria-label={EVIDENCE.label}>
            <li className="hero-evidence__item">
              <strong>{String(sealedPasses)}</strong> {EVIDENCE.sealed(sealedPasses)}
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
            {updated === null ? STATUS : RUN_STATUS.chipLive(dayMonth(updated))}
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
