import { ArrowUpRight } from "lucide-react";

import { explorerUrl, LEDGER_ANCHOR_ADDRESS } from "../../chain/config.ts";
import { REACH_CASES } from "../../reaches/catalog.ts";
import { ATTRIBUTION, EVIDENCE, STATUS } from "./content.ts";
import { evidenceOf } from "./evidence.ts";

// Counted once: the build's facts over the catalog's cases.
const EVIDENCE_FIGURES = evidenceOf(
  REACH_CASES.map((c) => c.id),
  __REACH_FACTS__,
);

/**
 * The hero's bottom row: the evidence strip (the demo's rivers, its sealed passes and, once the
 * anchor contract is deployed, a link to it) on the text column, the status chip on the right and
 * the data attribution under the strip.
 *
 * @returns The bottom row.
 */
export function Footer() {
  return (
    <div className="hero-foot">
      <div className="hero-foot__row">
        {EVIDENCE_FIGURES === null ? null : (
          <ul className="hero-evidence" aria-label={EVIDENCE.label}>
            <li className="hero-evidence__item">
              <strong>{String(EVIDENCE_FIGURES.rivers)}</strong>{" "}
              {EVIDENCE.rivers(EVIDENCE_FIGURES.rivers)}
            </li>
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
        <p className="hero-chip hero-ui__glass">
          <span className="hero-chip__dot" aria-hidden="true" />
          <span className="hero-chip__text">{STATUS}</span>
        </p>
      </div>
      <p className="hero-attribution">{ATTRIBUTION}</p>
    </div>
  );
}
