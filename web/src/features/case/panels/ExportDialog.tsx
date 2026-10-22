import { Download, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { useProofIo } from "../../chain/useProofIo.ts";
import { REACH_CASES } from "../../reaches/catalog.ts";
import { loadReach } from "../../reaches/data.ts";
import {
  buildExport,
  DATASET_IDS,
  planExport,
  rowsOf,
  type DatasetId,
  type ExportPlan,
} from "../../reaches/proof.ts";
import type { ReachData } from "../../reaches/types.ts";
import { CASE_COPY } from "../content.ts";

/** Props of {@link ExportDialog}. */
export interface ExportDialogProps {
  /** The dialog is open. */
  readonly open: boolean;
  /** The reach of the case (its sealed year). */
  readonly reach: ReachData;
  /** Its title, e.g. "Mississippi · Belle Chasse". */
  readonly title: string;
  readonly onClose: () => void;
}

type Step =
  | { readonly step: "idle" | "building" | "failed" }
  | { readonly step: "saved"; readonly name: string; readonly sha: string };

/**
 * "Export with proof": a modal dialog to choose the river (this one or all), the data, the period
 * and the reach shape, with a live count of the readings and of each board apart, then one zip
 * built in the browser. Nothing is uploaded.
 *
 * @param props - The dialog's props.
 * @param props.open - The dialog is open.
 * @param props.reach - The case's reach.
 * @param props.title - Its title.
 * @param props.onClose - The dialog closed.
 * @returns The dialog element (closed while `open` is false).
 */
export function ExportDialog({ open, reach, title, onClose }: ExportDialogProps) {
  const copy = CASE_COPY.exportDialog;
  const io = useProofIo();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const fromId = useId();
  const toId = useId();
  const [scope, setScope] = useState<"this" | "all">("this");
  const [all, setAll] = useState<readonly ReachData[] | null>(null);
  const [chosen, setChosen] = useState<ReadonlySet<DatasetId> | null>(null);
  const [shape, setShape] = useState(false);
  const [ranged, setRanged] = useState(false);
  const [from, setFrom] = useState("2026-01-01");
  const [to, setTo] = useState(new Date().toISOString().slice(0, 10));
  // The count for a choice, by its key: another choice shows "Counting" until its own arrives.
  const [counted, setCounted] = useState<{ key: string; plan: ExportPlan } | null>(null);
  const [step, setStep] = useState<Step>({ step: "idle" });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) {
      return;
    }
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  // Every reach, read once when "All rivers" is chosen.
  useEffect(() => {
    if (!open || scope !== "all" || all !== null) {
      return undefined;
    }
    let live = true;
    Promise.all(REACH_CASES.map((c) => loadReach(c.id).catch(() => null)))
      .then((found) => {
        if (live) {
          setAll(found.filter((r): r is ReachData => r !== null));
        }
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [open, scope, all]);

  const reaches = scope === "this" ? [reach] : (all ?? []);
  const available = DATASET_IDS.filter((d) => reaches.some((r) => rowsOf(r, d).length > 0));
  const datasets = available.filter((d) => chosen === null || chosen.has(d));
  const key = `${scope}|${String(all?.length ?? 0)}|${datasets.join(",")}|${ranged ? `${from}|${to}` : "all"}`;

  // The live count: recomputed from the files and the chain whenever the choice changes.
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    let live = true;
    planExport(reaches, datasets, ranged ? from : null, ranged ? to : null, io)
      .then((next) => {
        if (live) {
          setCounted({ key, plan: next });
        }
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` names everything the plan reads
  }, [open, key, io]);

  const plan = counted?.key === key ? counted.plan : null;
  const toggle = (d: DatasetId) => {
    const next = new Set(chosen ?? available);
    if (next.has(d)) {
      next.delete(d);
    } else {
      next.add(d);
    }
    setChosen(next);
    setStep({ step: "idle" });
  };

  const download = async () => {
    if (plan === null || plan.total.readings === 0) {
      return;
    }
    setStep({ step: "building" });
    try {
      const file = await buildExport(plan, shape, io, {
        exportedUtc: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
        appVersion: __APP_VERSION__,
        appCommit: __APP_COMMIT__,
        publicKey: __ML_DSA_PUBLIC_KEY__,
        cards: __ALONG_CARDS__,
      });
      const url = URL.createObjectURL(
        new Blob([new Uint8Array(file.zip)], { type: "application/zip" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = file.name;
      link.click();
      URL.revokeObjectURL(url);
      setStep({ step: "saved", name: file.name, sha: file.manifestSha256 });
    } catch {
      setStep({ step: "failed" });
    }
  };

  const total = plan?.total;
  const summary =
    total === undefined
      ? copy.counting
      : total.readings === 0
        ? copy.none
        : total.ethereum === null || total.waiting === null
          ? copy.summaryOffline(total.readings, total.bitcoin)
          : copy.summary(total.readings, total.ethereum, total.bitcoin, total.waiting);
  return (
    <dialog
      ref={dialogRef}
      className="case-proof case-export"
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          event.currentTarget.close();
        }
      }}
    >
      <div className="case-proof__body">
        <div className="case-proof__head">
          <h2 className="case-proof__title" id={titleId}>
            {copy.title}
          </h2>
          <button
            type="button"
            className="case-proof__close"
            aria-label={copy.close}
            onClick={() => dialogRef.current?.close()}
          >
            <X size={18} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </div>
        <p className="case-proof__note">{CASE_COPY.proof.exportPurpose}</p>
        <fieldset className="case-export__group">
          <legend>{copy.river}</legend>
          <label className="case-export__choice">
            <input
              type="radio"
              name="case-export-river"
              checked={scope === "this"}
              onChange={() => {
                setScope("this");
                setStep({ step: "idle" });
              }}
            />
            {copy.thisRiver(title)}
          </label>
          <label className="case-export__choice">
            <input
              type="radio"
              name="case-export-river"
              checked={scope === "all"}
              onChange={() => {
                setScope("all");
                setStep({ step: "idle" });
              }}
            />
            {copy.allRivers}
          </label>
        </fieldset>
        <fieldset className="case-export__group">
          <legend>{copy.data}</legend>
          {available.map((d) => (
            <label key={d} className="case-export__choice">
              <input
                type="checkbox"
                checked={datasets.includes(d)}
                onChange={() => {
                  toggle(d);
                }}
              />
              {copy.datasets[d]}
            </label>
          ))}
          <label className="case-export__choice">
            <input
              type="checkbox"
              checked={shape}
              onChange={(event) => {
                setShape(event.target.checked);
              }}
            />
            {copy.shape}
          </label>
        </fieldset>
        <fieldset className="case-export__group">
          <legend>{copy.period}</legend>
          <label className="case-export__choice">
            <input
              type="radio"
              name="case-export-period"
              checked={!ranged}
              onChange={() => {
                setRanged(false);
              }}
            />
            {copy.all}
          </label>
          <label className="case-export__choice">
            <input
              type="radio"
              name="case-export-period"
              checked={ranged}
              onChange={() => {
                setRanged(true);
              }}
            />
            {copy.range}
          </label>
          {ranged ? (
            <div className="case-export__dates">
              <label htmlFor={fromId}>{copy.from}</label>
              <input
                id={fromId}
                type="date"
                value={from}
                onChange={(event) => {
                  setFrom(event.target.value);
                }}
              />
              <label htmlFor={toId}>{copy.to}</label>
              <input
                id={toId}
                type="date"
                value={to}
                onChange={(event) => {
                  setTo(event.target.value);
                }}
              />
            </div>
          ) : null}
          <p className="case-export__note">{copy.periodNote}</p>
        </fieldset>
        <p className="case-export__summary" aria-live="polite">
          {summary}
        </p>
        <p className="case-proof__note">{CASE_COPY.record.boards}</p>
        <button
          type="button"
          className="case-btn case-btn--solid case-export__download"
          disabled={total === undefined || total.readings === 0 || step.step === "building"}
          onClick={() => void download()}
        >
          <Download size={15} strokeWidth={1.9} aria-hidden="true" />
          {step.step === "building" ? copy.building : copy.download}
        </button>
        <p className="case-export__status" aria-live="polite">
          {step.step === "saved" ? copy.saved(step.name, step.sha) : null}
          {step.step === "failed" ? copy.failed : null}
        </p>
        <p className="case-proof__note">{copy.local}</p>
      </div>
    </dialog>
  );
}
