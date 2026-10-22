import { Download } from "lucide-react";

import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY } from "../content.ts";
import { HelpTip } from "./HelpTip.tsx";

/** Props of {@link ArchivePanel}. */
export interface ArchivePanelProps {
  /** An earlier year of the reach (preregistration-archive.md). */
  readonly reach: ReachData;
}

/**
 * Right panel, in place of the record, for an earlier year: it says plainly that the year is
 * recomputed and not sealed, so there is nothing to verify, and offers the year's file, which
 * names the code and the models, for anyone to read the same passes again and compare.
 *
 * @param props - The panel's props.
 * @param props.reach - The earlier year.
 * @returns The panel (nothing for the sealed year).
 */
export function ArchivePanel({ reach }: ArchivePanelProps) {
  const archive = reach.archive;
  if (archive == null) {
    return null;
  }
  const copy = CASE_COPY.archive;
  const year = String(archive.year);
  return (
    <section
      className="case-panel case-record case-glass"
      data-frame=""
      aria-labelledby="case-archive-title"
    >
      <header className="case-head">
        <div className="case-head__text">
          <div className="case-record__title">
            <h2 className="case-head__title" id="case-archive-title">
              {CASE_COPY.record.title}
            </h2>
            <HelpTip label={copy.helpLabel}>{copy.help}</HelpTip>
          </div>
          <p className="case-head__caption">{copy.recordCaption(year)}</p>
        </div>
      </header>
      <p className="case-record__hint case-archive__text">{copy.recordText}</p>
      <a className="case-record__download" href={`${reach.base}${archive.file}`} download>
        <Download size={13} strokeWidth={1.75} aria-hidden="true" />
        {copy.download(year)}
      </a>
    </section>
  );
}
