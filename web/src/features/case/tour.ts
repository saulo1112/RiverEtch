// Where the guided tour puts its ring and its card (panels/GuidedTour.tsx): pure geometry, so the
// tests check it without a browser.

const GUTTER = 16; // the card never comes closer to the screen's edge
const OFFSET = 14; // from the ring to the card (the arrow sits in it)
const RING_PAD = 6; // the ring around the control
const ARROW_INSET = 22; // the arrow never comes closer to the card's corner
const SHEET = 640; // below this width, the card is a sheet across the screen

/** A side of the card or of the control. */
export type Side = "right" | "left" | "bottom" | "top";

/** A box in viewport pixels. */
export interface Box {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

/** Where everything goes for one step. */
export interface Layout {
  readonly ring: Box | null;
  readonly card: { readonly left: number; readonly top: number; readonly width: number };
  /** The side of the card the arrow is on, and its offset along it (null: no arrow). */
  readonly arrow: { readonly side: Side; readonly at: number } | null;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), Math.max(lo, hi));

/**
 * Places the ring around a control and the card beside it, on the first side with room for it
 * (right, left, below, above), or as a sheet on a narrow screen.
 *
 * @param rect - The control's box (null: no control, the card is centred).
 * @param card - The card's size.
 * @param card.width - Its width, in CSS pixels.
 * @param card.height - Its height.
 * @param view - The viewport's size.
 * @param view.width - Its width, in CSS pixels.
 * @param view.height - Its height.
 * @returns The layout.
 */
export function layout(
  rect: Box | null,
  card: { readonly width: number; readonly height: number },
  view: { readonly width: number; readonly height: number },
): Layout {
  const { width: w, height: h } = view;
  const ring =
    rect === null
      ? null
      : {
          left: rect.left - RING_PAD,
          top: rect.top - RING_PAD,
          width: rect.width + 2 * RING_PAD,
          height: rect.height + 2 * RING_PAD,
        };
  if (w < SHEET || ring === null) {
    const width = ring === null ? Math.min(400, w - 2 * GUTTER) : w - 2 * GUTTER;
    // A sheet goes where the control is not: at the top when the control is low.
    const low = ring !== null && ring.top + ring.height / 2 > h / 2;
    const top =
      ring === null
        ? Math.max(GUTTER, (h - card.height) / 2)
        : low
          ? GUTTER
          : h - card.height - GUTTER;
    return { ring, card: { left: (w - width) / 2, top, width }, arrow: null };
  }
  const width = Math.min(340, w - 2 * GUTTER);
  const room: Record<Side, number> = {
    right: w - (ring.left + ring.width) - OFFSET - GUTTER - width,
    left: ring.left - OFFSET - GUTTER - width,
    bottom: h - (ring.top + ring.height) - OFFSET - GUTTER - card.height,
    top: ring.top - OFFSET - GUTTER - card.height,
  };
  const order: Side[] = ["right", "left", "bottom", "top"];
  const side =
    order.find((s) => room[s] >= 0) ?? order.reduce((a, b) => (room[b] > room[a] ? b : a));
  const cx = ring.left + ring.width / 2;
  const cy = ring.top + ring.height / 2;
  if (side === "right" || side === "left") {
    const left = side === "right" ? ring.left + ring.width + OFFSET : ring.left - OFFSET - width;
    const top = clamp(cy - card.height / 2, GUTTER, h - card.height - GUTTER);
    return {
      ring,
      card: { left, top, width },
      arrow: {
        side: side === "right" ? "left" : "right",
        at: clamp(cy - top, ARROW_INSET, card.height - ARROW_INSET),
      },
    };
  }
  const left = clamp(cx - width / 2, GUTTER, w - width - GUTTER);
  const top = side === "bottom" ? ring.top + ring.height + OFFSET : ring.top - OFFSET - card.height;
  return {
    ring,
    card: { left, top, width },
    arrow: {
      side: side === "bottom" ? "top" : "bottom",
      at: clamp(cx - left, ARROW_INSET, width - ARROW_INSET),
    },
  };
}
