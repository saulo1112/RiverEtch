import { Check, Download, ShieldCheck, X } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";

import { loadText } from "../../reaches/data.ts";
import type { ObservationRecord, ReachData, SeriesRow } from "../../reaches/types.ts";
import { verifyRecord, type Verification } from "../../reaches/verify.ts";
import { CASE_COPY } from "../content.ts";

/** Props of {@link RecordPanel}. */
export interface RecordPanelProps {
  /** The reach. */
  readonly reach: ReachData;
  /** The selected pass (null before the series loads). */
  readonly row: SeriesRow | null;
}

/** The repository the records' code commits belong to. */
export const REPOSITORY = "https://github.com/saulo1112/Climate_Change_IEEE";

// A check, and the record file it is about (a new selection shows none).
type CheckState =
  | { readonly state: "idle" }
  | { readonly state: "running"; readonly file: string }
  | { readonly state: "done"; readonly file: string; readonly result: Verification }
  | { readonly state: "failed"; readonly file: string };

function short(hash: string, size = 12): string {
  return hash.length > size ? `${hash.slice(0, size)}…` : hash;
}

function Line({ ok, children }: { readonly ok: boolean; readonly children: ReactNode }) {
  return (
    <li className="case-verify__line" data-ok={ok}>
      {ok ? (
        <Check size={14} strokeWidth={2.25} aria-hidden="true" />
      ) : (
        <X size={14} strokeWidth={2.25} aria-hidden="true" />
      )}
      <span>{children}</span>
    </li>
  );
}

/**
 * Right panel: the selected pass's record (its scene, Sentinel-2 images, processing, code, model
 * card and seal) and "Verify this record", which recomputes its SHA-256 in the browser and checks
 * it against the ledger and the model card. "Alter one value first" changes a number in memory to
 * show a tampered record failing.
 *
 * @returns The record panel.
 */
export function RecordPanel({ reach, row }: RecordPanelProps) {
  const { record: copy } = CASE_COPY;
  const alterId = useId();
  const [record, setRecord] = useState<{ file: string; data: ObservationRecord } | null>(null);
  const [alter, setAlter] = useState(false);
  const [stored, setCheck] = useState<CheckState>({ state: "idle" });
  const file = row?.file ?? null;
  const check: CheckState =
    stored.state !== "idle" && stored.file === file ? stored : { state: "idle" };

  useEffect(() => {
    if (file === null) {
      return undefined;
    }
    let live = true;
    loadText(reach.base, file)
      .then((text) => {
        if (live) {
          setRecord({ file, data: JSON.parse(text) as ObservationRecord });
        }
      })
      .catch(() => {
        if (live) {
          setRecord(null);
        }
      });
    return () => {
      live = false;
    };
  }, [reach.base, file]);

  const verify = async () => {
    if (file === null) {
      return;
    }
    setCheck({ state: "running", file });
    try {
      const cardPath = reach.info.cards.turbidity;
      const [recordText, ledger, card] = await Promise.all([
        loadText(reach.base, file),
        loadText(reach.base, "ledger.jsonl"),
        cardPath === undefined ? Promise.resolve(null) : loadText(reach.base, cardPath),
      ]);
      const result = await verifyRecord(recordText, ledger, card, alter);
      setCheck({ state: "done", file, result });
    } catch {
      setCheck({ state: "failed", file });
    }
  };

  const data = record !== null && record.file === file ? record.data : null;
  const estimate = data?.estimates[0];
  const rows =
    data === null
      ? []
      : [
          { label: copy.scene, value: data.sceneId.split(":").at(-1) ?? data.sceneId },
          {
            label: copy.images,
            value: data.provenance.stacItems.map((item) => (
              <a key={item.id} href={item.url} target="_blank" rel="noopener noreferrer">
                {item.id}
              </a>
            )),
          },
          {
            label: copy.processing,
            value: `Sen2Cor L2A · baseline ${data.provenance.processingBaseline.join(", ")}`,
          },
          {
            label: copy.code,
            value: (
              <a
                href={`${REPOSITORY}/commit/${data.provenance.codeCommit}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                {short(data.provenance.codeCommit, 10)}
              </a>
            ),
          },
          {
            label: copy.card,
            value: `${estimate?.modelId?.split(":")[0] ?? "–"} · ${short(estimate?.modelCardSha256 ?? "–")}`,
          },
          { label: copy.seal, value: short(data.recordSha256, 16) },
        ];

  return (
    <section className="case-panel case-record case-glass" aria-labelledby="case-record-title">
      <h2 className="case-record__title" id="case-record-title">
        {copy.title}
      </h2>
      <label className="case-record__alter" htmlFor={alterId}>
        <input
          id={alterId}
          type="checkbox"
          checked={alter}
          onChange={(event) => {
            setAlter(event.target.checked);
            setCheck({ state: "idle" });
          }}
        />
        {copy.alter}
      </label>
      <button
        type="button"
        className="case-btn case-btn--solid case-record__verify"
        onClick={() => void verify()}
        disabled={file === null || check.state === "running"}
      >
        <ShieldCheck size={15} strokeWidth={1.9} aria-hidden="true" />
        {check.state === "running" ? copy.verifying : copy.verify}
      </button>
      <div className="case-verify" aria-live="polite">
        {check.state === "failed" ? <p className="case-verify__note">{copy.failed}</p> : null}
        {check.state === "done" ? (
          <ul className="case-verify__lines" data-sealed={check.result.sealed}>
            {check.result.altered === null ? null : (
              <li className="case-verify__altered">
                {copy.altered}: <code>{check.result.altered.path}</code> {check.result.altered.from}{" "}
                → {check.result.altered.to}
              </li>
            )}
            <Line ok={check.result.sealed}>{check.result.sealed ? copy.sealed : copy.broken}</Line>
            <Line ok={check.result.inLedger}>
              {check.result.inLedger ? copy.inLedger : copy.notInLedger}
            </Line>
            <Line ok={check.result.chainIntact}>
              {check.result.chainIntact ? copy.chain : copy.chainBroken} (
              {String(check.result.ledgerLines)} {copy.lines})
            </Line>
            {check.result.cardMatches === null ? null : (
              <Line ok={check.result.cardMatches}>
                {check.result.cardMatches ? copy.cardOk : copy.cardBad}
              </Line>
            )}
          </ul>
        ) : null}
      </div>
      <dl className="case-record__rows">
        {rows.map((r) => (
          <div className="case-record__row" key={r.label}>
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
      {file === null ? null : (
        <a className="case-record__download" href={`${reach.base}${file}`} download>
          <Download size={13} strokeWidth={1.75} aria-hidden="true" />
          {copy.download}
        </a>
      )}
      <p className="case-record__hint">{copy.notAnchored}</p>
    </section>
  );
}
