// The RiverEtch mark: a capital E whose three arms are the same river wave, built from strokes so
// every corner and thickness match. Units are those of a 64 × 64 icon. The static icons in
// web/public (logo-mark.svg, logo-mark-light.svg, favicon.svg) draw it from these values;
// test/logo.test.ts checks that they stay the same. The page header shows the wordmark only.

/** Stroke width of the stem and the arms. */
export const MARK_STROKE = 7;

/** The stem, top arm to bottom arm. */
export const MARK_STEM = "M17 15V47";

/**
 * One arm, from the stem: flat, a dip of 3 units at about 57 % of its length, then a slight crest
 * at its end (x 30). Every arm is this path, moved to its height.
 */
export const MARK_WAVE = "M0 0C8 0 11.5 3 17 3S26-.6 30-.6";

/** Where each arm starts: on the stem, at the top, middle and bottom. */
export const MARK_ARMS: readonly (readonly [number, number])[] = [
  [17, 15],
  [17, 31],
  [17, 47],
];

/** The etch: a slanted bite into the stem's outer edge at mid-height, cut out by a mask. */
export const MARK_NOTCH = "M12 31.1 16.6 29.4V31.6L12 33.5Z";
