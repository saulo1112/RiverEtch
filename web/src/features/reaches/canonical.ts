// The pipeline's canonical JSON, recomputed in the browser so anyone can check a record's seal.
// Python hashes `json.dumps(data, sort_keys=True, separators=(",", ":"))`. Parsing a file with
// JSON.parse would lose how each number was written (Python writes 3.0, JavaScript 3), so this
// parser keeps every number's text exactly as the file has it, and the serializer writes it back.

/** A number as the file wrote it. */
export class NumberText {
  /** The number's characters in the file. */
  readonly text: string;

  /**
   * Keeps a number's text.
   *
   * @param text - The number's characters in the file.
   */
  constructor(text: string) {
    this.text = text;
  }
}

/** A parsed JSON value whose numbers keep their text. */
export type JsonValue =
  null | boolean | string | NumberText | JsonValue[] | { [key: string]: JsonValue };

/**
 * Parses JSON, keeping each number's text.
 *
 * @param text - A JSON document.
 * @returns The value.
 * @throws {SyntaxError} On malformed JSON.
 */
export function parseJson(text: string): JsonValue {
  let at = 0;
  const fail = (what: string): never => {
    throw new SyntaxError(`${what} at ${String(at)}`);
  };
  const space = () => {
    while (at < text.length && " \t\n\r".includes(text.charAt(at))) {
      at += 1;
    }
  };
  const value = (): JsonValue => {
    space();
    const c = text.charAt(at);
    if (c === "{") {
      at += 1;
      const out: Record<string, JsonValue> = {};
      space();
      if (text.charAt(at) === "}") {
        at += 1;
        return out;
      }
      for (;;) {
        space();
        if (text.charAt(at) !== '"') {
          fail("expected a key");
        }
        const key = string();
        space();
        if (text.charAt(at) !== ":") {
          fail("expected ':'");
        }
        at += 1;
        out[key] = value();
        space();
        const next = text.charAt(at);
        at += 1;
        if (next === "}") {
          return out;
        }
        if (next !== ",") {
          fail("expected ',' or '}'");
        }
      }
    }
    if (c === "[") {
      at += 1;
      const out: JsonValue[] = [];
      space();
      if (text.charAt(at) === "]") {
        at += 1;
        return out;
      }
      for (;;) {
        out.push(value());
        space();
        const next = text.charAt(at);
        at += 1;
        if (next === "]") {
          return out;
        }
        if (next !== ",") {
          fail("expected ',' or ']'");
        }
      }
    }
    if (c === '"') {
      return string();
    }
    for (const [word, result] of [
      ["true", true],
      ["false", false],
      ["null", null],
    ] as const) {
      if (text.startsWith(word, at)) {
        at += word.length;
        return result;
      }
    }
    const match = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(text.slice(at, at + 64));
    if (match === null) {
      return fail("unexpected character");
    }
    at += match[0].length;
    return new NumberText(match[0]);
  };
  const string = (): string => {
    const start = at;
    at += 1;
    while (at < text.length && text.charAt(at) !== '"') {
      at += text.charAt(at) === "\\" ? 2 : 1;
    }
    at += 1;
    return JSON.parse(text.slice(start, at)) as string;
  };
  const result = value();
  space();
  if (at !== text.length) {
    fail("trailing characters");
  }
  return result;
}

// Python's json escapes for one string; with `ascii` every non-ASCII character becomes \uXXXX.
function quote(value: string, ascii: boolean): string {
  const text = JSON.stringify(value);
  return ascii
    ? text.replace(/[\u0080-￿]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`)
    : text;
}

/**
 * The canonical text of a value: keys sorted, no whitespace, numbers as written.
 *
 * @param value - The value.
 * @param ascii - Escape non-ASCII characters (Python's default `ensure_ascii`).
 * @returns The text Python's `json.dumps(..., sort_keys=True, separators=(",", ":"))` writes.
 */
export function canonical(value: JsonValue, ascii = false): string {
  if (value === null) {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string") {
    return quote(value, ascii);
  }
  if (value instanceof NumberText) {
    return value.text;
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonical(item, ascii)).join(",")}]`;
  }
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${quote(key, ascii)}:${canonical(value[key] ?? null, ascii)}`).join(",")}}`;
}

/**
 * SHA-256 of a text's UTF-8 bytes.
 *
 * @param text - The text.
 * @returns The hex digest.
 */
export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
