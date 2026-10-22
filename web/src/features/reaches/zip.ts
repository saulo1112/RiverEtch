// A small zip writer and reader for "Export with proof" and "Check a file", with no dependency.
// The writer stores each file as it is (no compression: the export is a few hundred kilobytes of
// text, and a stored zip is simple enough to check by hand). The reader opens stored files and,
// through the browser's own DecompressionStream, deflated ones (a file someone zipped again with
// another tool). Every file's CRC-32 is checked on reading.

/** One file of a zip: its path inside the archive and its bytes. */
export interface ZipEntry {
  readonly name: string;
  readonly data: Uint8Array;
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) {
      c = (c & 1) !== 0 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

/**
 * The CRC-32 of some bytes (the zip format's checksum).
 *
 * @param bytes - The bytes.
 * @returns The checksum, unsigned.
 */
export function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff;
  for (const byte of bytes) {
    c = (CRC_TABLE[(c ^ byte) & 0xff] ?? 0) ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

// A date and time as the zip format writes them (MS-DOS fields, local to no zone: UTC here).
function dosTime(when: Date): { time: number; date: number } {
  const year = Math.max(1980, when.getUTCFullYear());
  return {
    time: (when.getUTCHours() << 11) | (when.getUTCMinutes() << 5) | (when.getUTCSeconds() >> 1),
    date: ((year - 1980) << 9) | ((when.getUTCMonth() + 1) << 5) | when.getUTCDate(),
  };
}

/**
 * A zip of the given files, each stored without compression, names in UTF-8.
 *
 * @param entries - The files, in the order they are written.
 * @param when - The time written for every file.
 * @returns The archive's bytes.
 */
export function makeZip(entries: readonly ZipEntry[], when: Date = new Date()): Uint8Array {
  const encoder = new TextEncoder();
  const { time, date } = dosTime(when);
  const locals: Uint8Array[] = [];
  const centrals: Uint8Array[] = [];
  let offset = 0;
  for (const entry of entries) {
    const name = encoder.encode(entry.name);
    const crc = crc32(entry.data);
    const local = new Uint8Array(30 + name.length);
    const l = new DataView(local.buffer);
    l.setUint32(0, 0x04034b50, true);
    l.setUint16(4, 20, true); // version needed
    l.setUint16(6, 0x0800, true); // names in UTF-8
    l.setUint16(8, 0, true); // stored
    l.setUint16(10, time, true);
    l.setUint16(12, date, true);
    l.setUint32(14, crc, true);
    l.setUint32(18, entry.data.length, true);
    l.setUint32(22, entry.data.length, true);
    l.setUint16(26, name.length, true);
    local.set(name, 30);
    const central = new Uint8Array(46 + name.length);
    const c = new DataView(central.buffer);
    c.setUint32(0, 0x02014b50, true);
    c.setUint16(4, 20, true); // version made by
    c.setUint16(6, 20, true); // version needed
    c.setUint16(8, 0x0800, true);
    c.setUint16(10, 0, true);
    c.setUint16(12, time, true);
    c.setUint16(14, date, true);
    c.setUint32(16, crc, true);
    c.setUint32(20, entry.data.length, true);
    c.setUint32(24, entry.data.length, true);
    c.setUint16(28, name.length, true);
    c.setUint32(42, offset, true);
    central.set(name, 46);
    locals.push(local, entry.data);
    centrals.push(central);
    offset += local.length + entry.data.length;
  }
  const centralSize = centrals.reduce((n, b) => n + b.length, 0);
  const end = new Uint8Array(22);
  const e = new DataView(end.buffer);
  e.setUint32(0, 0x06054b50, true);
  e.setUint16(8, entries.length, true);
  e.setUint16(10, entries.length, true);
  e.setUint32(12, centralSize, true);
  e.setUint32(16, offset, true);
  const out = new Uint8Array(offset + centralSize + end.length);
  let at = 0;
  for (const part of [...locals, ...centrals, end]) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

// Inflates raw deflate data with the browser's (or Node's) own stream.
async function inflate(data: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([new Uint8Array(data)])
    .stream()
    .pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/**
 * The files of a zip, by name (folders left out); each file's CRC-32 is checked.
 *
 * @param bytes - The archive.
 * @returns The files.
 * @throws {Error} When the bytes are not a zip, use an unknown method, or a file is damaged.
 */
export async function readZip(bytes: Uint8Array): Promise<Map<string, Uint8Array>> {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let end = -1;
  for (let k = bytes.length - 22; k >= Math.max(0, bytes.length - 22 - 65535); k -= 1) {
    if (view.getUint32(k, true) === 0x06054b50) {
      end = k;
      break;
    }
  }
  if (end < 0) {
    throw new Error("not a zip file");
  }
  const count = view.getUint16(end + 10, true);
  let at = view.getUint32(end + 16, true);
  const decoder = new TextDecoder();
  const files = new Map<string, Uint8Array>();
  for (let n = 0; n < count; n += 1) {
    if (view.getUint32(at, true) !== 0x02014b50) {
      throw new Error("damaged zip directory");
    }
    const method = view.getUint16(at + 10, true);
    const crc = view.getUint32(at + 16, true);
    const compressed = view.getUint32(at + 20, true);
    const size = view.getUint32(at + 24, true);
    const nameLength = view.getUint16(at + 28, true);
    const extraLength = view.getUint16(at + 30, true);
    const commentLength = view.getUint16(at + 32, true);
    const offset = view.getUint32(at + 42, true);
    const name = decoder.decode(bytes.subarray(at + 46, at + 46 + nameLength));
    at += 46 + nameLength + extraLength + commentLength;
    if (name.endsWith("/")) {
      continue;
    }
    const start =
      offset + 30 + view.getUint16(offset + 26, true) + view.getUint16(offset + 28, true);
    const raw = bytes.subarray(start, start + compressed);
    let data: Uint8Array;
    if (method === 0) {
      data = raw.slice();
    } else if (method === 8) {
      data = await inflate(raw);
    } else {
      throw new Error(`${name}: an unknown compression method`);
    }
    if (data.length !== size || crc32(data) !== crc) {
      throw new Error(`${name}: damaged (its checksum does not match)`);
    }
    files.set(name, data);
  }
  return files;
}
