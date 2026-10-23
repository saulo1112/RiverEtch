import { ShieldCheck } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { subjectLabel, type LedgerKind } from "../../chain/ledger.ts";
import { useLedgerAnchor, type ChainCheck } from "../../chain/useLedgerAnchor.ts";
import { witnessesOf } from "../../chain/recordWitnesses.ts";
import type { BitcoinWitness, SignatureWitness } from "../../chain/witness.ts";
import { loadText } from "../../reaches/data.ts";
import type {
  ObservationRecord,
  ReachData,
  SeriesRow,
  ThermalRecord,
  ThermalRow,
} from "../../reaches/types.ts";
import { verifyRecord, type Verification } from "../../reaches/verify.ts";
import { CASE_COPY, formatDate, landsatName } from "../content.ts";
import { alongPassOf, temperaturePassOf, type Spot } from "../spot.ts";
import { VerifyDialog, type RecordDetail } from "./VerifyDialog.tsx";

/** The repository the records' code commits belong to. */
export const REPOSITORY = "https://github.com/saulo1112/RiverEtch";

/** Props of {@link ReadingCheck}. */
export interface ReadingCheckProps {
  readonly reach: ReachData;
  /** The selected pass (null: none yet). */
  readonly row: SeriesRow | null;
  /** The water-temperature pass to check instead (the temperature tab; null: the pass). */
  readonly thermal?: ThermalRow | null;
  /** The reading spot, away from the start (null: the start's records). */
  readonly spot?: Spot | null;
}

// The record checked: its ledger, its file, the ledger file and card it is checked against.
interface Source {
  readonly kind: LedgerKind;
  readonly file: string;
  readonly ledger: string;
  readonly card: string | undefined;
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
  readonly windows: readonly { readonly id: string; readonly abstainReason?: string }[];
}

type AnyRecord = ObservationRecord | ThermalRecord | AlongRecord;

const isAlong = (r: AnyRecord): r is AlongRecord =>
  "schema" in r && r.schema.startsWith("riveretch.along");
const isThermal = (r: AnyRecord): r is ThermalRecord => "kind" in r;

// The along record a pass has: its series names its file, or its ledger does.
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
  return pass.file !== undefined
    ? `${folder}/${pass.file}`
    : found?.sha === pass.recordSha256
      ? found.file
      : null;
}

const short = (hash: string, size = 12) => (hash.length > size ? `${hash.slice(0, size)}…` : hash);

// What a record's details say: its scene, images, processing, code, model sheet and fingerprint,
// and why it has no reading where it has none.
function detailsOf(
  data: AnyRecord,
  windowId: string | undefined,
  spot: Spot | null,
): RecordDetail[] {
  const { record: copy } = CASE_COPY;
  const code = (commit: string): ReactNode => (
    <a href={`${REPOSITORY}/commit/${commit}`} target="_blank" rel="noopener noreferrer">
      {short(commit, 10)}
    </a>
  );
  if (isAlong(data)) {
    const why = data.windows.find((w) => w.id === windowId)?.abstainReason;
    return [
      { label: copy.scene, value: data.sceneId.split(":").at(-1) ?? data.sceneId },
      {
        label: data.schema.includes("temperature") ? copy.landsatImages : copy.images,
        value: data.items.map((item) => item.id).join(", "),
      },
      ...(spot === null
        ? []
        : [
            {
              label: CASE_COPY.spot.recordStretch,
              value: CASE_COPY.spot.recordWindow(spot.id, spot.stretch),
            },
          ]),
      ...(why === undefined ? [] : [{ label: copy.noReadingWhy, value: why }]),
      { label: copy.code, value: code(data.codeCommit) },
      {
        label: copy.card,
        value: `${data.modelId.split(":")[0] ?? "–"} · ${short(data.modelCardSha256)}`,
      },
      { label: copy.seal, value: short(data.recordSha256, 16) },
    ];
  }
  const estimate = isThermal(data) ? data.estimate : data.estimates[0];
  const why = (estimate as { abstainReason?: string | null } | undefined)?.abstainReason;
  return [
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
    ...(why == null ? [] : [{ label: copy.noReadingWhy, value: why }]),
    { label: copy.code, value: code(data.provenance.codeCommit) },
    {
      label: copy.card,
      value: `${estimate?.modelId?.split(":")[0] ?? "–"} · ${short(estimate?.modelCardSha256 ?? "–")}`,
    },
    { label: copy.seal, value: short(data.recordSha256, 16) },
  ];
}

/**
 * "Check this reading": a small link on the reading card that checks the reading shown (the pass's
 * record, its water-temperature record on that tab, or the stretch's along-river record when the
 * reading spot has moved) in the browser, and opens the check: its verdict in one sentence first,
 * its steps folded under "Show the steps".
 *
 * @param props - The reach, the pass and where the reading spot is.
 * @param props.reach - The reach.
 * @param props.row - The selected pass.
 * @param props.thermal - The water-temperature pass to check instead.
 * @param props.spot - The reading spot, away from the start.
 * @returns The link and its dialog.
 */
export function ReadingCheck({ reach, row, thermal = null, spot = null }: ReadingCheckProps) {
  const { record: copy } = CASE_COPY;
  const anchor = useLedgerAnchor(reach);
  const [running, setRunning] = useState(false);
  const [failed, setFailed] = useState(false);
  const [proof, setProof] = useState<{
    result: Verification;
    chain: ChainCheck | null;
    bitcoin: BitcoinWitness | null;
    signature: SignatureWitness | null;
    fixedOn: string | null;
    details: RecordDetail[];
    download: string;
  } | null>(null);
  // Away from the start: the stretch's along-river record (water temperature on its tab).
  const alongPass = spot === null || thermal !== null ? null : alongPassOf(reach, row?.sceneId);
  const temperaturePass =
    spot === null || thermal === null ? null : temperaturePassOf(reach, thermal.sceneId);
  const alongFile = useAlongFile(reach, "along", alongPass);
  const temperatureFile = useAlongFile(reach, "along-temperature", temperaturePass);
  const source: Source | null =
    spot !== null && alongFile !== null
      ? { kind: "along", file: alongFile, ledger: "along/ledger.jsonl", card: undefined }
      : spot !== null && temperatureFile !== null
        ? {
            kind: "along-temperature",
            file: temperatureFile,
            ledger: "along-temperature/ledger.jsonl",
            card: undefined,
          }
        : thermal !== null
          ? {
              kind: "water-temperature",
              file: `thermal/${thermal.file}`,
              ledger: "thermal/ledger.jsonl",
              card: reach.info.cards.water_temperature,
            }
          : row === null || row.file === ""
            ? null
            : {
                kind: "observations",
                file: row.file,
                ledger: "ledger.jsonl",
                card: reach.info.cards.turbidity,
              };

  const run = async () => {
    if (source === null) {
      return;
    }
    setRunning(true);
    setFailed(false);
    try {
      const [recordText, ledger, card] = await Promise.all([
        loadText(reach.base, source.file),
        loadText(reach.base, source.ledger),
        source.card === undefined ? Promise.resolve(null) : loadText(reach.base, source.card),
      ]);
      const result = await verifyRecord(recordText, ledger, card);
      const hashes = result.ledger.map((l) => l.lineSha256);
      const chain = anchor.configured
        ? await anchor.check(source.kind, result.position, hashes)
        : null;
      const { bitcoin, signature } = await witnessesOf(
        subjectLabel(reach.info.site, source.kind),
        result.position,
        hashes,
      );
      const line = ledger
        .split("\n")
        .filter((t) => t.trim() !== "")
        .map((t) => JSON.parse(t) as { recordSha256: string; createdUtc?: string })
        .find((l) => l.recordSha256 === result.stated);
      setProof({
        result,
        chain,
        bitcoin,
        signature,
        fixedOn: line?.createdUtc?.slice(0, 10) ?? null,
        details: detailsOf(JSON.parse(recordText) as AnyRecord, spot?.id, spot),
        download: `${reach.base}${source.file}`,
      });
    } catch {
      setFailed(true);
    } finally {
      setRunning(false);
    }
  };

  const caption =
    thermal !== null
      ? `${landsatName(thermal.platform)} · ${copy.ofThermal} · ${formatDate(thermal.date, true)}`
      : null;
  return (
    <>
      <button
        type="button"
        className="case-check-link"
        data-tour="verify"
        disabled={source === null || running}
        title={caption ?? undefined}
        onClick={() => void run()}
      >
        <ShieldCheck size={13} strokeWidth={1.9} aria-hidden="true" />
        {running ? copy.verifying : copy.verify}
      </button>
      {failed ? (
        <span className="case-check-link__note" role="status">
          {copy.failed}
        </span>
      ) : null}
      <VerifyDialog
        result={proof?.result ?? null}
        chain={proof?.chain ?? null}
        bitcoin={proof?.bitcoin ?? null}
        signature={proof?.signature ?? null}
        fixedOn={proof?.fixedOn ?? null}
        details={proof?.details ?? []}
        download={proof?.download ?? null}
        onClose={() => {
          setProof(null);
        }}
      />
    </>
  );
}
