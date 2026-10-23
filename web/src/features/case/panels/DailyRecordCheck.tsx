import { GitCompareArrows, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { subjectLabel } from "../../chain/ledger.ts";
import { witnessesOf } from "../../chain/recordWitnesses.ts";
import { useLedgerAnchor, type ChainCheck } from "../../chain/useLedgerAnchor.ts";
import type { BitcoinWitness, SignatureWitness } from "../../chain/witness.ts";
import { compareYear, sourceYear, type Comparison } from "../../reaches/dailyrecord.ts";
import { loadText } from "../../reaches/data.ts";
import type { DailyRecord, DailyRecordRow, ReachData } from "../../reaches/types.ts";
import { verifyRecord, type Verification } from "../../reaches/verify.ts";
import { CASE_COPY, formatDate } from "../content.ts";
import { REPOSITORY } from "./ReadingCheck.tsx";
import { VerifyDialog, type RecordDetail } from "./VerifyDialog.tsx";

/** Props of {@link DailyRecordCheck}. */
export interface DailyRecordCheckProps {
  readonly reach: ReachData;
  /** The year's line of the reach's daily-record index. */
  readonly row: DailyRecordRow;
  /** The year's record (null: still loading). */
  readonly record: DailyRecord | null;
}

const FOLDER = "daily-record/";
const short = (hash: string, size = 12) => (hash.length > size ? `${hash.slice(0, size)}…` : hash);

// What the record's details say: who published it, which year, when it was fetched, what it
// replaces, the query and the code.
function detailsOf(record: DailyRecord): RecordDetail[] {
  const copy = CASE_COPY.climate.flow.detail;
  const { record: names } = CASE_COPY;
  const query = new URLSearchParams(record.provenance.query).toString();
  return [
    {
      label: copy.source,
      value: (
        <a href={record.source.url} target="_blank" rel="noopener noreferrer">
          {record.source.name}
        </a>
      ),
    },
    {
      label: record.source.measured ? copy.station : copy.model,
      value: record.source.stationId,
    },
    { label: copy.year, value: String(record.year) },
    { label: copy.days, value: String(Math.max(...record.series.map((s) => s.days.length), 0)) },
    { label: copy.lastDay, value: formatDate(record.date, true) },
    { label: copy.fetched, value: record.fetchedUtc.replace("T", " ").replace("+00:00", "") },
    {
      label: copy.replaces,
      value: record.replaces === null ? copy.first : short(record.replaces, 16),
    },
    { label: copy.query, value: `${record.provenance.api}?${query}` },
    {
      label: names.code,
      value: (
        <a
          href={`${REPOSITORY}/commit/${record.provenance.codeCommit}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          {short(record.provenance.codeCommit, 10)}
        </a>
      ),
    },
    { label: names.seal, value: short(record.recordSha256, 16) },
  ];
}

// The comparison in a few sentences: the same days first, then what the source changed.
function compared(result: Comparison, source: string): string {
  const copy = CASE_COPY.climate.flow;
  return [
    copy.compareSame(source, result.same, result.checked),
    ...(result.revised.length > 0 ? [copy.compareRevised(result.revised.length)] : []),
    ...(result.gone.length > 0 ? [copy.compareGone(result.gone.length)] : []),
    ...(result.filled > 0 ? [copy.compareFilled(result.filled)] : []),
    ...(result.newer > 0 ? [copy.compareNewer(result.newer)] : []),
  ].join(" ");
}

/**
 * The year's daily flow record checked two ways: "Check this record" (its seal, its place in the
 * reach's chained daily-record list, the post on Ethereum, the Bitcoin timestamp and the
 * signature, in the browser, as "Check this reading" does), and "Compare with the source now"
 * (the same year fetched from its source in the browser, day by day: the same, revised since, no
 * longer published).
 *
 * @param props - The reach, the year's index line and its record.
 * @param props.reach - The reach.
 * @param props.row - The year's index line.
 * @param props.record - The year's record.
 * @returns The two actions, the comparison's result and the check's dialog.
 */
export function DailyRecordCheck({ reach, row, record }: DailyRecordCheckProps) {
  const copy = CASE_COPY.climate.flow;
  const anchor = useLedgerAnchor(reach);
  const [checking, setChecking] = useState(false);
  const [failed, setFailed] = useState(false);
  const [proof, setProof] = useState<{
    result: Verification;
    chain: ChainCheck | null;
    bitcoin: BitcoinWitness | null;
    signature: SignatureWitness | null;
    fixedOn: string | null;
    details: RecordDetail[];
  } | null>(null);
  const [comparison, setComparison] = useState<
    | { readonly step: "idle" | "running" | "failed" }
    | { readonly step: "done"; readonly text: string }
  >({ step: "idle" });
  const source = record === null ? "" : copy.source[record.source.kind];
  // The comparison's result, scrolled into view in the short column it is written in.
  const resultRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (comparison.step === "done" || comparison.step === "failed") {
      resultRef.current?.scrollIntoView({ block: "nearest" });
    }
  }, [comparison.step]);

  const check = async () => {
    setChecking(true);
    setFailed(false);
    try {
      const [recordText, ledger] = await Promise.all([
        loadText(reach.base, `${FOLDER}${row.file}`),
        loadText(reach.base, `${FOLDER}ledger.jsonl`),
      ]);
      const result = await verifyRecord(recordText, ledger, null);
      const hashes = result.ledger.map((l) => l.lineSha256);
      const chain = anchor.configured
        ? await anchor.check("daily-record", result.position, hashes)
        : null;
      const { bitcoin, signature } = await witnessesOf(
        subjectLabel(reach.info.site, "daily-record"),
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
        details: detailsOf(JSON.parse(recordText) as DailyRecord),
      });
    } catch {
      setFailed(true);
    } finally {
      setChecking(false);
    }
  };

  const compare = async () => {
    if (record === null) {
      return;
    }
    setComparison({ step: "running" });
    try {
      const now = await sourceYear(record);
      setComparison({ step: "done", text: compared(compareYear(record, now), source) });
    } catch {
      setComparison({ step: "failed" });
    }
  };

  return (
    <>
      <button
        type="button"
        className="case-check-link"
        disabled={checking}
        aria-busy={checking}
        onClick={() => void check()}
      >
        <ShieldCheck size={13} strokeWidth={1.9} aria-hidden="true" />
        {checking ? CASE_COPY.record.verifying : copy.check}
      </button>
      <button
        type="button"
        className="case-check-link"
        disabled={record === null || comparison.step === "running"}
        aria-busy={comparison.step === "running"}
        onClick={() => void compare()}
      >
        <GitCompareArrows size={13} strokeWidth={1.9} aria-hidden="true" />
        {comparison.step === "running" ? copy.comparing : copy.compare(source)}
      </button>
      <span className="case-flow__result" ref={resultRef} role="status" aria-live="polite">
        {failed ? CASE_COPY.record.failed : null}
        {comparison.step === "failed" ? copy.compareFailed(source) : null}
        {comparison.step === "done" ? comparison.text : null}
      </span>
      <VerifyDialog
        title={copy.checkTitle}
        result={proof?.result ?? null}
        chain={proof?.chain ?? null}
        bitcoin={proof?.bitcoin ?? null}
        signature={proof?.signature ?? null}
        fixedOn={proof?.fixedOn ?? null}
        details={proof?.details ?? []}
        download={proof === null ? null : `${reach.base}${FOLDER}${row.file}`}
        onClose={() => {
          setProof(null);
        }}
      />
    </>
  );
}
