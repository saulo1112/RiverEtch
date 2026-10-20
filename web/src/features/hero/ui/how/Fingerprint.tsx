import { Check, Minus, Plus, RotateCcw, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

import {
  canonical,
  NumberText,
  parseJson,
  sha256Hex,
  type JsonValue,
} from "../../../reaches/canonical.ts";
import { reachBase } from "../../../reaches/data.ts";
import { HOW_IT_WORKS } from "../content.ts";

const copy = HOW_IT_WORKS.fingerprint;
const SITE = "mississippi-belle-chasse";

type JsonObject = Record<string, JsonValue>;
const isObject = (v: JsonValue | undefined): v is JsonObject =>
  typeof v === "object" && v !== null && !Array.isArray(v) && !(v instanceof NumberText);

interface Loaded {
  readonly record: JsonObject;
  readonly sealed: string;
  readonly place: string;
  readonly date: string;
  /** The turbidity value as the file writes it (null: the pass has none). */
  readonly value: string | null;
}

// The record with its turbidity set to `text` (as written), without its seal: what is hashed.
function content(record: JsonObject, text: string | null): JsonObject {
  const copyOf: JsonObject = { ...record };
  delete copyOf.recordSha256;
  const estimates = copyOf.estimates;
  if (text !== null && Array.isArray(estimates) && isObject(estimates[0])) {
    copyOf.estimates = [{ ...estimates[0], value: new NumberText(text) }, ...estimates.slice(1)];
  }
  return copyOf;
}

async function load(): Promise<Loaded> {
  const response = await fetch(`${reachBase(SITE)}latest.json`);
  if (!response.ok) {
    throw new Error(String(response.status));
  }
  const record = parseJson(await response.text());
  if (!isObject(record) || typeof record.recordSha256 !== "string") {
    throw new Error("not a sealed record");
  }
  const estimates = record.estimates;
  const first = Array.isArray(estimates) ? estimates[0] : undefined;
  const value = isObject(first) && first.value instanceof NumberText ? first.value.text : null;
  return {
    record,
    sealed: record.recordSha256,
    place: typeof record.reachId === "string" ? record.reachId : "",
    date: typeof record.date === "string" ? record.date : "",
    value,
  };
}

// The value one step up or down, in the last decimal place the sealed value writes (30.49 steps
// by 0.01), so a single press changes one digit.
function stepped(text: string | null, sealed: string, by: number): string {
  const places = sealed.split(".")[1]?.length ?? 0;
  const base = Number(text);
  const from = Number.isFinite(base) ? base : Number(sealed);
  return (from + by * 10 ** -places).toFixed(places);
}

// A fingerprint, its characters that differ from the sealed one marked and counted.
function Hash({ label, hash, against }: { label: string; hash: string; against?: string }) {
  const changed =
    against === undefined ? 0 : Array.from(hash).filter((c, k) => against[k] !== c).length;
  return (
    <p className="how-print__hash">
      <span className="how-print__hash-label">
        {label}
        {changed > 0 ? (
          <span className="how-print__changed">{copy.changed(changed, hash.length)}</span>
        ) : null}
      </span>
      <code>
        {Array.from(hash, (c, k) => (
          <span key={k} data-diff={against !== undefined && against[k] !== c}>
            {c}
          </span>
        ))}
      </code>
    </p>
  );
}

/**
 * A real sealed reading (Belle Chasse's newest record, from this build's files) and its
 * fingerprint, recomputed in the browser as the reader changes its turbidity: any other value and
 * every character can change, and the check says the reading was changed, by mark and words.
 *
 * @returns The demo.
 */
export function Fingerprint() {
  const inputId = useId();
  const [loaded, setLoaded] = useState<Loaded | null | "failed">(null);
  const [text, setText] = useState<string | null>(null);
  const [now, setNow] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    load()
      .then((l) => {
        if (live) {
          setLoaded(l);
          setText(l.value);
        }
      })
      .catch(() => {
        if (live) {
          setLoaded("failed");
        }
      });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (loaded === null || loaded === "failed") {
      return undefined;
    }
    let live = true;
    void sha256Hex(canonical(content(loaded.record, text))).then((h) => {
      if (live) {
        setNow(h);
      }
    });
    return () => {
      live = false;
    };
  }, [loaded, text]);

  if (loaded === null) {
    return <p className="how-print__note">{copy.loading}</p>;
  }
  if (loaded === "failed") {
    return <p className="how-print__note">{copy.unavailable}</p>;
  }
  const same = now === loaded.sealed;
  return (
    <section className="how-print" aria-label={copy.demoTitle}>
      <p className="how-print__title">{copy.demoTitle}</p>
      <dl className="how-print__fields">
        <dt>{copy.place}</dt>
        <dd>Mississippi at Belle Chasse</dd>
        <dt>{copy.date}</dt>
        <dd>{loaded.date}</dd>
        {loaded.value === null ? null : (
          <>
            <dt>
              <label htmlFor={inputId}>{copy.turbidity}</label>
            </dt>
            <dd className="how-print__edit">
              <button
                type="button"
                className="how-print__step"
                aria-label={copy.down}
                onClick={() => {
                  setText(stepped(text, loaded.value ?? "0", -1));
                }}
              >
                <Minus size={15} strokeWidth={2} aria-hidden="true" />
              </button>
              <input
                id={inputId}
                className="how-print__input"
                type="text"
                inputMode="decimal"
                value={text ?? ""}
                aria-describedby={`${inputId}-hint`}
                onChange={(event) => {
                  setText(event.target.value.trim() === "" ? "0" : event.target.value.trim());
                }}
              />
              <button
                type="button"
                className="how-print__step"
                aria-label={copy.up}
                onClick={() => {
                  setText(stepped(text, loaded.value ?? "0", 1));
                }}
              >
                <Plus size={15} strokeWidth={2} aria-hidden="true" />
              </button>
              <span>FNU</span>
              <span className="how-print__hint" id={`${inputId}-hint`}>
                {copy.edit}
              </span>
            </dd>
          </>
        )}
      </dl>
      <Hash label={copy.sealed} hash={loaded.sealed} />
      {now === null ? null : <Hash label={copy.now} hash={now} against={loaded.sealed} />}
      <p className="how-print__verdict" data-same={same} aria-live="polite">
        {same ? (
          <Check size={16} strokeWidth={2.25} aria-hidden="true" />
        ) : (
          <X size={16} strokeWidth={2.25} aria-hidden="true" />
        )}
        <span>{same ? copy.matches : copy.differs}</span>
        {same || loaded.value === null ? null : (
          <button
            type="button"
            className="how-print__reset"
            onClick={() => {
              setText(loaded.value);
            }}
          >
            <RotateCcw size={14} strokeWidth={1.9} aria-hidden="true" />
            {copy.reset}
          </button>
        )}
      </p>
      <p className="how-small">{copy.technical}</p>
    </section>
  );
}
