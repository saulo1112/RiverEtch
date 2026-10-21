// Focus the app moves itself (a screen that opens, a dialog or a tour handing it back) never shows a
// focus ring: there is none anywhere in the app (index.css), and this tells the browser so too.

/**
 * Moves the focus for the visitor, without a focus ring.
 *
 * @param element - Where the focus goes (nothing happens without one).
 * @param preventScroll - Keep the page where it is.
 */
export function focusForVisitor(
  element: HTMLElement | null | undefined,
  preventScroll = true,
): void {
  element?.focus({ preventScroll, focusVisible: false });
}
