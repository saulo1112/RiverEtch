import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

type Rgba = [number, number, number, number];

const tokens = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");
const caseCss = readFileSync(new URL("../src/features/case/case.css", import.meta.url), "utf8");

// "rgb(240 246 255 / 0.56)" or "#22d3ee".
function parse(color: string): Rgba {
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color);
  if (hex !== null) {
    return [parseInt(hex[1] ?? "", 16), parseInt(hex[2] ?? "", 16), parseInt(hex[3] ?? "", 16), 1];
  }
  const rgb = /^rgb\((\d+) (\d+) (\d+)(?: \/ ([\d.]+))?\)$/.exec(color);
  assert.ok(rgb !== null, `unparsed colour ${color}`);
  return [
    Number(rgb[1]),
    Number(rgb[2]),
    Number(rgb[3]),
    rgb[4] === undefined ? 1 : Number(rgb[4]),
  ];
}

function token(name: string): Rgba {
  const match = new RegExp(`${name}:\\s*([^;]+);`).exec(tokens);
  assert.ok(match?.[1] !== undefined, `missing token ${name}`);
  return parse(match[1].trim());
}

// A colour laid over an opaque one.
function over([r, g, b, a]: Rgba, [R, G, B]: Rgba): Rgba {
  return [r * a + R * (1 - a), g * a + G * (1 - a), b * a + B * (1 - a), 1];
}

// WCAG 2 relative luminance and contrast ratio.
function luminance([r, g, b]: Rgba): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: Rgba, b: Rgba): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((hi ?? 0) + 0.05) / ((lo ?? 0) + 0.05);
}

// The solid panel (reduced transparency, or no backdrop filter) over the case view's own ground.
const ground = parse(/\.case-view \{[^}]*?background: (#[0-9a-f]{6});/i.exec(caseCss)?.[1] ?? "");
const panel = over(token("--glass-solid"), ground);

void test("every text token reaches 4.5:1 over the solid panel", () => {
  for (const name of ["--text-1", "--text-2", "--text-3", "--accent"]) {
    const ratio = contrast(over(token(name), panel), panel);
    assert.ok(ratio >= 4.5, `${name}: ${ratio.toFixed(2)}:1`);
  }
});

void test("the reliability bars reach 3:1 over the solid panel", () => {
  const bar = /\.case-bars__bar \{[^}]*?background: (rgb\([^)]+\));/.exec(caseCss)?.[1] ?? "";
  for (const fill of [parse(bar), token("--accent")]) {
    const ratio = contrast(over(fill, panel), panel);
    assert.ok(ratio >= 3, `bar ${fill.join(",")}: ${ratio.toFixed(2)}:1`);
  }
});
