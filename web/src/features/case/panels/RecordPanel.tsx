import { Anchor, Check, Clock, Download, ExternalLink, ShieldCheck, X } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";

import { explorerUrl } from "../../chain/config.ts";
import { subjectLabel, type LedgerKind } from "../../chain/ledger.ts";
import {
  checkBitcoin,
  checkSignature,
  coveringProof,
  explorerHeader,
  type BitcoinWitness,
  type SignatureWitness,
} from "../../chain/witness.ts";
import {
  useLedgerAnchor,
  type AnchorOutcome,
  type ChainCheck,
} from "../../chain/useLedgerAnchor.ts";
import { loadProof, loadSignatures, loadStatus, loadText } from "../../reaches/data.ts";
import type {
  ObservationRecord,
  ReachData,
  SeriesRow,
  ThermalRecord,
  ThermalRow,
} from "../../reaches/types.ts";
import { verifyRecord, type Verification } from "../../reaches/verify.ts";
import { CASE_COPY, formatDate, landsatName } from "../content.ts";
import { DisclosureButton } from "./DisclosureButton.tsx";
import { usePanelOpen } from "./usePanelOpen.ts";
import { VerifyDialog } from "./VerifyDialog.tsx";

/** Props of {@link RecordPanel}. */
export interface RecordPanelProps {
  /** The reach. */
  readonly reach: ReachData;
  /** The selected pass (null before the series loads). */
  readonly row: SeriesRow | null;
  /** A water-temperature pass to show instead (the temperature tab; null: the pass's record). */
  readonly thermal?: ThermalRow | null;
}

/** The repository the records' code commits belong to. */
export const REPOSITORY = "https://github.com/saulo1112/RiverEtch";

// A check, and the record file it is about (a new selection shows none).
type CheckState =
  | { readonly state: "idle" }
  | { readonly state: "running"; readonly file: string }
  | {
      readonly state: "done";
      readonly file: string;
      readonly result: Verification;
      readonly chain: ChainCheck | null;
    }
  | { readonly state: "failed"; readonly file: string };

// The record shown: its file, the ledger and card it is checked against (paths in the reach's
// folder) and a caption naming it.
interface Source {
  readonly kind: LedgerKind;
  readonly file: string;
  readonly ledger: string;
  readonly card: string | undefined;
  readonly caption: string;
}

function sourceOf(
  reach: ReachData,
  row: SeriesRow | null,
  thermal: ThermalRow | null,
): Source | null {
  const { record: copy } = CASE_COPY;
  if (thermal !== null) {
    const date = formatDate(thermal.date, true);
    return {
      kind: "water-temperature",
      file: `thermal/${thermal.file}`,
      ledger: "thermal/ledger.jsonl",
      card: reach.info.cards.water_temperature,
      caption: `${landsatName(thermal.platform)} · ${copy.ofThermal} · ${date}`,
    };
  }
  return row === null
    ? null
    : {
        kind: "observations",
        file: row.file,
        ledger: "ledger.jsonl",
        card: reach.info.cards.turbidity,
        caption: `${copy.ofPass} · ${formatDate(row.date, true)}`,
      };
}

function isThermal(record: ObservationRecord | ThermalRecord): record is ThermalRecord {
  return "kind" in record;
}

function short(hash: string, size = 12): string {
  return hash.length > size ? `${hash.slice(0, size)}…` : hash;
}

function Line({ ok, children }: { readonly ok: boolean | null; readonly children: ReactNode }) {
  return (
    <li className="case-verify__line" data-ok={ok ?? "pending"}>
      {ok === null ? (
        <Clock size={14} strokeWidth={2.25} aria-hidden="true" />
      ) : ok ? (
        <Check size={14} strokeWidth={2.25} aria-hidden="true" />
      ) : (
        <X size={14} strokeWidth={2.25} aria-hidden="true" />
      )}
      <span>{children}</span>
    </li>
  );
}

// A record's anchor as a line of the panel's check.
function ChainItem({ chain }: { readonly chain: ChainCheck }) {
  const { record: copy } = CASE_COPY;
  if (chain.state === "anchored") {
    const day = new Date(chain.anchor.timestamp * 1000).toISOString().slice(0, 10);
    return (
      <Line ok>
        <a
          href={explorerUrl("block", chain.anchor.blockNumber)}
          target="_blank"
          rel="noopener noreferrer"
        >
          {copy.chainAnchored(formatDate(day, true), chain.anchor.blockNumber)}
        </a>
      </Line>
    );
  }
  if (chain.state === "mismatch") {
    return <Line ok={false}>{copy.chainMismatch}</Line>;
  }
  return (
    <Line ok={null}>{chain.state === "pending" ? copy.chainPending : copy.chainUnavailable}</Line>
  );
}

// The owner's action: anchor the reach's ledgers on Sepolia in one transaction.
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

// The two witnesses beside the anchor, from the daily run's published files: a Bitcoin timestamp
// and an ML-DSA-65 signature of a head covering the record's ledger line. Both are "unavailable"
// when the published files cannot be read (for instance before the repository is public).
async function witnesses(
  label: string,
  position: number,
  hashes: readonly string[],
): Promise<{ bitcoin: BitcoinWitness; signature: SignatureWitness }> {
  const status = await loadStatus();
  if (status === null || position < 0) {
    return { bitcoin: { state: "unavailable" }, signature: { state: "unavailable" } };
  }
  const entry = coveringProof(status.proofs ?? [], label, position);
  const bytes = entry === null ? null : await loadProof(entry.file);
  const bitcoin: BitcoinWitness =
    entry === null
      ? { state: "none" }
      : bytes === null
        ? { state: "unavailable" }
        : await checkBitcoin(entry, bytes, hashes, (h) => explorerHeader(h)).catch(
            (): BitcoinWitness => ({ state: "mismatch" }),
          );
  const signature = checkSignature(
    await loadSignatures(),
    __ML_DSA_PUBLIC_KEY__,
    label,
    position,
    hashes,
  );
  return { bitcoin, signature };
}

/**
 * Right panel: the selected pass's record and "Verify this record", which recomputes its SHA-256 in
 * the browser and checks it against the ledger, the model card and the anchor on Sepolia. "Alter
 * one value first" changes a number in memory to show a tampered record failing. Folded (the
 * default), it shows just those; its details add the record's provenance (scene, satellite images,
 * processing, code, model card and seal), the download, the anchor contract and the owner's
 * anchoring. On the temperature tab it shows the selected Landsat pass's water-temperature record,
 * checked against its own ledger and card.
 *
 * @returns The record panel.
 */
export function RecordPanel({ reach, row, thermal = null }: RecordPanelProps) {
  const { record: copy } = CASE_COPY;
  const alterId = useId();
  const detailsId = useId();
  const [open, setOpen] = usePanelOpen("record");
  const [record, setRecord] = useState<{
    file: string;
    data: ObservationRecord | ThermalRecord;
  } | null>(null);
  const [alter, setAlter] = useState(false);
  const [stored, setCheck] = useState<CheckState>({ state: "idle" });
  const [proof, setProof] = useState<{
    result: Verification;
    chain: ChainCheck | null;
    bitcoin: BitcoinWitness | null;
    signature: SignatureWitness | null;
  } | null>(null);
  const anchor = useLedgerAnchor(reach);
  const source = sourceOf(reach, row, thermal);
  const file = source?.file ?? null;
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
          setRecord({ file, data: JSON.parse(text) as ObservationRecord | ThermalRecord });
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
    if (source === null) {
      return;
    }
    const { file: path, ledger: ledgerPath, card: cardPath, kind } = source;
    setCheck({ state: "running", file: path });
    try {
      const [recordText, ledger, card] = await Promise.all([
        loadText(reach.base, path),
        loadText(reach.base, ledgerPath),
        cardPath === undefined ? Promise.resolve(null) : loadText(reach.base, cardPath),
      ]);
      const result = await verifyRecord(recordText, ledger, card, alter);
      const chain = anchor.configured
        ? await anchor.check(
            kind,
            result.position,
            result.ledger.map((l) => l.lineSha256),
          )
        : null;
      const hashes = result.ledger.map((l) => l.lineSha256);
      const { bitcoin, signature } = await witnesses(
        subjectLabel(reach.info.site, kind),
        result.position,
        hashes,
      );
      setCheck({ state: "done", file: path, result, chain });
      setProof({ result, chain, bitcoin, signature });
    } catch {
      setCheck({ state: "failed", file: path });
    }
  };

  const data = record !== null && record.file === file ? record.data : null;
  const estimate = data === null ? undefined : isThermal(data) ? data.estimate : data.estimates[0];
  const rows =
    data === null
      ? []
      : [
          { label: copy.scene, value: data.sceneId.split(":").at(-1) ?? data.sceneId },
          {
            label: isThermal(data) ? copy.landsatImages : copy.images,
            value: data.provenance.stacItems.map((item) => (
              <a key={item.id} href={item.url} target="_blank" rel="noopener noreferrer">
                {item.id}
              </a>
            )),
          },
          isThermal(data)
            ? { label: copy.processing, value: copy.thermalProcessing }
            : {
                label: copy.processing,
                value: `Sen2Cor L2A · baseline ${data.provenance.processingBaseline.join(", ")}`,
              },
          ...(isThermal(data)
            ? [
                {
                  label: copy.window,
                  value: `${String(data.window.waterPixels)} ${copy.waterPixels} · ${String(data.window.surfaceTemperatureK)} K`,
                },
              ]
            : []),
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
    <section
      className="case-panel case-record case-glass"
      data-frame=""
      data-open={open}
      aria-labelledby="case-record-title"
    >
      <header className="case-head">
        <div className="case-head__text">
          <h2 className="case-head__title" id="case-record-title">
            {copy.title}
          </h2>
          {source === null ? null : <p className="case-head__caption">{source.caption}</p>}
        </div>
        <DisclosureButton
          label={copy.details}
          open={open}
          controls={detailsId}
          onToggle={setOpen}
        />
      </header>
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
            {check.chain === null ? null : <ChainItem chain={check.chain} />}
          </ul>
        ) : null}
      </div>
      <div className="case-record__details" id={detailsId} hidden={!open}>
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
        {anchor.address === null ? (
          <p className="case-record__hint">{copy.notAnchored}</p>
        ) : (
          <p className="case-record__hint">
            {copy.anchoredHint}{" "}
            <a
              href={explorerUrl("address", anchor.address)}
              target="_blank"
              rel="noopener noreferrer"
            >
              {copy.contract}
              <ExternalLink size={11} strokeWidth={1.75} aria-hidden="true" />
            </a>
          </p>
        )}
        {anchor.isOwner ? <AnchorAction run={anchor.anchorReach} /> : null}
      </div>
      <VerifyDialog
        result={proof?.result ?? null}
        chain={proof?.chain ?? null}
        bitcoin={proof?.bitcoin ?? null}
        signature={proof?.signature ?? null}
        onClose={() => {
          setProof(null);
        }}
      />
    </section>
  );
}
