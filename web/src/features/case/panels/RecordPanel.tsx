import {
  Anchor,
  Check,
  Clock,
  Download,
  ExternalLink,
  FileSearch,
  ShieldCheck,
  X,
} from "lucide-react";
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
import { ALONG_CLASSES, TEMPERATURE_CLASSES } from "../../reaches/along.ts";
import { checkFile, type FileCheck } from "../../reaches/checkfile.ts";
import { loadProof, loadSignatures, loadStatus, loadText } from "../../reaches/data.ts";
import { FNU_CLASSES } from "../../reaches/scene.ts";
import type {
  ObservationRecord,
  ReachData,
  SeriesRow,
  ThermalRecord,
  ThermalRow,
} from "../../reaches/types.ts";
import {
  editable,
  isNumberText,
  verifyRecord,
  type Editable,
  type Verification,
} from "../../reaches/verify.ts";
import { CASE_COPY, formatDate, landsatName } from "../content.ts";
import { alongPassOf, temperaturePassOf, type Spot } from "../spot.ts";
import { DisclosureButton } from "./DisclosureButton.tsx";
import { HelpTip } from "./HelpTip.tsx";
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
  /** The reading spot, away from the start (null or absent: the start's records). */
  readonly spot?: Spot | null;
}

/** An along-river record (turbidity or water temperature): one class, or reason, per window. */
interface AlongRecord {
  readonly schema: string;
  readonly sceneId: string;
  readonly recordSha256: string;
  readonly codeCommit: string;
  readonly modelId: string;
  readonly modelCardSha256: string;
  readonly items: readonly { readonly id: string }[];
  readonly windows: readonly {
    readonly id: string;
    readonly fnuClass?: string;
    readonly temperatureClass?: string;
    readonly abstainReason?: string;
  }[];
}

type AnyRecord = ObservationRecord | ThermalRecord | AlongRecord;

function isAlong(record: AnyRecord): record is AlongRecord {
  return "schema" in record && record.schema.startsWith("riveretch.along");
}

// The along record a pass has, and where its file is: its series names it; a series published
// before it did leaves it to the ledger.
function useAlongFile(
  reach: ReachData,
  folder: "along" | "along-temperature",
  pass: { readonly recordSha256: string; readonly file?: string } | null,
): string | null {
  const [found, setFound] = useState<{ sha: string; file: string } | null>(null);
  useEffect(() => {
    if (pass === null || pass.file !== undefined) {
      return undefined;
    }
    let live = true;
    loadText(reach.base, `${folder}/ledger.jsonl`)
      .then((text) => {
        const line = text
          .split("\n")
          .filter((t) => t.trim() !== "")
          .map((t) => JSON.parse(t) as { recordSha256: string; file: string })
          .find((l) => l.recordSha256 === pass.recordSha256);
        if (live && line !== undefined) {
          setFound({ sha: pass.recordSha256, file: `${folder}/${line.file}` });
        }
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [reach.base, folder, pass]);
  if (pass === null) {
    return null;
  }
  if (pass.file !== undefined) {
    return `${folder}/${pass.file}`;
  }
  return found?.sha === pass.recordSha256 ? found.file : null;
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
  /** An along record: the reading spot's window, its classes and their words. */
  readonly windowId?: string;
  readonly classes?: readonly string[];
  readonly words?: Readonly<Record<string, string>>;
}

function sourceOf(
  reach: ReachData,
  row: SeriesRow | null,
  thermal: ThermalRow | null,
  along: Source | null,
): Source | null {
  const { record: copy } = CASE_COPY;
  if (along !== null) {
    return along;
  }
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

function isThermal(record: AnyRecord): record is ThermalRecord {
  return "kind" in record;
}

// A file someone was sent, checked against this reach: a water-temperature record against the
// temperature ledger, anything else (a turbidity record, a series) against the observations'.
async function checkSentFile(reach: ReachData, text: string): Promise<FileCheck> {
  let thermal = false;
  try {
    const parsed = JSON.parse(text) as unknown;
    thermal = typeof parsed === "object" && parsed !== null && "kind" in parsed;
  } catch {
    // A series (CSV), or not a RiverEtch file at all.
  }
  if (thermal && reach.thermal !== null) {
    return checkFile(text, {
      site: reach.info.site,
      series: reach.thermal.series,
      ledger: await loadText(reach.base, "thermal/ledger.jsonl"),
      load: (path) => loadText(reach.base, `thermal/${path}`),
    });
  }
  return checkFile(text, {
    site: reach.info.site,
    series: reach.series,
    ledger: await loadText(reach.base, "ledger.jsonl"),
    load: (path) => loadText(reach.base, path),
  });
}

// A changed value in a line: what, the sealed value and the file's.
function changeText(path: string, sealed: string, given: string): string {
  const { record: copy } = CASE_COPY;
  return copy.file.change(copy.fields[path] ?? path, sealed, given);
}

// What "Check a file" found, in marks and words.
function FileResult({ check }: { readonly check: FileCheck }) {
  const { file } = CASE_COPY.record;
  if (check.kind === "unreadable") {
    return <p className="case-verify__note">{file.unreadable}</p>;
  }
  if (check.kind === "other-reach") {
    return <p className="case-verify__note">{file.otherReach(check.site)}</p>;
  }
  if (check.kind === "record") {
    const date = formatDate(check.date, true);
    return (
      <ul className="case-verify__lines" data-sealed={check.identical}>
        <Line ok={check.identical}>
          {check.identical ? file.identical(date) : file.notIdentical(date)}
        </Line>
        <Line ok={check.inLedger}>{check.inLedger ? file.inLedger : file.notInLedger}</Line>
        {check.selfSealed ? null : <Line ok={false}>{file.selfBroken}</Line>}
        {check.changes.map((c) => (
          <li key={c.path} className="case-verify__altered">
            {changeText(c.path, c.sealed, c.given)}
          </li>
        ))}
      </ul>
    );
  }
  const off = check.rows.filter((r) => r.status === "changed" || r.status === "unsealed");
  const unknown = check.rows.filter((r) => r.status === "unknown").length;
  const known = check.rows.length - unknown;
  const shown = off.slice(0, 4);
  return (
    <ul className="case-verify__lines" data-sealed={off.length === 0 && unknown === 0}>
      <Line ok={off.length === 0}>
        {off.length === 0 ? file.seriesSame(known) : file.seriesChanged(off.length, known)}
      </Line>
      {unknown === 0 ? null : <Line ok={false}>{file.unknown(unknown)}</Line>}
      {shown.map((r) => (
        <li key={`${r.sceneId}-${r.status}`} className="case-verify__altered">
          {formatDate(r.date, true)}:{" "}
          {r.status === "unsealed" && r.changes.length === 0
            ? file.unsealed
            : r.changes.map((c) => changeText(c.path, c.sealed, c.given)).join("; ")}
          {r.status === "unsealed" && r.changes.length > 0 ? ` (${file.unsealed})` : ""}
        </li>
      ))}
      {off.length > shown.length ? (
        <li className="case-verify__altered">{file.more(off.length - shown.length)}</li>
      ) : null}
    </ul>
  );
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
 * the browser and checks it against the ledger, the model card and the anchor on Sepolia. "Change
 * one number first" opens a field with the record's estimate (its value, or its class on a reach
 * with no gauge), which the reader changes in memory to see a tampered record fail, and puts back
 * to see it match again. Folded (the
 * default), it shows just those; its details add the record's provenance (scene, satellite images,
 * processing, code, model card and seal), the download, the anchor contract and the owner's
 * anchoring. On the temperature tab it shows the selected Landsat pass's water-temperature record,
 * checked against its own ledger and card.
 *
 * @returns The record panel.
 */
export function RecordPanel({ reach, row, thermal = null, spot = null }: RecordPanelProps) {
  const { record: copy } = CASE_COPY;
  const alterId = useId();
  const fieldId = useId();
  const hintId = useId();
  const detailsId = useId();
  const [open, setOpen] = usePanelOpen("record");
  const [record, setRecord] = useState<{
    file: string;
    data: AnyRecord;
    field: Editable | null;
  } | null>(null);
  const [alter, setAlter] = useState(false);
  const fileId = useId();
  const fileHintId = useId();
  const [sent, setSent] = useState<
    | { state: "idle" }
    | { state: "running" }
    | { state: "done"; check: FileCheck }
    | { state: "failed" }
  >({ state: "idle" });
  // The reader's value for the record's field; another pass starts again from its sealed value.
  const [draft, setDraft] = useState<{ file: string; text: string } | null>(null);
  const [stored, setCheck] = useState<CheckState>({ state: "idle" });
  const [proof, setProof] = useState<{
    result: Verification;
    chain: ChainCheck | null;
    bitcoin: BitcoinWitness | null;
    signature: SignatureWitness | null;
  } | null>(null);
  const anchor = useLedgerAnchor(reach);
  // Away from the start: the pass's along-river record (water temperature on its tab), when it has
  // one; else the start's record, as before.
  const alongPass = spot === null || thermal !== null ? null : alongPassOf(reach, row?.sceneId);
  const temperaturePass =
    spot === null || thermal === null ? null : temperaturePassOf(reach, thermal.sceneId);
  const alongFile = useAlongFile(reach, "along", alongPass);
  const temperatureFile = useAlongFile(reach, "along-temperature", temperaturePass);
  const along: Source | null =
    spot !== null && alongFile !== null && row !== null
      ? {
          kind: "along",
          file: alongFile,
          ledger: "along/ledger.jsonl",
          card: undefined,
          caption: CASE_COPY.spot.recordCaption(formatDate(row.date, true)),
          windowId: spot.id,
          classes: ALONG_CLASSES,
          words: CASE_COPY.ungauged.classes,
        }
      : spot !== null && temperatureFile !== null && thermal !== null
        ? {
            kind: "along-temperature",
            file: temperatureFile,
            ledger: "along-temperature/ledger.jsonl",
            card: undefined,
            caption: CASE_COPY.spot.recordTemperatureCaption(
              landsatName(thermal.platform),
              formatDate(thermal.date, true),
            ),
            windowId: spot.id,
            classes: TEMPERATURE_CLASSES,
            words: CASE_COPY.temperatureClasses,
          }
        : null;
  const source = sourceOf(reach, row, thermal, along);
  const windowId = source?.windowId;
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
          setRecord({
            file,
            data: JSON.parse(text) as AnyRecord,
            field: editable(text, windowId),
          });
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
  }, [reach.base, file, windowId]);

  const data = record !== null && record.file === file ? record.data : null;
  const estimate =
    data === null || isAlong(data)
      ? undefined
      : isThermal(data)
        ? data.estimate
        : data.estimates[0];
  const field = record !== null && record.file === file ? record.field : null;
  const value = field === null ? "" : draft?.file === file ? draft.text : field.sealed;
  const valid = field === null || field.kind === "class" || isNumberText(value);
  // A class reads as its range; a number as the record writes it.
  const words: Readonly<Record<string, string>> = source?.words ?? CASE_COPY.ungauged.classes;
  const shown = (text: string) => (field?.kind === "class" ? (words[text] ?? text) : text);
  const unit = estimate?.unit ?? "";
  const fieldLabel =
    field === null
      ? ""
      : source?.kind === "along-temperature"
        ? copy.fieldTemperatureClass
        : field.kind === "class"
          ? copy.fieldClass
          : field.path === "indices.ndti.downstream"
            ? copy.fieldIndex
            : data !== null && isThermal(data)
              ? copy.fieldTemperature(unit)
              : copy.fieldValue(unit);
  // The reach's classes, and the sealed one when it is not among them.
  const classes: readonly string[] = source?.classes ?? reach.card?.classes?.labels ?? FNU_CLASSES;
  const options =
    field?.kind === "class" && !classes.includes(field.sealed)
      ? [...classes, field.sealed]
      : classes;
  const typed = (text: string) => {
    setDraft({ file: file ?? "", text });
    setCheck({ state: "idle" });
  };

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
      const result = await verifyRecord(
        recordText,
        ledger,
        card,
        alter && field !== null ? value.trim() : undefined,
        source.windowId,
      );
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

  // A record with no reading names why; the panels say "No reading" only.
  const why =
    data === null
      ? undefined
      : isAlong(data)
        ? data.windows.find((w) => w.id === windowId)?.abstainReason
        : ((estimate as { abstainReason?: string | null } | undefined)?.abstainReason ?? undefined);
  const rows =
    data === null
      ? []
      : isAlong(data)
        ? [
            { label: copy.scene, value: data.sceneId.split(":").at(-1) ?? data.sceneId },
            {
              label: data.schema.includes("temperature") ? copy.landsatImages : copy.images,
              value: data.items.map((item) => item.id).join(", "),
            },
            {
              label: CASE_COPY.spot.recordStretch,
              value: spot === null ? "–" : CASE_COPY.spot.recordWindow(spot.id, spot.stretch),
            },
            ...(why === undefined ? [] : [{ label: copy.noReadingWhy, value: why }]),
            {
              label: copy.code,
              value: (
                <a
                  href={`${REPOSITORY}/commit/${data.codeCommit}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {short(data.codeCommit, 10)}
                </a>
              ),
            },
            {
              label: copy.card,
              value: `${data.modelId.split(":")[0] ?? "–"} · ${short(data.modelCardSha256)}`,
            },
            { label: copy.seal, value: short(data.recordSha256, 16) },
          ]
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
            ...(why === undefined ? [] : [{ label: copy.noReadingWhy, value: why }]),
            { label: copy.seal, value: short(data.recordSha256, 16) },
            ...(row?.supersedes === undefined || isThermal(data)
              ? []
              : [
                  {
                    label: copy.replaces,
                    value: `${short(row.supersedes, 16)} · ${copy.replacesNote}`,
                  },
                ]),
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
          <div className="case-record__title">
            <h2 className="case-head__title" id="case-record-title">
              {copy.title}
            </h2>
            <HelpTip label={copy.whyLabel}>{copy.why}</HelpTip>
          </div>
          {source === null ? null : <p className="case-head__caption">{source.caption}</p>}
        </div>
        <DisclosureButton
          label={copy.details}
          open={open}
          controls={detailsId}
          onToggle={setOpen}
        />
      </header>
      {data !== null && field === null ? null : (
        <label className="case-record__alter" htmlFor={alterId} data-tour="alter">
          <input
            id={alterId}
            type="checkbox"
            checked={alter}
            aria-controls={fieldId}
            onChange={(event) => {
              setAlter(event.target.checked);
              setDraft(null);
              setCheck({ state: "idle" });
            }}
          />
          {copy.alter}
        </label>
      )}
      {alter && field !== null ? (
        <div className="case-record__field">
          <label className="case-record__field-label" htmlFor={fieldId}>
            {fieldLabel}
          </label>
          {field.kind === "class" ? (
            <select
              id={fieldId}
              className="case-record__input"
              value={value}
              aria-describedby={hintId}
              onChange={(event) => {
                typed(event.target.value);
              }}
            >
              {options.map((c) => (
                <option key={c} value={c}>
                  {words[c] ?? c}
                </option>
              ))}
            </select>
          ) : (
            <input
              id={fieldId}
              className="case-record__input"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              spellCheck={false}
              value={value}
              aria-invalid={!valid}
              aria-describedby={hintId}
              onChange={(event) => {
                typed(event.target.value);
              }}
            />
          )}
          <p className="case-record__field-hint" id={hintId} data-invalid={!valid}>
            {valid ? copy.sealedAs(shown(field.sealed)) : copy.notNumber}
          </p>
        </div>
      ) : null}
      <button
        type="button"
        className="case-btn case-btn--solid case-record__verify"
        data-tour="verify"
        onClick={() => void verify()}
        disabled={file === null || check.state === "running" || (alter && !valid)}
      >
        <ShieldCheck size={15} strokeWidth={1.9} aria-hidden="true" />
        {check.state === "running" ? copy.verifying : copy.verify}
      </button>
      <div className="case-verify" aria-live="polite">
        {check.state === "failed" ? <p className="case-verify__note">{copy.failed}</p> : null}
        {check.state === "done" ? (
          <ul className="case-verify__lines" data-sealed={check.result.sealed}>
            {check.result.altered === null ? (
              alter && field !== null ? (
                <li className="case-verify__same">{copy.unchanged}</li>
              ) : null
            ) : (
              <li className="case-verify__altered">
                {copy.altered}: {fieldLabel}, {shown(check.result.altered.from)} →{" "}
                {shown(check.result.altered.to)}
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
      <div className="case-record__file">
        <label className="case-btn case-btn--ghost case-record__file-btn" htmlFor={fileId}>
          <FileSearch size={14} strokeWidth={1.9} aria-hidden="true" />
          {sent.state === "running" ? copy.checkingFile : copy.checkFile}
        </label>
        <input
          id={fileId}
          className="case-visually-hidden"
          type="file"
          accept=".json,.csv,application/json,text/csv"
          aria-describedby={fileHintId}
          onChange={(event) => {
            const picked = event.target.files?.[0];
            event.target.value = "";
            if (picked === undefined) {
              return;
            }
            setSent({ state: "running" });
            picked
              .text()
              .then((text) => checkSentFile(reach, text))
              .then((check) => {
                setSent({ state: "done", check });
              })
              .catch(() => {
                setSent({ state: "failed" });
              });
          }}
        />
        <p className="case-record__field-hint" id={fileHintId}>
          {copy.checkFileHint}
        </p>
        <div className="case-verify" aria-live="polite">
          {sent.state === "failed" ? <p className="case-verify__note">{copy.file.failed}</p> : null}
          {sent.state === "done" ? <FileResult check={sent.check} /> : null}
        </div>
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
